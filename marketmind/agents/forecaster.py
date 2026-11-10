"""Demand Forecasting Agent (machine learning): 12-month demand forecast with model selection by
rolling-origin backtest, econometric price elasticities and price what-if scenarios."""
from __future__ import annotations

import pandas as pd

from ..core.agent import BaseAgent
from ..core.findings import Finding
from ..ml.forecasting import DemandForecaster, add_intervals, make_panel
from ..ml.pricing import estimate_elasticities, price_scenarios
from .common import idr, pct, windows

MODEL_NAMES = {"gradient_boosting": "gradient boosting", "seasonal_naive": "seasonal naive",
               "seasonal_naive_drift": "seasonal naive with drift", "ensemble": "gradient boosting + drift ensemble"}


class DemandForecastingAgent(BaseAgent):
    name = "Demand Forecasting Agent"
    role = "Forecasting and pricing economist. Builds ML demand forecasts and measures price sensitivity."
    goal = "Quantify the 12-month outlook for the market and the client, and how price moves change volume and revenue."
    ml_capability = ("Machine learning: global direct multi-horizon gradient boosting (HistGradientBoosting) with "
                     "rolling-origin backtesting and model selection; fixed-effects log-log price elasticity model")

    def register_tools(self):
        self.tool("build_monthly_panel", make_panel, "aggregate sales to brand x category x channel monthly series + calendar")
        self.tool("estimate_price_elasticity", estimate_elasticities, "fixed-effects log-log demand regression per brand")
        self.tool("backtest_models", self._backtest, "rolling-origin backtest of 4 candidate models")
        self.tool("forecast_demand", self._forecast, "12-month forecast with the winning model + 80% intervals")
        self.tool("simulate_price_scenarios", price_scenarios, "volume / revenue / profit impact of price changes")

    def execute(self) -> str:
        data = self.bb.require("datasets")
        plan = self.bb.require("plan")
        self.client = plan["client"]
        self.horizon = int(plan.get("horizon_months", 12))
        sales = data["sales"]
        panel = self.use("build_monthly_panel", sales)
        el, el_info = self.use("estimate_price_elasticity", panel)
        bt = self.use("backtest_models", panel)
        self.think(f"Backtest winner: {MODEL_NAMES[bt['best']]} (series WAPE {bt['metrics'][bt['best']]['series_wape']:.3f}).")
        fut = self.use("forecast_demand", panel, bt["best"])
        t = self._tables(panel, fut, bt, el)
        my_el = float(el.set_index("brand").loc[self.client, "elasticity"])
        base_rev = float(t["forecast_summary_brand"].set_index("brand").loc[self.client, "revenue_next12"])
        t["price_scenarios"] = self.use("simulate_price_scenarios", my_el, base_rev)
        t["elasticities"] = el
        self.put("forecast.tables", t, "Forecasts, backtests, elasticities and price scenarios")
        self.put("forecast.model_card", dict(
            model=MODEL_NAMES[bt["best"]], model_key=bt["best"], candidates=list(MODEL_NAMES.values()), metrics=bt["metrics"],
            backtest_window=bt["backtest_window"], folds=3, horizon=self.horizon, sigma=bt["sigma"],
            features=list(bt["importance"]["label"]), elasticity_model=el_info), "Forecast model card")
        self._publish_findings(t, bt, el, my_el)
        return f"Forecast with {MODEL_NAMES[bt['best']]}; {self.client} elasticity {my_el:.2f}"

    # ------------------------------------------------------------------ tools
    def _backtest(self, panel: pd.DataFrame) -> dict:
        self.fc = DemandForecaster(horizon=self.horizon, backtest_months=6)
        return self.fc.backtest(panel, self.client)

    def _forecast(self, panel: pd.DataFrame, method: str) -> pd.DataFrame:
        return self.fc.forecast(panel, method=method)

    def _tables(self, panel: pd.DataFrame, fut: pd.DataFrame, bt: dict, el: pd.DataFrame) -> dict:
        sig = bt["sigma"]
        last, l12, _ = windows(panel["month"])
        hist = panel[panel["month"] >= l12]
        sb = pd.DataFrame({"revenue_last12": hist.groupby("brand")["revenue"].sum(),
                           "revenue_next12": fut.groupby("brand")["revenue"].sum(),
                           "units_last12": hist.groupby("brand")["units"].sum(),
                           "units_next12": fut.groupby("brand")["units"].sum()})
        sb["revenue_growth"] = sb["revenue_next12"] / sb["revenue_last12"] - 1
        sb["units_growth"] = sb["units_next12"] / sb["units_last12"] - 1
        sb["share_next12"] = sb["revenue_next12"] / sb["revenue_next12"].sum()
        sb["share_last12"] = sb["revenue_last12"] / sb["revenue_last12"].sum()
        sc = pd.DataFrame({"revenue_last12": hist.groupby("category")["revenue"].sum(),
                           "revenue_next12": fut.groupby("category")["revenue"].sum()})
        sc["revenue_growth"] = sc["revenue_next12"] / sc["revenue_last12"] - 1
        mine_h, mine_f = hist[hist["brand"] == self.client], fut[fut["brand"] == self.client]
        cc = pd.DataFrame({"revenue_last12": mine_h.groupby("category")["revenue"].sum(),
                           "revenue_next12": mine_f.groupby("category")["revenue"].sum()})
        cc["revenue_growth"] = cc["revenue_next12"] / cc["revenue_last12"] - 1

        def outlook(h: pd.DataFrame, f: pd.DataFrame, sigma: float) -> pd.DataFrame:
            a = h.groupby("month")[["units", "revenue"]].sum().reset_index().assign(type="actual")
            b = add_intervals(f.groupby(["month", "horizon"])[["units", "revenue"]].sum().reset_index(), sigma).assign(type="forecast")
            return pd.concat([a, b], ignore_index=True)

        brand_month = add_intervals(fut.groupby(["month", "brand", "horizon"])[["units", "revenue"]].sum().reset_index(), sig["brand"])
        hist_brand = panel.groupby(["month", "brand"])[["units", "revenue"]].sum().reset_index()
        return {
            "forecast_summary_brand": sb.reset_index().rename(columns={"index": "brand"}).sort_values("revenue_next12", ascending=False),
            "forecast_summary_category": sc.reset_index().rename(columns={"index": "category"}).sort_values("revenue_growth", ascending=False),
            "client_category_outlook": cc.reset_index().rename(columns={"index": "category"}).sort_values("revenue_growth", ascending=False),
            "market_outlook": outlook(panel, fut, sig["market"]),
            "client_outlook": outlook(panel[panel["brand"] == self.client], mine_f, sig["brand"]),
            "brand_forecast_monthly": brand_month, "brand_history_monthly": hist_brand,
            "forecast_series": fut, "backtest_metrics": pd.DataFrame(bt["metrics"]).T.reset_index().rename(columns={"index": "model"}),
            "backtest_folds": bt["folds"], "backtest_detail": bt["detail"], "feature_importance": bt["importance"],
        }

    # ------------------------------------------------------------------ findings
    def _publish_findings(self, t: dict, bt: dict, el: pd.DataFrame, my_el: float) -> None:
        c = self.client
        sb = t["forecast_summary_brand"].set_index("brand")
        mo = t["market_outlook"]
        f = mo[mo["type"] == "forecast"]
        tot_now, tot_next = sb["revenue_last12"].sum(), sb["revenue_next12"].sum()
        g_mkt = tot_next / tot_now - 1
        self.publish(Finding(
            id="FCT-01", agent=self.name, area="forecast", title="Market outlook",
            statement=(f"Tracked-panel revenue is forecast to grow {pct(g_mkt)} over the next {self.horizon} months to "
                       f"{idr(tot_next)} (80% interval for the final month: {idr(f['revenue_lo'].iloc[-1])}-"
                       f"{idr(f['revenue_hi'].iloc[-1])})."),
            metrics=dict(growth=round(g_mkt, 4), revenue_next12_idr=round(tot_next), revenue_last12_idr=round(tot_now),
                         final_month_lo_idr=round(f["revenue_lo"].iloc[-1]), final_month_hi_idr=round(f["revenue_hi"].iloc[-1])),
            evidence=["market_sales_panel.csv", "forecast model"], impact=4, confidence=0.7, swot="O", tags=["outlook"]))
        me = sb.loc[c]
        self.publish(Finding(
            id="FCT-02", agent=self.name, area="forecast", title=f"{c} baseline outlook",
            statement=(f"On current plans, {c}'s revenue is forecast at {idr(me['revenue_next12'])} over the next "
                       f"{self.horizon} months ({pct(me['revenue_growth'])}), moving its panel share from "
                       f"{pct(me['share_last12'], sign=False)} to {pct(me['share_next12'], sign=False)}."),
            metrics=dict(revenue_next12_idr=round(me["revenue_next12"]), growth=round(me["revenue_growth"], 4),
                         share_last12=round(me["share_last12"], 4), share_next12=round(me["share_next12"], 4)),
            evidence=["market_sales_panel.csv", "forecast model"], impact=4, confidence=0.7,
            swot="S" if me["revenue_growth"] > g_mkt else "W", tags=["outlook"]))
        sc = t["forecast_summary_category"].reset_index(drop=True)
        self.publish(Finding(
            id="FCT-03", agent=self.name, area="forecast", title="Category outlook",
            statement=(f"{sc.iloc[0]['category']} ({pct(sc.iloc[0]['revenue_growth'])}) and {sc.iloc[1]['category']} "
                       f"({pct(sc.iloc[1]['revenue_growth'])}) lead forecast growth; {sc.iloc[-1]['category']} trails "
                       f"({pct(sc.iloc[-1]['revenue_growth'])})."),
            metrics=dict(top_category=sc.iloc[0]["category"], top_growth=round(sc.iloc[0]["revenue_growth"], 4),
                         second_category=sc.iloc[1]["category"], second_growth=round(sc.iloc[1]["revenue_growth"], 4),
                         last_category=sc.iloc[-1]["category"], last_growth=round(sc.iloc[-1]["revenue_growth"], 4)),
            evidence=["forecast model"], impact=3, confidence=0.7, swot="O", tags=["outlook", "category"]))
        e = el.set_index("brand")
        sc5 = t["price_scenarios"].set_index("price_change_pct").loc[5.0]
        self.publish(Finding(
            id="FCT-04", agent=self.name, area="pricing", title=f"{c} price elasticity",
            statement=(f"{c}'s demand is {'price-elastic' if my_el < -1 else 'price-inelastic'} (elasticity {my_el:.2f}, "
                       f"95% CI {e.loc[c, 'ci_low']:.2f} to {e.loc[c, 'ci_high']:.2f}): a 5% price rise would change volume by "
                       f"{sc5['volume_change_pct']:+.1f}% and revenue by {sc5['revenue_change_pct']:+.1f}%. Across brands, "
                       f"elasticities range from {e['elasticity'].max():.2f} ({e['elasticity'].idxmax()}) to "
                       f"{e['elasticity'].min():.2f} ({e['elasticity'].idxmin()})."),
            metrics=dict(elasticity=round(my_el, 3), ci_low=float(e.loc[c, "ci_low"]), ci_high=float(e.loc[c, "ci_high"]),
                         volume_change_5pct=float(sc5["volume_change_pct"]), revenue_change_5pct=float(sc5["revenue_change_pct"]),
                         least_elastic=e["elasticity"].idxmax(), least_elastic_value=float(e["elasticity"].max()),
                         most_elastic=e["elasticity"].idxmin(), most_elastic_value=float(e["elasticity"].min())),
            evidence=["market_sales_panel.csv (fixed-effects log-log regression)"], impact=4, confidence=0.8,
            swot="W" if my_el < -1 else "S", tags=["price"]))
        m = bt["metrics"]
        best = bt["best"]
        imp = bt["importance"].head(3)["label"].str.lower().tolist()
        self.publish(Finding(
            id="FCT-05", agent=self.name, area="forecast", title="Forecast model quality",
            statement=(f"Model selection by rolling-origin backtest (3 x 6-month folds) picked the {MODEL_NAMES[best]}: "
                       f"WAPE {pct(m[best]['series_wape'], sign=False)} at brand-category-channel level versus "
                       f"{pct(m['seasonal_naive']['series_wape'], sign=False)} for a seasonal-naive benchmark; "
                       f"the strongest drivers are {', '.join(imp)}."),
            metrics=dict(model=MODEL_NAMES[best], wape=m[best]["series_wape"], naive_wape=m["seasonal_naive"]["series_wape"],
                         market_mape=m[best]["market_mape"]),
            evidence=["backtest"], impact=2, confidence=0.9, tags=["methodology", "model"]))
