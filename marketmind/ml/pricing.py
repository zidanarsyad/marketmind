"""Pricing analytics: econometric price elasticity, what-if scenarios and Van Westendorp PSM."""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm


def estimate_elasticities(panel: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Log-log demand model with fixed effects.

    log(units) = series FE + (month x online/offline) FE + brand-specific quadratic trend
                 + gamma * log(1 - stock-out share) + sum_b beta_b * log(price) * 1[brand = b]

    The series fixed effects absorb level differences, the month x channel-type effects absorb
    seasonality (Ramadan, 11.11, 12.12) and the trends absorb each brand's growth path, so the
    beta_b are identified from promotional and list-price variation. HC1 robust standard errors.
    """
    d = panel[(panel["units"] > 0) & (panel["price"] > 0)].copy()
    d["lu"] = np.log(d["units"])
    d["lp"] = np.log(d["price"])
    d["loos"] = np.log((1 - d["oos_frac"]).clip(lower=0.05))
    d["online"] = (d["channel"] != "Offline Retail").astype(int)
    d["series"] = d["brand"] + "|" + d["category"] + "|" + d["channel"]
    d["time_group"] = d["month"].astype(str) + "_" + d["online"].astype(str)
    d["t"] = (d["month"].rank(method="dense") - 1) / 12.0
    X = pd.get_dummies(d[["series", "time_group"]], drop_first=True, dtype=float)
    brands = sorted(d["brand"].unique())
    for b in brands:
        is_b = (d["brand"] == b).astype(float)
        X[f"trend|{b}"] = d["t"] * is_b
        X[f"trend2|{b}"] = d["t"] ** 2 * is_b
        X[f"lp|{b}"] = d["lp"] * is_b
    X["loos"] = d["loos"]
    X = sm.add_constant(X, has_constant="add")
    with warnings.catch_warnings():  # FE dummies are collinear by design; pinv identifies the elasticities
        warnings.simplefilter("ignore")
        res = sm.OLS(d["lu"].values, X.values).fit(cov_type="HC1")
        params, bse = np.asarray(res.params), np.asarray(res.bse)  # bse is lazy: compute inside the filter
    cols = list(X.columns)
    rows = []
    for b in brands:
        i = cols.index(f"lp|{b}")
        beta, se = float(params[i]), float(bse[i])
        rows.append(dict(brand=b, elasticity=round(beta, 3), std_err=round(se, 3), ci_low=round(beta - 1.96 * se, 3),
                         ci_high=round(beta + 1.96 * se, 3), n_obs=int((d["brand"] == b).sum()),
                         interpretation="elastic" if beta < -1 else "inelastic"))
    info = dict(r_squared=round(float(res.rsquared), 4), n_obs=int(res.nobs), n_params=len(cols),
                stockout_coef=round(float(params[cols.index("loos")]), 3))
    return pd.DataFrame(rows), info


def price_scenarios(elasticity: float, base_revenue: float, changes=None, gross_margin: float = 0.6) -> pd.DataFrame:
    changes = np.round(np.arange(-0.20, 0.201, 0.05), 2) if changes is None else np.asarray(changes)
    vol = (1 + changes) ** elasticity
    rev = (1 + changes) * vol
    profit = ((1 + changes) - (1 - gross_margin)) / gross_margin * vol
    return pd.DataFrame(dict(price_change_pct=(changes * 100).round(0), volume_change_pct=((vol - 1) * 100).round(1),
                             revenue_change_pct=((rev - 1) * 100).round(1),
                             gross_profit_change_pct=((profit - 1) * 100).round(1),
                             revenue_idr_bn=(base_revenue * rev / 1e9).round(1)))


def _cross(x: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    diff = a - b
    idx = np.where(np.sign(diff[:-1]) != np.sign(diff[1:]))[0]
    if not len(idx):
        return float("nan")
    i = idx[0]
    t = diff[i] / (diff[i] - diff[i + 1]) if diff[i] != diff[i + 1] else 0.0
    return float(x[i] + t * (x[i + 1] - x[i]))


def van_westendorp(df: pd.DataFrame, too_cheap: str, cheap: str, expensive: str, too_expensive: str,
                   step: int = 1000) -> tuple[dict, pd.DataFrame]:
    """Van Westendorp Price Sensitivity Meter.

    OPP = too cheap x too expensive; IPP = cheap x expensive;
    PMC = too cheap x not cheap; PME = too expensive x not expensive.
    The acceptable price range is [PMC, PME].
    """
    d = df[[too_cheap, cheap, expensive, too_expensive]].dropna()
    lo, hi = d.min().min(), d.max().max()
    grid = np.arange(np.floor(lo / step) * step, np.ceil(hi / step) * step + step, step)
    tc = np.array([(d[too_cheap] >= p).mean() for p in grid])
    ch = np.array([(d[cheap] >= p).mean() for p in grid])
    ex = np.array([(d[expensive] <= p).mean() for p in grid])
    te = np.array([(d[too_expensive] <= p).mean() for p in grid])
    curves = pd.DataFrame(dict(price_idr=grid, too_cheap=tc, cheap=ch, expensive=ex, too_expensive=te,
                               not_cheap=1 - ch, not_expensive=1 - ex))
    points = dict(pmc=_cross(grid, tc, 1 - ch), opp=_cross(grid, tc, te), ipp=_cross(grid, ch, ex),
                  pme=_cross(grid, te, 1 - ex), n=int(len(d)))
    return {k: (round(v, -2) if isinstance(v, float) and not np.isnan(v) else v) for k, v in points.items()}, curves
