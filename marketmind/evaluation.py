"""Objective evaluation of a run against the ground truth planted in the synthetic data.

Because the datasets are simulated, we know the "true" market facts (elasticities, events, segments,
trends, data defects). This module checks how many of them the agents recovered - an insight-recall
score for the whole multi-agent system, plus model-level metrics against hidden labels.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, adjusted_rand_score, f1_score

from .config import DATA_DIR, GROUND_TRUTH
from .core.store import RunData

GT_DIR = DATA_DIR / "ground_truth"


def _f(run: RunData) -> dict:
    return {f.id: f for f in run.findings}


def evaluate(run: RunData) -> dict:
    truth = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    exp = truth["expected_insights"]
    F = _f(run)
    checks = []

    def check(area, name, expected, found, passed, detail=""):
        checks.append(dict(area=area, check=name, expected=str(expected), found=str(found), passed=bool(passed), detail=detail))

    def metric(fid, key, default=None):
        return F[fid].metrics.get(key, default) if fid in F else default

    # -- market
    check("market", "Fastest-growing category", exp["fastest_growing_category"], metric("MKT-02", "top_category"),
          metric("MKT-02", "top_category") == exp["fastest_growing_category"])
    check("market", "Fastest-growing channel", exp["fastest_growing_channel"], metric("MKT-03", "fastest_channel"),
          metric("MKT-03", "fastest_channel") == exp["fastest_growing_channel"])
    check("market", "Fastest-growing region", exp["fastest_growing_regions"][0], metric("MKT-04", "top_region"),
          metric("MKT-04", "top_region") in exp["fastest_growing_regions"][:2])
    rising = [v for k, v in (F["MKT-06"].metrics.items() if "MKT-06" in F else []) if k.startswith("rising_") and not k.endswith("_change")]
    falling = [v for k, v in (F["MKT-06"].metrics.items() if "MKT-06" in F else []) if k.startswith("declining_") and not k.endswith("_change")]
    rec_up = len(set(rising) & set(exp["rising_topics"])) / len(exp["rising_topics"])
    rec_dn = len(set(falling) & set(exp["declining_topics"])) / len(exp["declining_topics"])
    check("market", "Rising topics recalled", exp["rising_topics"], rising, rec_up >= 0.75, f"recall {rec_up:.0%}")
    check("market", "Declining topics recalled", exp["declining_topics"], falling, rec_dn >= 0.66, f"recall {rec_dn:.0%}")

    # -- competition
    check("competition", "Client under-indexed channel", exp["client_underindexed_channel"], metric("CMP-02", "channel"),
          metric("CMP-02", "channel") == exp["client_underindexed_channel"])
    check("competition", "Top competitive threat", " or ".join(exp["top_competitive_threats"]), metric("CMP-05", "brand"),
          metric("CMP-05", "brand") in exp["top_competitive_threats"])
    ws = str(metric("CMP-08", "space", ""))
    check("competition", "White space identified", exp["white_space"], ws,
          "fragrance-free" in ws.lower() and "moisturizer" in ws.lower())

    # -- consumer
    asp = metric("CON-03", "aspect")
    check("consumer", "Client's top pain point", "Packaging (kemasan)", asp, asp == "Packaging")
    s, e = metric("CON-03", "start"), metric("CON-03", "end")
    tm = exp["client_negative_spike_months"]
    overlap = bool(s and e and s <= tm[-1] and e >= tm[0])
    check("consumer", "Pain-point timing", f"{tm[0]}..{tm[-1]}", f"{s}..{e}", overlap)
    gm = exp["glownesia_negative_spike_months"]
    ok = metric("CON-05", "brand") == "GlowNesia" and metric("CON-05", "aspect") == "Authenticity" \
        and (metric("CON-05", "start") or "9999") <= gm[-1] and (metric("CON-05", "end") or "0000") >= gm[0]
    check("consumer", "Competitor crisis (counterfeits)", f"GlowNesia authenticity {gm[0]}..{gm[-1]}",
          f"{metric('CON-05', 'brand')} {metric('CON-05', 'aspect')} {metric('CON-05', 'start')}..{metric('CON-05', 'end')}", ok)
    price_spike = any(f.id in ("CON-03", "CON-04", "CON-06") and "price" in (str(f.metrics.get("aspect", "")) + f.title).lower()
                      for f in F.values())
    check("consumer", "Price-increase backlash detected", "Kirana price complaints after 2025-07", price_spike, price_spike)

    # -- segmentation & pricing
    k = metric("SEG-01", "k")
    check("segmentation", "Number of segments", exp["n_segments"], k, k == exp["n_segments"])
    assign = run.table("segmentation.tables.assignments")
    ari, target_true = None, None
    if assign is not None and (GT_DIR / "survey_segments.csv").exists():
        gt = pd.read_csv(GT_DIR / "survey_segments.csv").merge(assign, on="respondent_id")
        ari = adjusted_rand_score(gt["true_segment"], gt["segment"])
        prim = metric("SEG-02", "segment")
        members = gt[gt["segment_name"] == prim]
        target_true = members["true_segment"].mode().iloc[0] if len(members) else None
    check("segmentation", "Segment recovery (ARI)", ">= 0.80", None if ari is None else round(ari, 3), ari is not None and ari >= 0.8)
    check("segmentation", "Concept target segment", exp["target_segment_for_concept"], target_true,
          target_true == exp["target_segment_for_concept"])
    price = metric("SEG-04", "recommended_price")
    lo, hi = exp["concept_optimal_price_band_idr"]
    support, alt = metric("SEG-04", "price_support"), metric("SEG-04", "alternative_price")
    found = f"{price}" + (f" (wins {support:.0%} of bootstrap resamples; runner-up {alt})" if support is not None and alt else "")
    check("pricing", "Recommended concept price", f"Rp {lo:,}-{hi:,}", found, price is not None and lo <= price <= hi)
    el = run.table("forecast.tables.elasticities")
    if el is not None:
        el = el.assign(true=el["brand"].map(truth["price_elasticity"]))
        mae = float((el["elasticity"] - el["true"]).abs().mean())
        client_err = float((el.set_index("brand").loc[truth["client_brand"], "elasticity"] - truth["price_elasticity"][truth["client_brand"]]))
        check("pricing", "Client price elasticity", truth["price_elasticity"][truth["client_brand"]],
              round(truth["price_elasticity"][truth["client_brand"]] + client_err, 3), abs(client_err) <= 0.2,
              f"error {client_err:+.3f}; MAE across brands {mae:.3f}")

    # -- models
    card = run.json("consumer.model_card", {}) or {}
    sel = card.get("selected")
    if sel:  # judged on the study's own reviews, whichever data the models were trained on
        by_source = card.get("test_metrics_by_source") or {}
        if "study" in by_source:
            f1, basis = by_source["study"][sel]["macro_f1"], "held-out study reviews (trained on study + real reviews)"
        elif card.get("study_reviews_check"):
            f1, basis = card["study_reviews_check"]["macro_f1"], "all study reviews (trained on real reviews only)"
        else:
            f1, basis = card["test_metrics"][sel]["macro_f1"], ""
        check("models", "Sentiment model quality (held-out reviews)", "macro-F1 >= 0.75", round(f1, 3), f1 >= 0.75, basis)
    soc = run.table("consumer.tables.social_scored")
    if soc is not None and (GT_DIR / "social_sentiment.csv").exists():
        m = soc.merge(pd.read_csv(GT_DIR / "social_sentiment.csv"), on="post_id")
        acc = accuracy_score(m["true_sentiment"], m["pred"])
        mf1 = f1_score(m["true_sentiment"], m["pred"], average="macro")
        check("models", "Sentiment transfer to all social posts (hidden labels)", "accuracy >= 0.85",
              f"{acc:.3f} (macro-F1 {mf1:.3f}, n={len(m):,})", acc >= 0.85)
    asp_s = run.table("consumer.tables.aspect_mentions_sample")
    if asp_s is not None and (GT_DIR / "review_aspects.csv").exists():
        gt = pd.read_csv(GT_DIR / "review_aspects.csv").set_index("review_id")["true_aspects"].fillna("")
        rows = asp_s[asp_s["review_id"].isin(gt.index)]
        truth_map = {rid: dict(a.split(":") for a in gt[rid].split(";") if ":" in a) for rid in rows["review_id"].unique()}
        hit = [r.aspect in truth_map[r.review_id] for r in rows.itertuples()]
        pol = [truth_map[r.review_id][r.aspect] == ("pos" if r.polarity == "positive" else "neg")
               for r, h in zip(rows.itertuples(), hit, strict=True) if h and r.polarity != "neutral"]
        prec, pacc = float(np.mean(hit)) if hit else 0.0, float(np.mean(pol)) if pol else 0.0
        check("models", "Aspect detection precision / polarity accuracy", ">= 0.80 / >= 0.85",
              f"{prec:.3f} / {pacc:.3f} (n={len(rows):,})", prec >= 0.8 and pacc >= 0.85)
    fm = run.json("forecast.model_card", {}) or {}
    if fm.get("metrics"):
        best, naive = fm["metrics"][fm["model_key"]]["series_wape"], fm["metrics"]["seasonal_naive"]["series_wape"]
        check("models", "Forecast beats seasonal-naive benchmark", f"WAPE < {naive:.3f}", round(best, 3), best < naive)

    # -- data quality
    dq = run.json("dq.report", {}) or {}
    inj = truth["data_quality_defects"]
    if "sales" in dq:
        found = dq["sales"]["issues"]
        exp_bad = inj["sales"]["negative_units"] + inj["sales"]["outliers_x12"]
        got_bad = found.get("non_positive_units", 0) + found.get("outliers", 0)
        check("data", "Invalid sales rows caught", exp_bad, got_bad, got_bad >= exp_bad)
        check("data", "Duplicate sales rows removed", inj["sales"]["duplicate_rows"], found.get("duplicates"),
              found.get("duplicates", 0) >= inj["sales"]["duplicate_rows"] * 0.95)
    if "survey" in dq:
        iss = dq["survey"]["issues"]
        injected = inj["survey"]["speeders"] + inj["survey"]["straight_liners"] + inj["survey"]["attention_fails"]
        caught = iss.get("speeders", 0) + iss.get("straight_liners", 0) + iss.get("attention_fails", 0)
        check("data", "Low-quality survey responses caught", injected, caught, caught >= injected * 0.95)
    qa = run.meta.get("qa", {})
    check("governance", "Report passed the Critic's QA gate", "passed", qa.get("score"), bool(qa.get("passed")))

    df = pd.DataFrame(checks)
    return dict(score=round(float(df["passed"].mean()), 4), passed=int(df["passed"].sum()), total=len(df),
                checks=df.to_dict(orient="records"))
