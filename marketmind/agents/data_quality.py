"""Data Quality Agent: profiles, validates and cleans every dataset and documents each fix.

Checks include duplicate records, inconsistent category labels, impossible values, statistical
outliers, missing values (imputed where safe) and survey-response quality (speeders,
straight-liners, failed attention checks, invalid ages) - standard practice in commercial
market research before any analysis is trusted.
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from ..core.agent import BaseAgent
from ..core.findings import Finding
from ..ml.segmentation import IMPORTANCE

ATTENTION_EXPECTED = 4  # instructed-response item: "select 'Agree' (4) for this question"


def _canonical_labels(series: pd.Series) -> dict[str, str]:
    """Map label variants (case, spacing, truncation) to the most frequent spelling."""
    def key(s) -> str:
        return re.sub(r"[^a-z0-9]", "", str(s).lower())

    counts = series.value_counts()
    canon_by_key: dict[str, str] = {}
    for label in counts.index:  # most frequent first
        canon_by_key.setdefault(key(label), label)
    keys = sorted(canon_by_key, key=lambda k: -counts[canon_by_key[k]])
    mapping = {}
    for label in counts.index:
        k = key(label)
        target = canon_by_key[k]
        if counts[target] < 0.05 * counts.iloc[0]:  # rare spelling: try to attach to a frequent label it prefixes
            for big in keys:
                if big != k and big.startswith(k) and counts[canon_by_key[big]] >= 0.05 * counts.iloc[0]:
                    target = canon_by_key[big]
                    break
        mapping[label] = target
    return mapping


class DataQualityAgent(BaseAgent):
    name = "Data Quality Agent"
    role = "Data steward. Profiles, validates and cleans every dataset and documents each fix."
    goal = "Make sure downstream analysis runs on trustworthy data and that limitations are disclosed."

    def register_tools(self):
        self.tool("clean_sales_panel", self._clean_sales, "standardise labels, drop duplicates, impossible values and outliers, impute discounts")
        self.tool("clean_reviews", self._clean_reviews, "de-duplicate reviews, parse dates, flag rating-only reviews")
        self.tool("screen_survey_responses", self._clean_survey, "remove speeders, straight-liners, attention-check failures, invalid ages")
        self.tool("clean_social_posts", self._clean_social, "remove reposts and normalise fields")
        self.tool("validate_reference_data", self._clean_reference, "validate catalogue and market-size tables")

    def execute(self) -> str:
        raw = self.bb.require("datasets.raw")
        clean, report = {}, {}
        steps = [("sales", "clean_sales_panel"), ("reviews", "clean_reviews"), ("survey", "screen_survey_responses"),
                 ("social", "clean_social_posts")]
        for key, tool in steps:
            if key in raw:
                clean[key], report[key] = self.use(tool, raw[key])
        for key in ("catalog", "market_size"):
            if key in raw:
                clean[key], report[key] = self.use("validate_reference_data", raw[key], key)
        for key in set(raw) - set(clean):  # auxiliary tables pass through after de-duplication
            d = raw[key].drop_duplicates()
            clean[key] = d
            report[key] = dict(rows_in=len(raw[key]), rows_out=len(d), issues={"duplicates": len(raw[key]) - len(d)},
                               actions=[], warnings=[], completeness=self._completeness(raw[key], list(raw[key].columns)))
        rows = []
        for key, rep in report.items():
            removed = rep["rows_in"] - rep["rows_out"]
            score = 100 - 200 * removed / max(rep["rows_in"], 1) - 50 * (1 - rep["completeness"]) - 2 * len(rep.get("warnings", []))
            rows.append(dict(dataset=key, rows_in=rep["rows_in"], rows_out=rep["rows_out"], removed=removed,
                             issues_fixed=sum(rep["issues"].values()), completeness=round(rep["completeness"], 4),
                             quality_score=round(float(np.clip(score, 0, 100)), 1),
                             actions="; ".join(rep["actions"]) or "no changes needed"))
        scorecard = pd.DataFrame(rows)
        overall = round(float(np.average(scorecard["quality_score"], weights=scorecard["rows_in"])), 1)
        caveats = [
            "All datasets are simulated for demonstration purposes; brands, products and respondents are fictional.",
            "The sales panel tracks six local brands, not the whole market; shares are shares of the tracked panel.",
            "Review sentiment labels come from star ratings, which are a noisy proxy for what the text says.",
        ]
        if "survey" in report:
            s = report["survey"]
            caveats.append(f"Survey base after quality screening: n={s['rows_out']:,} "
                           f"({s['rows_in'] - s['rows_out']} low-quality responses removed).")
        self.put("datasets", clean, "Cleaned, analysis-ready datasets")
        self.put("dq.report", report, "Per-dataset data quality report")
        self.put("dq.scorecard", scorecard, "Data quality scorecard")
        self.put("dq.caveats", caveats, "Limitations to disclose in the report")
        sales, survey = report.get("sales", {}), report.get("survey", {})
        self.publish(Finding(
            id="DAT-02", agent=self.name, area="data", title="Data quality",
            statement=(f"Data quality score {overall}/100 after fixing {int(scorecard['issues_fixed'].sum()):,} issues: e.g. "
                       f"{sales.get('issues', {}).get('duplicates', 0)} duplicate and "
                       f"{sales.get('issues', {}).get('outliers', 0) + sales.get('issues', {}).get('non_positive_units', 0)} "
                       f"invalid sales rows removed, and {survey.get('rows_in', 0) - survey.get('rows_out', 0)} low-quality "
                       f"survey responses excluded."),
            metrics=dict(quality_score=overall, issues_fixed=int(scorecard["issues_fixed"].sum()),
                         survey_removed=int(survey.get("rows_in", 0) - survey.get("rows_out", 0))),
            evidence=["dq.scorecard"], impact=1, confidence=1.0, tags=["methodology"]))
        return f"Cleaned {len(clean)} datasets; overall quality score {overall}/100"

    # ------------------------------------------------------------------ tools
    @staticmethod
    def _completeness(df: pd.DataFrame, cols: list[str]) -> float:
        cols = [c for c in cols if c in df]
        return float(1 - df[cols].isna().mean().mean()) if cols else 1.0

    def _clean_sales(self, df: pd.DataFrame):
        d = df.copy()
        rows_in, issues, actions = len(d), {}, []
        mapping = _canonical_labels(d["channel"])
        fixed = int((d["channel"] != d["channel"].map(mapping)).sum())
        d["channel"] = d["channel"].map(mapping)
        issues["label_variants"] = fixed
        if fixed:
            actions.append(f"standardised {fixed} inconsistent channel labels")
        dups = int(d.duplicated().sum())
        d = d.drop_duplicates()
        issues["duplicates"] = dups
        if dups:
            actions.append(f"removed {dups} duplicate rows")
        bad = int((d["units"] < 0).sum())
        d = d[d["units"] >= 0]
        issues["non_positive_units"] = bad
        if bad:
            actions.append(f"removed {bad} rows with negative units/revenue")
        keys = ["brand", "category", "channel", "region"]
        med = d.groupby(keys)["units"].transform("median")
        mad = d.groupby(keys)["units"].transform(lambda s: (s - s.median()).abs().median()).replace(0, np.nan)
        robust_z = (d["units"] - med) / (1.4826 * mad)
        out = (d["units"] > 4 * med) & (robust_z > 8)
        issues["outliers"] = int(out.sum())
        d = d[~out]
        if out.any():
            actions.append(f"removed {int(out.sum())} extreme outliers (>4x series median, robust z>8)")
        miss = int(d["discount_pct"].isna().sum())
        if miss:
            fill = d.groupby(["brand", "channel", "month"])["discount_pct"].transform("mean")
            d["discount_pct"] = d["discount_pct"].fillna(fill).fillna(d.groupby("channel")["discount_pct"].transform("median"))
            actions.append(f"imputed {miss} missing discount values from brand-channel-month means")
        issues["missing_discount"] = miss
        implied = d["units"] * d["avg_selling_price_idr"]
        inconsistent = int(((implied - d["revenue_idr"]).abs() > 0.02 * d["revenue_idr"].abs() + 1).sum())
        warnings = [f"{inconsistent} rows where revenue != units x price"] if inconsistent else []
        d["month"] = pd.to_datetime(d["month"])
        return d.reset_index(drop=True), dict(rows_in=rows_in, rows_out=len(d), issues=issues, actions=actions,
                                              warnings=warnings, completeness=self._completeness(df, list(df.columns)))

    def _clean_reviews(self, df: pd.DataFrame):
        d = df.copy()
        rows_in, issues, actions = len(d), {}, []
        dups = int(d.duplicated(["reviewer_id", "review_text", "sku_id"]).sum())
        d = d.drop_duplicates(["reviewer_id", "review_text", "sku_id"])
        issues["duplicates"] = dups
        if dups:
            actions.append(f"removed {dups} duplicate reviews")
        d["review_date"] = pd.to_datetime(d["review_date"], errors="coerce")
        bad_date = int(d["review_date"].isna().sum())
        d = d.dropna(subset=["review_date"])
        bad_rating = int((~d["rating"].between(1, 5)).sum())
        d = d[d["rating"].between(1, 5)]
        issues["invalid_values"] = bad_date + bad_rating
        d["month"] = d["review_date"].dt.to_period("M").dt.to_timestamp()
        d["has_text"] = d["review_text"].fillna("").str.strip().str.len() > 0
        n_empty = int((~d["has_text"]).sum())
        actions.append(f"flagged {n_empty} rating-only reviews (kept for star ratings, excluded from text models)")
        return d.reset_index(drop=True), dict(rows_in=rows_in, rows_out=len(d), issues=issues, actions=actions,
                                              warnings=[], completeness=self._completeness(df, ["rating", "brand", "review_date", "sku_id"]))

    def _clean_survey(self, df: pd.DataFrame):
        d = df.copy()
        rows_in, issues, actions = len(d), {}, []
        threshold = d["completion_time_sec"].median() / 3
        flags = {
            "speeders": d["completion_time_sec"] < threshold,
            "straight_liners": d[IMPORTANCE].std(axis=1) == 0,
            "attention_fails": d["attention_check"] != ATTENTION_EXPECTED,
            "invalid_age": ~d["age"].between(15, 75),
        }
        for k, f in flags.items():
            issues[k] = int(f.sum())
        bad = np.logical_or.reduce(list(flags.values()))
        d = d[~bad]
        actions.append(f"removed {int(bad.sum())} low-quality responses: {issues['speeders']} speeders "
                       f"(<{threshold:.0f}s, a third of the median), {issues['straight_liners']} straight-liners, "
                       f"{issues['attention_fails']} failed attention checks, {issues['invalid_age']} invalid ages")
        missing_income = int(d["monthly_income_idr"].isna().sum())
        if missing_income:
            actions.append(f"kept {missing_income} 'prefer not to say' income answers as missing")
        issues["missing_income"] = missing_income
        return d.reset_index(drop=True), dict(rows_in=rows_in, rows_out=len(d), issues=issues, actions=actions,
                                              warnings=[], completeness=self._completeness(df, list(df.columns)),
                                              speeder_threshold_sec=round(threshold))

    def _clean_social(self, df: pd.DataFrame):
        d = df.copy()
        rows_in, issues, actions = len(d), {}, []
        dups = int(d.duplicated("post_id").sum())
        d = d.drop_duplicates("post_id")
        issues["duplicates"] = dups
        if dups:
            actions.append(f"removed {dups} reposted duplicates")
        d["brand_mentioned"] = d["brand_mentioned"].fillna("")
        d["post_date"] = pd.to_datetime(d["post_date"], errors="coerce")
        d = d.dropna(subset=["post_date"])
        d["month"] = d["post_date"].dt.to_period("M").dt.to_timestamp()
        d["engagement"] = d[["likes", "comments", "shares"]].sum(axis=1)
        return d.reset_index(drop=True), dict(rows_in=rows_in, rows_out=len(d), issues=issues, actions=actions,
                                              warnings=[], completeness=self._completeness(df, ["post_text", "platform", "post_date"]))

    def _clean_reference(self, df: pd.DataFrame, key: str):
        d = df.copy()
        issues, actions, warnings = {}, [], []
        if key == "catalog":
            missing = int(d["rating_avg"].isna().sum())
            issues["missing_rating"] = missing
            if missing:
                actions.append(f"{missing} recently launched SKUs have no rating yet (kept, flagged)")
            d["price_tier"] = pd.cut(d["price_idr"], [0, 60000, 120000, np.inf], labels=["Mass (<Rp60k)", "Masstige (Rp60-120k)", "Premium (>Rp120k)"])
        else:
            years = sorted(d["year"].unique())
            if years != list(range(min(years), max(years) + 1)):
                warnings.append("market size years are not continuous")
            issues["non_positive"] = int((d["market_value_idr_bn"] <= 0).sum())
        return d, dict(rows_in=len(df), rows_out=len(d), issues=issues, actions=actions, warnings=warnings,
                       completeness=self._completeness(df, [c for c in df.columns if c not in ("spf", "yoy_growth_pct")]))
