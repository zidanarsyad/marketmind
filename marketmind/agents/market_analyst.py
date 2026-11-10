"""Market & Trend Analyst: market sizing, growth drivers, seasonality and emerging consumer trends."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core.agent import BaseAgent
from ..core.findings import Finding
from ..ml.calendar_id import calendar_frame
from .common import growth, idr, pct, windows


class MarketTrendAnalystAgent(BaseAgent):
    name = "Market & Trend Analyst"
    finding_prefix = "MKT"
    role = "Market analyst. Sizes the market and explains where growth comes from - categories, channels, regions, seasons and trends."
    goal = "Quantify market attractiveness and the structural shifts the client must ride."

    def register_tools(self):
        self.tool("size_market", self._size_market, "compute market size, CAGR, local-brand and online share trends")
        self.tool("decompose_growth", self._growth_drivers, "last-12-month growth by category, channel and region")
        self.tool("estimate_seasonality", self._seasonality, "seasonal index, Ramadan/Eid and mega-sale uplift")
        self.tool("detect_social_trends", self._social_trends, "share-of-voice momentum of skincare topics")

    def execute(self) -> str:
        data = self.bb.require("datasets")
        sales = data["sales"]
        tables = {}
        tables.update(self.use("size_market", data["market_size"]))
        tables.update(self.use("decompose_growth", sales))
        tables.update(self.use("estimate_seasonality", sales))
        if "social" in data:
            tables.update(self.use("detect_social_trends", data["social"]))
        macro = self.bb.get("external.macro")
        if macro is not None and not macro.empty:
            tables["macro"] = macro
        self.put("market.tables", tables, "Market sizing, growth and trend tables")
        self._publish_findings(tables)
        return f"Produced {len(tables)} market tables and {self._findings} findings"

    # ------------------------------------------------------------------ tools
    def _size_market(self, ms: pd.DataFrame) -> dict:
        by_year = ms.pivot_table(index=["year", "status"], columns="category", values="market_value_idr_bn", aggfunc="sum")
        by_year["total_idr_bn"] = by_year.sum(axis=1)
        by_year = by_year.reset_index()
        shares = ms.groupby("year")[["local_brand_share_pct", "online_share_pct"]].first().reset_index()
        by_year = by_year.merge(shares, on="year")
        actual = by_year[by_year["status"] == "actual"]
        y0, y1 = actual["year"].min(), actual["year"].max()
        t0, t1 = actual.loc[actual["year"] == y0, "total_idr_bn"].iloc[0], actual.loc[actual["year"] == y1, "total_idr_bn"].iloc[0]
        cagr = (t1 / t0) ** (1 / (y1 - y0)) - 1
        cat_cagr = []
        for c in ms["category"].unique():
            s = ms[(ms["category"] == c) & (ms["status"] == "actual")].set_index("year")["market_value_idr_bn"]
            cat_cagr.append(dict(category=c, size_latest_idr_bn=float(s.loc[y1]), cagr=float((s.loc[y1] / s.loc[y0]) ** (1 / (y1 - y0)) - 1)))
        est = by_year[by_year["status"] == "estimate"]
        self._sizing = dict(first_year=int(y0), last_year=int(y1), size_last_bn=float(t1), cagr=float(cagr),
                            local_share=float(actual["local_brand_share_pct"].iloc[-1]),
                            local_share_first=float(actual["local_brand_share_pct"].iloc[0]),
                            online_share=float(actual["online_share_pct"].iloc[-1]),
                            estimate_year=int(est["year"].iloc[0]) if len(est) else None,
                            estimate_bn=float(est["total_idr_bn"].iloc[0]) if len(est) else None)
        return {"market_size_by_year": by_year, "category_cagr": pd.DataFrame(cat_cagr)}

    def _growth_drivers(self, sales: pd.DataFrame) -> dict:
        last, l12, p12 = windows(sales["month"])
        cur = sales[sales["month"] >= l12]
        prev = sales[(sales["month"] >= p12) & (sales["month"] < l12)]
        self._window = (l12, last)
        out = {}
        for dim in ("category", "channel", "region"):
            a = cur.groupby(dim)["revenue_idr"].sum()
            b = prev.groupby(dim)["revenue_idr"].sum()
            t = pd.DataFrame({"revenue_l12": a, "revenue_p12": b}).fillna(0)
            t["growth"] = t["revenue_l12"] / t["revenue_p12"] - 1
            t["share_l12"] = t["revenue_l12"] / t["revenue_l12"].sum()
            t["share_p12"] = t["revenue_p12"] / t["revenue_p12"].sum()
            t["share_change_pp"] = t["share_l12"] - t["share_p12"]
            out[f"{dim}_growth"] = t.reset_index().sort_values("growth", ascending=False)
        yearly = sales.assign(year=sales["month"].dt.year).pivot_table(index="year", columns="channel", values="revenue_idr", aggfunc="sum")
        out["channel_mix"] = (yearly.div(yearly.sum(axis=1), axis=0)).reset_index()
        monthly = sales.groupby("month")[["revenue_idr", "units"]].sum().reset_index()
        monthly["yoy_growth"] = monthly["revenue_idr"].pct_change(12)
        out["monthly_market"] = monthly
        tot_cur, tot_prev = cur["revenue_idr"].sum(), prev["revenue_idr"].sum()
        self._panel = dict(revenue_l12=float(tot_cur), growth=growth(tot_cur, tot_prev),
                           first_month=sales["month"].min(), last_month=last)
        return out

    def _seasonality(self, sales: pd.DataFrame) -> dict:
        m = sales.groupby("month")["revenue_idr"].sum()
        trend = m.rolling(12, center=True, min_periods=12).mean()
        trend = trend.fillna(m.rolling(12, min_periods=6).mean()).bfill().ffill()
        ratio = (m / trend).rename("ratio").reset_index()
        cal = calendar_frame(ratio["month"])
        ratio = ratio.merge(cal, on="month")
        index = ratio.groupby("month_of_year")["ratio"].mean().reset_index().rename(columns={"ratio": "seasonal_index"})
        ram = ratio[ratio["pre_eid_share"] > 0.2]["ratio"].mean()
        non = ratio[(ratio["ramadan_share"] == 0) & (ratio["post_eid_share"] == 0) & (~ratio["month_of_year"].isin([11, 12, 1]))]["ratio"].mean()
        on = sales[sales["channel"] != "Offline Retail"].groupby("month")["revenue_idr"].sum()
        on_ratio = (on / on.rolling(12, center=True, min_periods=12).mean()).dropna()
        mega = on_ratio[on_ratio.index.month.isin([11, 12])].mean()
        base = on_ratio[on_ratio.index.month.isin([5, 6, 7, 8])].mean()
        self._season = dict(ramadan_uplift=float(ram / non - 1), mega_sale_uplift=float(mega / base - 1),
                            peak_month=int(index.loc[index["seasonal_index"].idxmax(), "month_of_year"]))
        return {"seasonal_index": index, "seasonality_ratio": ratio[["month", "ratio", "ramadan_share", "pre_eid_share"]]}

    def _social_trends(self, social: pd.DataFrame) -> dict:
        last, l12, p12 = windows(social["month"])
        ex = social.assign(topic=social["topics"].str.split(";")).explode("topic")
        cur = ex[ex["month"] >= l12]["topic"].value_counts(normalize=True)
        prev = ex[(ex["month"] >= p12) & (ex["month"] < l12)]["topic"].value_counts(normalize=True)
        t = pd.DataFrame({"sov_l12": cur, "sov_p12": prev}).fillna(0)
        t["sov_change"] = t["sov_l12"] / t["sov_p12"].replace(0, np.nan) - 1
        t["mentions_l12"] = ex[ex["month"] >= l12]["topic"].value_counts()
        t["status"] = np.select(
            [(t["sov_p12"] < 0.03) & (t["sov_change"] > 0.5), t["sov_change"] > 0.10, t["sov_change"] < -0.10],
            ["emerging", "rising", "declining"], "stable")
        t = t.reset_index().rename(columns={"index": "topic"}).sort_values("sov_change", ascending=False)
        monthly = ex.groupby(["month", "topic"]).size().rename("mentions").reset_index()
        return {"topic_trends": t, "topic_monthly": monthly}

    # ------------------------------------------------------------------ findings
    def _publish_findings(self, t: dict) -> None:
        s = self._sizing
        self.publish(Finding(
            id="MKT-01", agent=self.name, area="market", title="Market size and growth",
            statement=(f"Indonesia's facial-skincare market reached {idr(s['size_last_bn'] * 1e9)} in {s['last_year']}, "
                       f"growing at a {pct(s['cagr'], sign=False)} CAGR since {s['first_year']}; local brands now hold "
                       f"{s['local_share']:.0f}% of value (up from {s['local_share_first']:.0f}%) and online channels "
                       f"{s['online_share']:.0f}%."),
            metrics=dict(market_size_idr_bn=round(s["size_last_bn"], 1), cagr=round(s["cagr"], 4), year=s["last_year"],
                         local_share_pct=s["local_share"], online_share_pct=s["online_share"],
                         estimate_next_year_idr_bn=s["estimate_bn"]),
            evidence=["market_size.csv"], impact=4, confidence=0.8, swot="O", tags=["market size"]))

        cat = t["category_growth"].reset_index(drop=True)
        top, second, last = cat.iloc[0], cat.iloc[1], cat.iloc[-1]
        self.publish(Finding(
            id="MKT-02", agent=self.name, area="market", title="Fastest-growing categories",
            statement=(f"{top['category']} is the fastest-growing category in the tracked panel ({pct(top['growth'])} "
                       f"last-12-month revenue growth), followed by {second['category']} ({pct(second['growth'])}); "
                       f"{last['category']} is the slowest ({pct(last['growth'])})."),
            metrics=dict(top_category=top["category"], top_growth=round(top["growth"], 4),
                         second_category=second["category"], second_growth=round(second["growth"], 4),
                         slowest_category=last["category"], slowest_growth=round(last["growth"], 4)),
            evidence=["market_sales_panel.csv"], impact=4, confidence=0.85, swot="O", tags=["category"]))

        ch = t["channel_growth"].set_index("channel")
        fastest = ch["growth"].idxmax()
        mix = t["channel_mix"].set_index("year")
        first_share = mix[fastest].iloc[0]
        laggard = ch["growth"].idxmin()
        self.publish(Finding(
            id="MKT-03", agent=self.name, area="market", title="Channel shift to social commerce",
            statement=(f"{fastest} is the fastest-growing channel ({pct(ch.loc[fastest, 'growth'])} last 12 months) and now "
                       f"carries {pct(ch.loc[fastest, 'share_l12'], sign=False)} of tracked sales, up from "
                       f"{pct(first_share, sign=False)} in {mix.index[0]}; {laggard} is losing ground "
                       f"({pct(ch.loc[laggard, 'growth'])})."),
            metrics=dict(fastest_channel=fastest, fastest_channel_growth=round(ch.loc[fastest, "growth"], 4),
                         fastest_channel_share=round(ch.loc[fastest, "share_l12"], 4), share_first_year=round(first_share, 4),
                         laggard_channel=laggard, laggard_growth=round(ch.loc[laggard, "growth"], 4)),
            evidence=["market_sales_panel.csv"], impact=5, confidence=0.9, swot="O", tags=["channel"]))

        rg = t["region_growth"].reset_index(drop=True)
        r1, r2, rl = rg.iloc[0], rg.iloc[1], rg.iloc[-1]
        self.publish(Finding(
            id="MKT-04", agent=self.name, area="market", title="Regional growth outside Java's core",
            statement=(f"Growth is strongest in {r1['region']} ({pct(r1['growth'])}) and {r2['region']} ({pct(r2['growth'])}), "
                       f"versus {pct(rl['growth'])} in {rl['region']}."),
            metrics=dict(top_region=r1["region"], top_region_growth=round(r1["growth"], 4), second_region=r2["region"],
                         second_region_growth=round(r2["growth"], 4), slowest_region=rl["region"],
                         slowest_region_growth=round(rl["growth"], 4)),
            evidence=["market_sales_panel.csv"], impact=3, confidence=0.8, swot="O", tags=["region"]))

        se = self._season
        self.publish(Finding(
            id="MKT-05", agent=self.name, area="market", title="Seasonality: Ramadan and mega-sales",
            statement=(f"Pre-Eid months run {pct(se['ramadan_uplift'])} above trend versus ordinary months, and the 11.11/12.12 "
                       f"mega-sales lift online sales {pct(se['mega_sale_uplift'])} above the mid-year base; campaigns and "
                       f"stock must be planned around both peaks."),
            metrics=dict(ramadan_uplift=round(se["ramadan_uplift"], 4), mega_sale_uplift=round(se["mega_sale_uplift"], 4)),
            evidence=["market_sales_panel.csv", "Indonesian Ramadan calendar"], impact=3, confidence=0.8, swot="O",
            tags=["seasonality"]))

        if "topic_trends" in t:
            tt = t["topic_trends"]
            up = tt[tt["status"].isin(["emerging", "rising"])].head(4)
            down = tt[tt["status"] == "declining"].sort_values("sov_change").head(3)
            if len(up):
                self.publish(Finding(
                    id="MKT-06", agent=self.name, area="market", title="Rising consumer conversation topics",
                    statement=("Share of social conversation (last 12 months vs prior year) is shifting towards "
                               + ", ".join(f"{r.topic} ({pct(r.sov_change, 0)})" for r in up.itertuples())
                               + (("; fading: " + ", ".join(f"{r.topic} ({pct(r.sov_change, 0)})" for r in down.itertuples()))
                                  if len(down) else "") + "."),
                    metrics={**{f"rising_{i + 1}": r.topic for i, r in enumerate(up.itertuples())},
                             **{f"rising_{i + 1}_change": round(r.sov_change, 3) for i, r in enumerate(up.itertuples())},
                             **{f"declining_{i + 1}": r.topic for i, r in enumerate(down.itertuples())},
                             **{f"declining_{i + 1}_change": round(r.sov_change, 3) for i, r in enumerate(down.itertuples())}},
                    evidence=["social_mentions.csv"], impact=4, confidence=0.75, swot="O", tags=["trend"]))
