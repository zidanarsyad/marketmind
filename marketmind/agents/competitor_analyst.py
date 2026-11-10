"""Competitive Intelligence Agent: share, momentum, channel/region presence, price positioning,
share of voice, threat scoring and white-space (unmet need vs. product supply) detection."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core.agent import BaseAgent
from ..core.findings import Finding
from .common import cosine, growth, idr, minmax, pct, pp, windows

WHITE_SPACES = [
    dict(name="Fragrance-free ceramide/barrier moisturizer, Rp60-120k", category="Moisturizer", pattern="ceramide|barrier",
         tier=(60000, 120000), fragrance_free=True, topics=["skin barrier", "ceramide"],
         need=("imp_fragrance_free", ">=", 4), need_label="rate fragrance-free as important"),
    dict(name="Peptide anti-ageing serum, Rp60-120k", category="Serum", pattern="peptide", tier=(60000, 120000),
         fragrance_free=None, topics=["peptide"], need=("primary_concern", "==", "Fine lines & aging"),
         need_label="name ageing as their main concern"),
    dict(name="Mineral sunscreen, Rp60-120k", category="Sunscreen", pattern="mineral|zinc", tier=(60000, 120000),
         fragrance_free=None, topics=["sunscreen"], need=("skin_type", "==", "sensitive"), need_label="have sensitive skin"),
    dict(name="Refill / low-waste formats", category=None, pattern="refill", tier=None, fragrance_free=None,
         topics=["refill"], need=("imp_sustainability", ">=", 4), need_label="rate sustainability as important"),
    dict(name="Budget acne serum, under Rp60k", category="Serum", pattern="salicylic|acne|bha", tier=(0, 60000),
         fragrance_free=None, topics=["salicylic acid"], need=("primary_concern", "==", "Acne & breakouts"),
         need_label="name acne as their main concern"),
]


class CompetitiveIntelligenceAgent(BaseAgent):
    name = "Competitive Intelligence Agent"
    role = "Competitive analyst. Benchmarks the client against rivals and finds gaps competitors leave open."
    goal = "Show where the client wins, where it is exposed, who the main threat is and which spaces are unclaimed."

    def register_tools(self):
        self.tool("compute_market_share", self._shares, "value/volume share, momentum and share trend by brand")
        self.tool("channel_region_index", self._indices, "client over/under-indexing by channel, category and region")
        self.tool("price_value_map", self._positioning, "price index vs rating/sentiment per brand")
        self.tool("share_of_voice", self._sov, "brand share of social conversation by platform")
        self.tool("score_threats", self._threats, "multi-factor competitive threat index")
        self.tool("find_white_space", self._white_space, "match consumer needs and trend momentum against SKU supply")
        self.tool("estimate_stockout_loss", self._stockouts, "estimate sales lost to stock-outs")

    def execute(self) -> str:
        data = self.bb.require("datasets")
        self.client = self.bb.require("plan")["client"]
        sales = data["sales"]
        self.last, self.l12, self.p12 = windows(sales["month"])
        t = {}
        t.update(self.use("compute_market_share", sales))
        t.update(self.use("channel_region_index", sales))
        t["price_positioning"] = self.use("price_value_map", sales, data.get("reviews"), data.get("catalog"))
        if "social" in data:
            t["share_of_voice"] = self.use("share_of_voice", data["social"])
        t["threats"] = self.use("score_threats", sales, t)
        if "catalog" in data:
            t["white_space"] = self.use("find_white_space", data["catalog"], data.get("survey"), data.get("social"))
        t["stockout_loss"] = self.use("estimate_stockout_loss", sales)
        self.put("competition.tables", t, "Competitive benchmarking tables")
        self._publish_findings(t)
        return f"Benchmarked {t['brand_share'].shape[0]} brands; top threat: {t['threats'].iloc[0]['brand']}"

    # ------------------------------------------------------------------ tools
    def _shares(self, sales: pd.DataFrame) -> dict:
        cur = sales[sales["month"] >= self.l12]
        prev = sales[(sales["month"] >= self.p12) & (sales["month"] < self.l12)]
        b = pd.DataFrame({"revenue_l12": cur.groupby("brand")["revenue_idr"].sum(),
                          "revenue_p12": prev.groupby("brand")["revenue_idr"].sum(),
                          "units_l12": cur.groupby("brand")["units"].sum()})
        b["share_l12"] = b["revenue_l12"] / b["revenue_l12"].sum()
        b["share_p12"] = b["revenue_p12"] / b["revenue_p12"].sum()
        b["share_change_pp"] = b["share_l12"] - b["share_p12"]
        b["growth"] = b["revenue_l12"] / b["revenue_p12"] - 1
        b["volume_share_l12"] = b["units_l12"] / b["units_l12"].sum()
        b = b.sort_values("revenue_l12", ascending=False)
        b["rank"] = np.arange(1, len(b) + 1)
        m = sales.groupby(["month", "brand"])["revenue_idr"].sum().reset_index()
        m["share"] = m["revenue_idr"] / m.groupby("month")["revenue_idr"].transform("sum")
        self._panel_growth = growth(cur["revenue_idr"].sum(), prev["revenue_idr"].sum())
        return {"brand_share": b.reset_index(), "share_trend": m}

    def _indices(self, sales: pd.DataFrame) -> dict:
        cur = sales[sales["month"] >= self.l12]
        prev = sales[(sales["month"] >= self.p12) & (sales["month"] < self.l12)]
        out = {}
        for dim in ("channel", "category", "region"):
            mk = cur.groupby(dim)["revenue_idr"].sum()
            cl = cur[cur["brand"] == self.client].groupby(dim)["revenue_idr"].sum()
            mg = mk / prev.groupby(dim)["revenue_idr"].sum() - 1
            t = pd.DataFrame({"market_mix": mk / mk.sum(), "client_mix": cl / cl.sum(),
                              "client_share_in_segment": cl / mk, "market_growth": mg})
            t["index"] = t["client_mix"] / t["market_mix"]
            out[f"{dim}_index"] = t.reset_index().sort_values("index")
        return out

    def _positioning(self, sales: pd.DataFrame, reviews: pd.DataFrame | None, catalog: pd.DataFrame | None) -> pd.DataFrame:
        cur = sales[sales["month"] >= self.l12]
        cat_price = cur.groupby("category").apply(lambda g: g["revenue_idr"].sum() / g["units"].sum(), include_groups=False)
        bc = cur.groupby(["brand", "category"]).agg(rev=("revenue_idr", "sum"), units=("units", "sum")).reset_index()
        bc["price_ratio"] = (bc["rev"] / bc["units"]) / bc["category"].map(cat_price)
        pidx = bc.groupby("brand").apply(lambda g: np.average(g["price_ratio"], weights=g["rev"]), include_groups=False)
        t = pd.DataFrame({"price_index": pidx, "revenue_l12": cur.groupby("brand")["revenue_idr"].sum()})
        if reviews is not None:
            rv = reviews[reviews["month"] >= self.l12]
            t["avg_rating"] = rv.groupby("brand")["rating"].mean()
            t["reviews_l12"] = rv.groupby("brand").size()
            t["net_rating_sentiment"] = rv.groupby("brand")["rating"].apply(lambda s: (s >= 4).mean() - (s <= 2).mean())
        if catalog is not None:
            t["skus"] = catalog.groupby("brand").size()
            t["fragrance_free_skus"] = catalog.groupby("brand")["fragrance_free"].sum()
        return t.reset_index().rename(columns={"index": "brand"}).sort_values("price_index")

    def _sov(self, social: pd.DataFrame) -> pd.DataFrame:
        s = social[(social["month"] >= self.l12) & (social["brand_mentioned"] != "")]
        allp = s.groupby("brand_mentioned").agg(mentions=("post_id", "count"), engagement=("engagement", "sum"))
        allp["sov"] = allp["mentions"] / allp["mentions"].sum()
        allp["engagement_share"] = allp["engagement"] / allp["engagement"].sum()
        tt = s[s["platform"] == "TikTok"].groupby("brand_mentioned").size()
        allp["tiktok_sov"] = tt / tt.sum()
        return allp.reset_index().rename(columns={"brand_mentioned": "brand"}).sort_values("sov", ascending=False)

    def _threats(self, sales: pd.DataFrame, t: dict) -> pd.DataFrame:
        cur = sales[sales["month"] >= self.l12]
        bs = t["brand_share"].set_index("brand")
        pos = t["price_positioning"].set_index("brand")
        cats, chans = sorted(cur["category"].unique()), sorted(cur["channel"].unique())
        def mix(b, dim, keys):
            return cur[cur["brand"] == b].groupby(dim)["revenue_idr"].sum().reindex(keys, fill_value=0).to_numpy()

        rows = []
        for b in bs.index:
            if b == self.client:
                continue
            rows.append(dict(
                brand=b, growth=bs.loc[b, "growth"], share_l12=bs.loc[b, "share_l12"], share_gain_pp=bs.loc[b, "share_change_pp"],
                price_proximity=1 - min(abs(np.log(pos.loc[b, "price_index"] / pos.loc[self.client, "price_index"])), 1),
                category_overlap=cosine(mix(b, "category", cats), mix(self.client, "category", cats)),
                channel_overlap=cosine(mix(b, "channel", chans), mix(self.client, "channel", chans)),
                social_sov=float(t["share_of_voice"].set_index("brand")["sov"].get(b, 0)) if "share_of_voice" in t else 0.0,
            ))
        th = pd.DataFrame(rows)
        weights = dict(growth=0.25, share_l12=0.20, share_gain_pp=0.15, price_proximity=0.15, category_overlap=0.10,
                       channel_overlap=0.05, social_sov=0.10)
        th["threat_index"] = sum(w * minmax(th[c]) for c, w in weights.items()).round(3)
        th = th.sort_values("threat_index", ascending=False).reset_index(drop=True)
        th["rank"] = np.arange(1, len(th) + 1)
        return th

    def _white_space(self, catalog: pd.DataFrame, survey: pd.DataFrame | None, social: pd.DataFrame | None) -> pd.DataFrame:
        topic_change, topic_sov = {}, {}
        if social is not None:
            ex = social.assign(topic=social["topics"].str.split(";")).explode("topic")
            cur = ex[ex["month"] >= self.l12]["topic"].value_counts(normalize=True)
            prev = ex[(ex["month"] >= self.p12) & (ex["month"] < self.l12)]["topic"].value_counts(normalize=True)
            topic_change, topic_sov = (cur / prev - 1).to_dict(), cur.to_dict()
        text = (catalog["product_name"] + " " + catalog["key_ingredient"]).str.lower()
        rows = []
        for sp in WHITE_SPACES:
            mask = text.str.contains(sp["pattern"])
            if sp["category"]:
                mask &= catalog["category"] == sp["category"]
            if sp["tier"]:
                mask &= catalog["price_idr"].between(*sp["tier"])
            if sp["fragrance_free"] is not None:
                mask &= catalog["fragrance_free"] == sp["fragrance_free"]
            need_share = np.nan
            if survey is not None:
                col, op, val = sp["need"]
                need_share = float((survey[col] >= val).mean() if op == ">=" else (survey[col] == val).mean())
            momentum = float(np.nanmean([topic_change.get(tp, np.nan) for tp in sp["topics"]])) if topic_change else 0.0
            attention = float(np.mean([topic_sov.get(tp, 0.0) for tp in sp["topics"]])) if topic_sov else 0.05
            supply = int(mask.sum())
            rows.append(dict(space=sp["name"], supply_skus=supply, client_present=bool((mask & (catalog["brand"] == self.client)).any()),
                             competitors_present=", ".join(sorted(catalog.loc[mask, "brand"].unique())) or "none",
                             consumer_need_share=round(need_share, 4), need_label=sp["need_label"],
                             trend_momentum=round(momentum, 4), topic_share_of_voice=round(attention, 4),
                             topics=", ".join(sp["topics"]),
                             opportunity_score=(need_share if not np.isnan(need_share) else 0.2) * attention
                             * (1 + max(momentum, 0)) / (1 + supply)))
        ws = pd.DataFrame(rows)
        ws["opportunity_score"] = (100 * ws["opportunity_score"] / ws["opportunity_score"].max()).round(1)
        return ws.sort_values("opportunity_score", ascending=False).reset_index(drop=True)

    def _stockouts(self, sales: pd.DataFrame) -> pd.DataFrame:
        d = sales[(sales["month"] >= self.l12) & (sales["stockout_days"] > 0)].copy()
        days = d["month"].dt.days_in_month
        d["lost_units"] = d["units"] * d["stockout_days"] / (days - d["stockout_days"]).clip(lower=1)
        d["lost_revenue"] = d["lost_units"] * d["avg_selling_price_idr"]
        return d.groupby(["brand", "channel", "month"]).agg(stockout_days=("stockout_days", "max"),
                                                             lost_units=("lost_units", "sum"),
                                                             lost_revenue=("lost_revenue", "sum")).reset_index() \
                .sort_values("lost_revenue", ascending=False)

    # ------------------------------------------------------------------ findings
    def _publish_findings(self, t: dict) -> None:
        c = self.client
        bs = t["brand_share"].set_index("brand")
        me = bs.loc[c]
        outgrowing = me["growth"] > self._panel_growth
        self.publish(Finding(
            id="CMP-01", agent=self.name, area="competition", title=f"{c} market position",
            statement=(f"{c} holds {pct(me['share_l12'], sign=False)} of tracked-panel value (#{int(me['rank'])} of {len(bs)}), "
                       f"with revenue of {idr(me['revenue_l12'])} in the last 12 months, growing {pct(me['growth'])} versus "
                       f"{pct(self._panel_growth)} for the panel ({pp(me['share_change_pp'])} share)."),
            metrics=dict(share=round(me["share_l12"], 4), rank=int(me["rank"]), revenue_l12_idr=round(me["revenue_l12"]),
                         growth=round(me["growth"], 4), panel_growth=round(self._panel_growth, 4),
                         share_change_pp=round(me["share_change_pp"], 4)),
            evidence=["market_sales_panel.csv"], impact=4, confidence=0.9, swot="S" if outgrowing else "W",
            tags=["share"]))

        ci = t["channel_index"].set_index("channel")
        fastest = ci["market_growth"].idxmax()
        idx = ci.loc[fastest, "index"]
        if idx < 0.85:
            self.publish(Finding(
                id="CMP-02", agent=self.name, area="competition", title=f"Under-indexed on {fastest}",
                statement=(f"{c} is under-indexed on {fastest}, the fastest-growing channel ({pct(ci.loc[fastest, 'market_growth'])}): "
                           f"it generates {pct(ci.loc[fastest, 'client_mix'], sign=False)} of {c}'s sales versus "
                           f"{pct(ci.loc[fastest, 'market_mix'], sign=False)} for the market (index {idx:.2f})."),
                metrics=dict(channel=fastest, index=round(idx, 3), client_mix=round(ci.loc[fastest, "client_mix"], 4),
                             market_mix=round(ci.loc[fastest, "market_mix"], 4),
                             channel_growth=round(ci.loc[fastest, "market_growth"], 4)),
                evidence=["market_sales_panel.csv"], impact=5, confidence=0.9, swot="W", tags=["channel", "gap"]))
        strongest = ci["index"].idxmax()
        self.publish(Finding(
            id="CMP-03", agent=self.name, area="competition", title=f"Channel stronghold: {strongest}",
            statement=(f"{c}'s strongest channel is {strongest} (index {ci.loc[strongest, 'index']:.2f}, "
                       f"{pct(ci.loc[strongest, 'client_mix'], sign=False)} of its sales)."),
            metrics=dict(channel=strongest, index=round(ci.loc[strongest, "index"], 3),
                         client_mix=round(ci.loc[strongest, "client_mix"], 4)),
            evidence=["market_sales_panel.csv"], impact=2, confidence=0.9, swot="S", tags=["channel"]))

        ri = t["region_index"].set_index("region")
        fast_regions = ri.sort_values("market_growth", ascending=False).head(2)
        weak = fast_regions[fast_regions["index"] < 0.9]
        if len(weak):
            self.publish(Finding(
                id="CMP-04", agent=self.name, area="competition", title="Weak presence in fast-growing regions",
                statement=(f"{c} under-indexes in the fastest-growing regions: "
                           + "; ".join(f"{r} (index {row['index']:.2f}, market {pct(row['market_growth'])})" for r, row in weak.iterrows())
                           + "."),
                metrics={**{f"region_{i + 1}": r for i, r in enumerate(weak.index)},
                         **{f"region_{i + 1}_index": round(row["index"], 3) for i, (_, row) in enumerate(weak.iterrows())},
                         **{f"region_{i + 1}_growth": round(row["market_growth"], 4) for i, (_, row) in enumerate(weak.iterrows())}},
                evidence=["market_sales_panel.csv"], impact=3, confidence=0.8, swot="O", tags=["region", "gap"]))

        th = t["threats"].iloc[0]
        self.publish(Finding(
            id="CMP-05", agent=self.name, area="competition", title=f"Top competitive threat: {th['brand']}",
            statement=(f"{th['brand']} is the most serious competitive threat (threat index {th['threat_index']:.2f}): "
                       f"{pct(th['share_l12'], sign=False)} share, {pct(th['growth'])} growth and "
                       f"{pct(th['social_sov'], sign=False)} of brand social conversation, with "
                       f"{th['category_overlap']:.2f} category overlap with {c}."),
            metrics=dict(brand=th["brand"], threat_index=round(th["threat_index"], 3), share=round(th["share_l12"], 4),
                         growth=round(th["growth"], 4), social_sov=round(th["social_sov"], 4),
                         category_overlap=round(th["category_overlap"], 3),
                         runner_up=t["threats"].iloc[1]["brand"], runner_up_index=round(t["threats"].iloc[1]["threat_index"], 3)),
            evidence=["market_sales_panel.csv", "social_mentions.csv"], impact=4, confidence=0.75, swot="T",
            tags=["threat"]))

        pos = t["price_positioning"].set_index("brand")
        cheapest, dearest = pos["price_index"].idxmin(), pos["price_index"].idxmax()
        rating_txt = (f" and an average rating of {pos.loc[c, 'avg_rating']:.2f} stars (panel best: "
                      f"{pos['avg_rating'].idxmax()} {pos['avg_rating'].max():.2f})") if "avg_rating" in pos else ""
        self.publish(Finding(
            id="CMP-06", agent=self.name, area="competition", title="Price positioning",
            statement=(f"{c} is priced at {pos.loc[c, 'price_index']:.2f}x the category average, between {cheapest} "
                       f"({pos.loc[cheapest, 'price_index']:.2f}x) and {dearest} ({pos.loc[dearest, 'price_index']:.2f}x){rating_txt}."),
            metrics=dict(price_index=round(pos.loc[c, "price_index"], 3), cheapest=cheapest,
                         cheapest_index=round(pos.loc[cheapest, "price_index"], 3), dearest=dearest,
                         dearest_index=round(pos.loc[dearest, "price_index"], 3),
                         avg_rating=round(pos.loc[c, "avg_rating"], 2) if "avg_rating" in pos else None),
            evidence=["market_sales_panel.csv", "product_reviews.csv"], impact=2, confidence=0.85, tags=["price"]))

        if "share_of_voice" in t:
            sov = t["share_of_voice"].set_index("brand")
            if c in sov.index:
                gap = sov.loc[c, "sov"] - me["share_l12"]
                self.publish(Finding(
                    id="CMP-07", agent=self.name, area="competition", title="Share of voice",
                    statement=(f"{c} captures {pct(sov.loc[c, 'sov'], sign=False)} of brand social mentions but only "
                               f"{pct(sov.loc[c, 'tiktok_sov'], sign=False)} on TikTok, versus {pct(me['share_l12'], sign=False)} "
                               f"value share; {sov['tiktok_sov'].idxmax()} dominates TikTok with "
                               f"{pct(sov['tiktok_sov'].max(), sign=False)}."),
                    metrics=dict(sov=round(sov.loc[c, "sov"], 4), tiktok_sov=round(sov.loc[c, "tiktok_sov"], 4),
                                 value_share=round(me["share_l12"], 4), tiktok_leader=sov["tiktok_sov"].idxmax(),
                                 tiktok_leader_sov=round(sov["tiktok_sov"].max(), 4)),
                    evidence=["social_mentions.csv"], impact=3, confidence=0.75, swot="W" if gap < 0 else "S",
                    tags=["social", "channel"]))

        if "white_space" in t:
            ws = t["white_space"].iloc[0]
            self.publish(Finding(
                id="CMP-08", agent=self.name, area="competition", title="White space",
                statement=(f"Biggest white space: {ws['space']} - "
                           + ("no product on the market fits it" if ws["supply_skus"] == 0 else
                              f"only {ws['supply_skus']} SKU(s) fit it ({ws['competitors_present']})")
                           + f", while {pct(ws['consumer_need_share'], 0, sign=False)} of consumers "
                           f"{ws['need_label']} and conversation about {ws['topics']} grew {pct(ws['trend_momentum'], 0)}."),
                metrics=dict(space=ws["space"], supply_skus=int(ws["supply_skus"]), need_share=ws["consumer_need_share"],
                             trend_momentum=ws["trend_momentum"], client_present=bool(ws["client_present"])),
                evidence=["product_catalog.csv", "consumer_survey.csv", "social_mentions.csv"], impact=5, confidence=0.75,
                swot="O", tags=["white space", "concept"]))

        so = t["stockout_loss"]
        mine = so[so["brand"] == c]
        if len(mine) and mine["lost_revenue"].sum() > 0:
            worst = mine.iloc[0]
            self.publish(Finding(
                id="CMP-09", agent=self.name, area="competition", title="Sales lost to stock-outs",
                statement=(f"Stock-outs cost {c} an estimated {idr(mine['lost_revenue'].sum())} "
                           f"({mine['lost_units'].sum():,.0f} units) in the last 12 months; the worst episode was "
                           f"{worst['channel']} in {worst['month']:%b %Y} ({int(worst['stockout_days'])} days out of stock)."),
                metrics=dict(lost_revenue_idr=round(mine["lost_revenue"].sum()), lost_units=round(mine["lost_units"].sum()),
                             worst_channel=worst["channel"], worst_month=f"{worst['month']:%Y-%m}",
                             worst_days=int(worst["stockout_days"])),
                evidence=["market_sales_panel.csv"], impact=3, confidence=0.7, swot="W", tags=["operations"]))
