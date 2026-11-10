"""Demand forecasting with a global, direct multi-horizon gradient-boosting model.

* Global: one model learns from all brand x category x channel series at once.
* Target: year-over-year log growth of monthly units, ``y[t] - y[t-12]``, learned as a residual
  over the recent 3-month YoY momentum (residual boosting on top of a seasonal-naive-with-drift
  baseline). Modelling growth rather than levels lets a tree ensemble extrapolate fast-growing
  brands, and differencing against the same month last year removes fixed seasonality.
* Direct multi-horizon: each training row pairs the momentum observed at a forecast origin with
  the outcome ``h`` months later (h = 1..12), so the model learns how momentum fades with the
  horizon and multi-step forecasts never feed on their own predictions.
* Exogenous drivers: the moving Ramadan / Eid calendar, list-price and promo-depth changes and
  stock-outs (all expressed as changes versus the same month last year).

Candidates (the boosted model, two seasonal-naive baselines and a GBM + drift ensemble) are compared
with rolling-origin backtests (three 6-month folds). The winner produces the 12-month forecast with
empirical, error-based 80% prediction intervals.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.inspection import permutation_importance

from .calendar_id import calendar_frame

FEATURES = ["horizon", "mom1", "mom3", "mom6", "lvl", "ram_d", "pre_d", "post_d", "lp_d", "disc_d", "oos_d",
            "days_d", "month_of_year", "mega_sale", "brand_c", "category_c", "channel_c"]
CATEGORICAL = ["brand_c", "category_c", "channel_c"]
FEATURE_LABELS = {
    "horizon": "Forecast horizon", "mom1": "YoY growth at origin", "mom3": "3-month YoY momentum",
    "mom6": "6-month YoY momentum", "lvl": "Level vs 12-month mean", "ram_d": "Ramadan days shift (YoY)",
    "pre_d": "Pre-Eid peak shift (YoY)", "post_d": "Post-Eid dip shift (YoY)", "lp_d": "Price change (YoY)",
    "disc_d": "Discount change (YoY)", "oos_d": "Stock-out change (YoY)", "days_d": "Trading days (YoY)",
    "month_of_year": "Month of year", "mega_sale": "Mega-sale month", "brand_c": "Brand", "category_c": "Category",
    "channel_c": "Channel",
}
MIN_ORIGIN = 17  # 6-month YoY momentum needs 18 months of history
MOM3 = FEATURES.index("mom3")
Z80 = 1.2816


def make_panel(sales: pd.DataFrame) -> pd.DataFrame:
    d = sales.copy()
    d["month"] = pd.to_datetime(d["month"])
    panel = d.groupby(["month", "brand", "category", "channel"], as_index=False).agg(
        units=("units", "sum"), revenue=("revenue_idr", "sum"), list_price=("list_price_idr", "mean"),
        discount=("discount_pct", "mean"), stockout_days=("stockout_days", "max"))
    panel["price"] = panel["revenue"] / panel["units"].replace(0, np.nan)
    cal = calendar_frame(sorted(panel["month"].unique()))
    panel = panel.merge(cal, on="month", how="left")
    panel["oos_frac"] = (panel["stockout_days"] / panel["days_in_month"]).clip(0, 0.9)
    return panel.sort_values(["brand", "category", "channel", "month"]).reset_index(drop=True)


class DemandForecaster:
    def __init__(self, horizon: int = 12, backtest_months: int = 6, seed: int = 42):
        self.horizon = horizon
        self.backtest_months = backtest_months
        self.seed = seed
        self.model: HistGradientBoostingRegressor | None = None
        self.sigma: dict = {}

    # ------------------------------------------------------------------ matrices
    def _matrices(self, panel: pd.DataFrame) -> None:
        keys = ["brand", "category", "channel"]
        self.series = panel[keys].drop_duplicates().sort_values(keys).reset_index(drop=True)
        self.months = list(pd.DatetimeIndex(sorted(panel["month"].unique())))

        def pivot(col: str) -> np.ndarray:
            w = panel.pivot_table(index=keys, columns="month", values=col, aggfunc="mean")
            w = w.reindex(pd.MultiIndex.from_frame(self.series)).reindex(columns=self.months)
            return w.T.interpolate(limit_direction="both").T.to_numpy(dtype=float)

        self.Y = np.log1p(pivot("units"))
        self.LIST = pivot("list_price")
        self.DISC = np.nan_to_num(pivot("discount"), nan=0.0)
        self.OOS = np.nan_to_num(pivot("oos_frac"), nan=0.0)
        self.LP = np.log(self.LIST * (1 - self.DISC))
        self.cal = calendar_frame(self.months).reset_index(drop=True)
        self.codes = {k: {v: i for i, v in enumerate(sorted(self.series[k].unique()))} for k in keys}
        self.series_codes = np.column_stack([self.series[k].map(self.codes[k]).to_numpy() for k in keys])

    def _extend(self, n_future: int, price_multiplier: dict | None = None) -> None:
        """Append future months: list price held at its last level (optionally scaled per brand),
        promo depth repeats last year's calendar, no stock-outs."""
        last = len(self.months) - 1
        future = pd.date_range(self.months[-1] + pd.offsets.MonthBegin(1), periods=n_future, freq="MS")
        self.months = self.months + list(future)
        mult = np.ones(len(self.series))
        for b, m in (price_multiplier or {}).items():
            mult[(self.series["brand"] == b).to_numpy()] = m
        disc_f = np.column_stack([self.DISC[:, last + 1 + h - 12] for h in range(n_future)])
        self.Y = np.hstack([self.Y, np.full((len(self.series), n_future), np.nan)])
        self.DISC = np.hstack([self.DISC, disc_f])
        self.LIST = np.hstack([self.LIST, np.repeat((self.LIST[:, last] * mult)[:, None], n_future, axis=1)])
        self.OOS = np.hstack([self.OOS, np.zeros((len(self.series), n_future))])
        self.LP = np.log(self.LIST * (1 - self.DISC))
        self.cal = calendar_frame(self.months).reset_index(drop=True)

    def _features(self, o: int, h: int) -> np.ndarray:
        Y, c, j, n = self.Y, self.cal, o + h, len(self.series)

        def yoy(k: int) -> np.ndarray:
            return Y[:, o - k] - Y[:, o - k - 12]

        cols = [
            np.full(n, h), yoy(0), np.mean([yoy(k) for k in range(3)], axis=0),
            np.mean([yoy(k) for k in range(6)], axis=0), Y[:, o] - Y[:, o - 11:o + 1].mean(axis=1),
            np.full(n, c.at[j, "ramadan_share"] - c.at[j - 12, "ramadan_share"]),
            np.full(n, c.at[j, "pre_eid_share"] - c.at[j - 12, "pre_eid_share"]),
            np.full(n, c.at[j, "post_eid_share"] - c.at[j - 12, "post_eid_share"]),
            self.LP[:, j] - self.LP[:, j - 12], self.DISC[:, j] - self.DISC[:, j - 12],
            np.log(1 - self.OOS[:, j]) - np.log(1 - self.OOS[:, j - 12]),
            np.full(n, np.log(c.at[j, "days_in_month"] / c.at[j - 12, "days_in_month"])),
            np.full(n, c.at[j, "month_of_year"]), np.full(n, c.at[j, "mega_sale"]),
        ]
        return np.column_stack(cols + [self.series_codes[:, i] for i in range(3)])

    def _fit(self, known: int) -> HistGradientBoostingRegressor:
        X, y = [], []
        for h in range(1, self.horizon + 1):
            for o in range(MIN_ORIGIN, known - h):
                x = self._features(o, h)
                X.append(x)
                y.append(self.Y[:, o + h] - self.Y[:, o + h - 12] - x[:, MOM3])
        model = HistGradientBoostingRegressor(
            max_iter=300, learning_rate=0.04, max_leaf_nodes=15, min_samples_leaf=60, l2_regularization=1.0,
            categorical_features=[FEATURES.index(c) for c in CATEGORICAL], random_state=self.seed)
        return model.fit(np.vstack(X), np.concatenate(y))

    def _candidates(self, model, origin: int, steps: int) -> dict[str, np.ndarray]:
        start = origin + 1
        gbm = []
        for h in range(1, steps + 1):
            x = self._features(origin, h)
            gbm.append(self.Y[:, origin + h - 12] + x[:, MOM3] + model.predict(x))
        gbm = np.column_stack(gbm)
        drift = np.mean([self.Y[:, origin - k] - self.Y[:, origin - k - 12] for k in range(3)], axis=0)
        snaive = self.Y[:, start - 12:start - 12 + steps]
        return {"gradient_boosting": gbm, "seasonal_naive": snaive, "seasonal_naive_drift": snaive + drift[:, None],
                "ensemble": (gbm + snaive + drift[:, None]) / 2}

    # ------------------------------------------------------------------ public API
    def backtest(self, panel: pd.DataFrame, client: str, folds: int = 3) -> dict:
        """Rolling-origin evaluation over ``folds`` consecutive 6-month windows ending at the last month."""
        self._matrices(panel)
        n, steps = len(self.months), self.backtest_months
        is_client = (self.series["brand"] == client).to_numpy()
        brand_masks = [(self.series["brand"] == b).to_numpy() for b in self.series["brand"].unique()]
        fold_rows, detail, errs = [], [], {}
        for fold, start in enumerate(range(n - steps * folds, n, steps), 1):
            origin = start - 1
            model = self._fit(start)
            actual = np.expm1(self.Y[:, start:start + steps])
            for name, p in self._candidates(model, origin, steps).items():
                f = np.expm1(p)
                tot_a, tot_f = actual.sum(0), f.sum(0)
                cl_a, cl_f = actual[is_client].sum(0), f[is_client].sum(0)
                window = f"{self.months[start]:%Y-%m}..{self.months[start + steps - 1]:%Y-%m}"
                fold_rows.append(dict(fold=fold, window=window, model=name,
                                      series_wape=float(np.abs(actual - f).sum() / actual.sum()),
                                      market_mape=float(np.mean(np.abs(tot_f - tot_a) / tot_a)),
                                      client_mape=float(np.mean(np.abs(cl_f - cl_a) / cl_a))))
                e = errs.setdefault(name, {"brand": [], "market": []})
                e["brand"] += [(f[m].sum(0) - actual[m].sum(0)) / actual[m].sum(0) for m in brand_masks]
                e["market"].append((tot_f - tot_a) / tot_a)
                if fold == folds:
                    for h in range(steps):
                        detail.append(dict(month=self.months[start + h].date().isoformat(), model=name, horizon=h + 1,
                                           market_actual=float(tot_a[h]), market_forecast=float(tot_f[h]),
                                           client_actual=float(cl_a[h]), client_forecast=float(cl_f[h])))
        folds_df = pd.DataFrame(fold_rows)
        summary = folds_df.groupby("model")[["series_wape", "market_mape", "client_mape"]].mean().round(4)
        best = str(summary["series_wape"].idxmin())
        # the client's own total can favour another candidate; record it (and how consistently) rather than switching,
        # because three folds are too few to pick a separate model for one aggregate
        client_best = str(summary["client_mape"].idxmin())
        per_fold = folds_df.pivot(index="fold", columns="model", values="client_mape")
        client_wins = int((per_fold[client_best] < per_fold[best]).sum()) if client_best != best else folds
        hz = np.arange(1, steps + 1)
        be, me = np.array(errs[best]["brand"]), np.array(errs[best]["market"])
        self.sigma = dict(brand=max(float(np.sqrt(np.mean(be ** 2 / hz[None, :]))), 0.02),
                          market=max(float(np.sqrt(np.mean(me ** 2 / hz[None, :]))), 0.015))
        origin, k = n - steps - 1, len(self.series)
        X_bt = np.vstack([self._features(origin, h) for h in range(1, steps + 1)])
        y_bt = np.concatenate([self.Y[:, origin + h] - self.Y[:, origin + h - 12] for h in range(1, steps + 1)])
        y_bt = y_bt - X_bt[:, MOM3]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            imp = permutation_importance(model, X_bt, y_bt, n_repeats=5, random_state=self.seed,
                                         scoring="neg_mean_absolute_error")
        importance = pd.DataFrame(dict(feature=FEATURES, label=[FEATURE_LABELS[f] for f in FEATURES],
                                       importance=imp.importances_mean.round(5))).sort_values("importance", ascending=False)
        return dict(metrics=summary.to_dict(orient="index"), best=best, client_best=client_best, client_wins=client_wins,
                    folds=folds_df.round(4),
                    detail=pd.DataFrame(detail), importance=importance, sigma=self.sigma, n_series=k,
                    backtest_window=[self.months[n - steps * folds].date().isoformat(), self.months[n - 1].date().isoformat()])

    def forecast(self, panel: pd.DataFrame, method: str = "ensemble",
                 price_multiplier: dict | None = None) -> pd.DataFrame:
        self._matrices(panel)
        n = len(self.months)
        origin = n - 1
        self.model = self._fit(n)
        self._extend(self.horizon, price_multiplier)
        Y = self._candidates(self.model, origin, self.horizon)[method]
        units = np.expm1(Y)
        price = np.exp(self.LP[:, n:n + self.horizon])
        rows = [dict(month=self.months[n + h], brand=s.brand, category=s.category, channel=s.channel, horizon=h + 1,
                     units=float(units[i, h]), revenue=float(units[i, h] * price[i, h]))
                for i, s in enumerate(self.series.itertuples(index=False)) for h in range(self.horizon)]
        return pd.DataFrame(rows)


def add_intervals(df: pd.DataFrame, sigma: float, value_cols=("units", "revenue")) -> pd.DataFrame:
    out = df.copy()
    band = np.exp(Z80 * sigma * np.sqrt(out["horizon"]))
    for c in value_cols:
        out[f"{c}_lo"] = out[c] / band
        out[f"{c}_hi"] = out[c] * band
    return out
