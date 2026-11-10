"""Consumer Segmentation Agent (machine learning): segments the survey sample, profiles personas,
evaluates the new-product concept per segment and runs Van Westendorp pricing research."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core.agent import BaseAgent
from ..core.findings import Finding
from ..ml import segmentation as seg
from ..ml.pricing import van_westendorp
from .common import client_key, idr, minmax, pct

PRICE_POINTS = [49900, 59900, 69900, 79900, 89900, 99900, 109900, 119900, 129900, 149900, 179900, 199900]
VW_COLS = ("vw_too_cheap_idr", "vw_cheap_idr", "vw_expensive_idr", "vw_too_expensive_idr")


class SegmentationAgent(BaseAgent):
    name = "Consumer Segmentation Agent"
    role = "Quantitative consumer researcher. Segments consumers with machine learning and tests the concept and its price."
    goal = "Find actionable segments, choose the target for the new concept and recommend a launch price."
    ml_capability = ("Machine learning: K-Means clustering on standardised attitudes and behaviours, silhouette-based "
                     "choice of k, PCA projection, automatic persona naming; Van Westendorp price sensitivity meter")

    def register_tools(self):
        self.tool("choose_number_of_segments", seg.select_k, "fit K-Means for k=3..8 and compare silhouette / CH / DB scores")
        self.tool("fit_segments", seg.fit_segments, "fit the final K-Means model")
        self.tool("profile_personas", self._personas, "profile and name each segment")
        self.tool("evaluate_concept", self._concept, "concept purchase intent and attractiveness by segment")
        self.tool("price_sensitivity_meter", self._vw, "Van Westendorp price sensitivity analysis")

    def execute(self) -> str:
        data = self.bb.require("datasets")
        plan = self.bb.require("plan")
        self.client = plan["client"]
        df = data["survey"].copy().reset_index(drop=True)
        aware_col = f"aware_{client_key(self.client)}"
        df["aware_client"] = df[aware_col] if aware_col in df else np.nan
        X, _ = seg.feature_matrix(df)
        k, ktab = self.use("choose_number_of_segments", X)
        self.think(f"Silhouette is highest at k={k} ({ktab.set_index('k').loc[k, 'silhouette']:.3f}); using {k} segments.")
        labels, _ = self.use("fit_segments", X, k)
        coords, evr = seg.pca_coords(X)
        profiles = self.use("profile_personas", df, labels)
        concept = self.use("evaluate_concept", profiles)
        primary, secondary = concept.iloc[0], concept.iloc[1]
        target_mask = np.isin(labels, [int(primary["segment"]), int(secondary["segment"])])
        vw = self.use("price_sensitivity_meter", df, labels, target_mask, primary)
        assign = pd.DataFrame(dict(respondent_id=df["respondent_id"], segment=labels,
                                   segment_name=pd.Series(labels).map(profiles.set_index("segment")["name"]),
                                   pc1=coords[:, 0].round(4), pc2=coords[:, 1].round(4), age=df["age"],
                                   spend=df["monthly_skincare_spend_idr"], main_brand=df["main_brand"]))
        imp = profiles.melt(id_vars=["segment", "name"], value_vars=seg.IMPORTANCE, var_name="attribute", value_name="importance")
        imp["attribute"] = imp["attribute"].map(seg.LABELS)
        brand_mix = pd.crosstab(pd.Series(labels, name="segment"), df["main_brand"], normalize="index").round(4).reset_index()
        tables = {"k_selection": ktab, "profiles": profiles, "concept": concept, "assignments": assign,
                  "importance": imp, "brand_mix": brand_mix, "vw_curves": vw["curves"], "vw_points": vw["points"]}
        self.put("segmentation.tables", tables, "Segments, personas, concept test and price research")
        self.put("segmentation.model_card", dict(algorithm="K-Means (k-means++, n_init=20) on standardised features",
                                                 features=[seg.LABELS[f] for f in seg.FEATURES], k=k,
                                                 silhouette=float(ktab.set_index("k").loc[k, "silhouette"]),
                                                 pca_explained_variance=evr, n=int(len(df))),
                 "Segmentation model card")
        self._publish_findings(df, ktab, k, profiles, concept, vw, brand_mix)
        return f"{k} segments; primary target: {primary['name']}; recommended price {idr(vw['recommended_price'])}"

    # ------------------------------------------------------------------ tools
    def _personas(self, df: pd.DataFrame, labels: np.ndarray) -> pd.DataFrame:
        profiles = seg.profile_segments(df, labels, self.client)
        names = seg.name_segments(profiles, df)
        drivers = seg.distinctive_drivers(profiles, df)
        profiles.insert(1, "name", profiles["segment"].map(names))
        profiles["drivers"] = profiles["segment"].map(lambda s: ", ".join(drivers[s]))
        profiles["description"] = profiles.apply(seg.describe, axis=1)
        if self.llm.available and self.options.get("use_llm", True):
            facts = profiles[["segment", "name", "share", "age_mean", "female_pct", "top_occupation", "spend_mean_idr",
                              "top_concern", "top_channel", "top_brand", "drivers"]].to_dict(orient="records")
            out = self.ask_llm("Give each segment a vivid but professional persona name (2-4 words). Return JSON "
                               "{\"names\": {\"<segment number>\": \"<name>\"}}.", facts, max_tokens=300, as_json=True)
            new = (out or {}).get("names", {}) if isinstance(out, dict) else {}
            cleaned = {int(k): str(v).strip() for k, v in new.items() if str(k).isdigit() and isinstance(v, str) and 2 <= len(v) <= 40}
            if len(cleaned) == len(profiles) and len(set(cleaned.values())) == len(cleaned):
                profiles["name"] = profiles["segment"].map(cleaned)
        return profiles

    def _concept(self, profiles: pd.DataFrame) -> pd.DataFrame:
        """Primary target = the sizeable segment (>= 10% of consumers) most eager to buy the concept;
        secondary = the largest remaining pool of likely buyers (segment share x top-2-box intent)."""
        c = profiles[["segment", "name", "share", "concept_t2b", "concept_mean", "spend_mean_idr", "client_user_pct",
                      "top_concern", "top_skin_type"]].copy()
        c["attractiveness"] = (0.40 * minmax(c["concept_t2b"]) + 0.25 * minmax(c["share"]) +
                               0.20 * minmax(c["spend_mean_idr"]) + 0.15 * minmax(c["client_user_pct"])).round(3)
        c["volume_potential"] = (c["share"] * c["concept_t2b"]).round(4)
        sizeable = c[c["share"] >= 0.10]
        primary = (sizeable if len(sizeable) else c)["concept_t2b"].idxmax()
        rest = c.drop(index=primary)
        secondary = rest["volume_potential"].idxmax()
        c["role"] = "other"
        c.loc[primary, "role"], c.loc[secondary, "role"] = "primary", "secondary"
        order = [primary, secondary] + list(rest.drop(index=secondary).sort_values("attractiveness", ascending=False).index)
        return c.loc[order].reset_index(drop=True)

    def _vw(self, df: pd.DataFrame, labels: np.ndarray, target_mask: np.ndarray, primary: pd.Series) -> dict:
        overall, _ = van_westendorp(df, *VW_COLS)
        target, curves = van_westendorp(df[target_mask], *VW_COLS)
        prim, _ = van_westendorp(df[labels == int(primary["segment"])], *VW_COLS)
        lo, hi = sorted([target["opp"], target["ipp"]])
        mid = (lo + hi) / 2
        allowed = [p for p in PRICE_POINTS if target["pmc"] <= p <= target["pme"]] or PRICE_POINTS
        rec = min(allowed, key=lambda p: abs(p - mid))
        points = pd.DataFrame([dict(group="All respondents", **overall), dict(group="Target segments", **target),
                               dict(group=f"Primary: {primary['name']}", **prim)])
        return dict(curves=curves, points=points, target=target, overall=overall, recommended_price=rec)

    # ------------------------------------------------------------------ findings
    def _publish_findings(self, df, ktab, k, profiles, concept, vw, brand_mix) -> None:
        c = self.client
        sil = float(ktab.set_index("k").loc[k, "silhouette"])
        self.publish(Finding(
            id="SEG-01", agent=self.name, area="segmentation", title=f"{k} consumer segments",
            statement=(f"K-Means clustering of {len(df):,} screened respondents on 16 attitudinal and behavioural variables finds "
                       f"{k} distinct segments (silhouette {sil:.3f}, the best of k=3-8): "
                       + "; ".join(f"{p.name} ({pct(p.share, 0, sign=False)})" for p in profiles.itertuples()) + "."),
            metrics=dict(k=k, silhouette=round(sil, 4), n=len(df),
                         **{f"segment_{p.segment}": p.name for p in profiles.itertuples()},
                         **{f"segment_{p.segment}_share": p.share for p in profiles.itertuples()}),
            evidence=["consumer_survey.csv"], impact=3, confidence=0.85, tags=["methodology", "segments"]))

        p, s = concept.iloc[0], concept.iloc[1]
        overall_t2b = float((df["concept_purchase_intent"] >= 4).mean())
        overall_client = float((df["main_brand"] == c).mean())
        self.publish(Finding(
            id="SEG-02", agent=self.name, area="segmentation", title=f"Primary target: {p['name']}",
            statement=(f"The primary target for the concept is '{p['name']}' ({pct(p['share'], 0, sign=False)} of consumers): "
                       f"{pct(p['concept_t2b'], 0, sign=False)} would probably or definitely buy it (vs "
                       f"{pct(overall_t2b, 0, sign=False)} overall), they spend about {idr(p['spend_mean_idr'])} a month on "
                       f"skincare, and {pct(p['client_user_pct'], 0, sign=False)} already use {c} (vs "
                       f"{pct(overall_client, 0, sign=False)} overall)."),
            metrics=dict(segment=p["name"], share=p["share"], concept_t2b=p["concept_t2b"], overall_t2b=round(overall_t2b, 4),
                         spend_idr=p["spend_mean_idr"], client_user_pct=p["client_user_pct"],
                         overall_client_pct=round(overall_client, 4)),
            evidence=["consumer_survey.csv (concept test)"], impact=5, confidence=0.8, swot="O", tags=["target", "concept"]))
        self.publish(Finding(
            id="SEG-03", agent=self.name, area="segmentation", title=f"Secondary target: {s['name']}",
            statement=(f"'{s['name']}' is the secondary target: {pct(s['share'], 0, sign=False)} of consumers with "
                       f"{pct(s['concept_t2b'], 0, sign=False)} top-2-box intent and {idr(s['spend_mean_idr'])} monthly spend."),
            metrics=dict(segment=s["name"], share=s["share"], concept_t2b=s["concept_t2b"], spend_idr=s["spend_mean_idr"]),
            evidence=["consumer_survey.csv (concept test)"], impact=3, confidence=0.75, swot="O", tags=["target", "concept"]))

        t = vw["target"]
        self.publish(Finding(
            id="SEG-04", agent=self.name, area="pricing", title="Concept price research (Van Westendorp)",
            statement=(f"Among the two target segments (n={t['n']:,}), the acceptable price range for the concept is "
                       f"{idr(t['pmc'])}-{idr(t['pme'])} and the optimal zone {idr(min(t['opp'], t['ipp']))}-"
                       f"{idr(max(t['opp'], t['ipp']))}; recommended launch price: {idr(vw['recommended_price'])}."),
            metrics=dict(pmc=t["pmc"], opp=t["opp"], ipp=t["ipp"], pme=t["pme"], n=t["n"],
                         recommended_price=vw["recommended_price"]),
            evidence=["consumer_survey.csv (Van Westendorp PSM)"], impact=4, confidence=0.75, swot="O", tags=["price", "concept"]))

        bm = brand_mix.set_index("segment")
        for prof in profiles.sort_values("share", ascending=False).itertuples():
            row = bm.loc[prof.segment].drop(labels=[c], errors="ignore")
            rival = row.idxmax()
            if prof.share >= 0.2 and row.max() >= 0.35 and rival != "Other local brand":
                self.publish(Finding(
                    id="SEG-05", agent=self.name, area="segmentation", title=f"{rival} owns '{prof.name}'",
                    statement=(f"{rival} is the main brand of {pct(row.max(), 0, sign=False)} of '{prof.name}' "
                               f"({pct(prof.share, 0, sign=False)} of consumers), versus {pct(bm.loc[prof.segment].get(c, 0), 0, sign=False)} for {c}."),
                    metrics=dict(rival=rival, rival_share=round(float(row.max()), 4), segment=prof.name,
                                 segment_share=prof.share, client_share=round(float(bm.loc[prof.segment].get(c, 0)), 4)),
                    evidence=["consumer_survey.csv"], impact=3, confidence=0.7, swot="T", tags=["competitor", "segments"]))
                break
