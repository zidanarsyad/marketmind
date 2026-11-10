#!/usr/bin/env python
"""Validate MarketMind's sentiment models on real Indonesian text (sources in docs/DATA_SOURCES.md).

    python scripts/validate_on_real_data.py                  # all three training modes
    python scripts/validate_on_real_data.py --modes study    # only the models trained on the study's reviews
    python scripts/validate_on_real_data.py --no-train       # only models already cached by MarketMind runs

Each training mode of the Consumer Insight agent (run option --sentiment-data) is scored on:
- the study's reviews (held-out study reviews, or all of them when the model never saw any),
- real Shopee/Tokopedia beauty reviews: the corpus's test split, minus reviews that also occur in its
  train or validation split (the splits MarketMind may train on),
- IndoNLU SmSA: 500 general-topic sentences labelled by linguists.

A mode's model is taken from MarketMind's cache when a run has trained it; otherwise it is trained here,
in memory only. Nothing is written to the model cache. Results go to outputs/real_data_validation.json.

Inputs, downloaded into data/external/ (both openly licensed; see the SOURCE.txt in each folder):
  ulasan-beauty-products/  Shopee and Tokopedia beauty reviews with star ratings (Hugging Face, Apache-2.0)
  indonlu-smsa/            IndoNLU SmSA test split (GitHub)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from marketmind.config import DATA_EXTERNAL, OUTPUTS  # noqa: E402
from marketmind.ml import real_reviews  # noqa: E402
from marketmind.ml.sentiment import LABELS, SentimentSuite, _metrics, rating_to_label  # noqa: E402
from marketmind.ml.text import detect_aspects  # noqa: E402

SMSA = DATA_EXTERNAL / "indonlu-smsa"
OUT = OUTPUTS / "real_data_validation.json"
MODE_NAMES = {"study": "study reviews only (the default)", "study+real": "study + real reviews", "real": "real reviews only"}


def load_smsa(split: str) -> tuple[list[str], np.ndarray]:
    df = pd.read_csv(SMSA / f"{split}_preprocess.tsv", sep="\t", header=None, names=["text", "label"], quoting=3)
    return df["text"].astype(str).tolist(), df["label"].map(LABELS.index).to_numpy()


def study_reviews() -> tuple[np.ndarray, np.ndarray]:
    """The study's reviews with text and their star labels, cleaned as the Data Quality agent does."""
    from marketmind.sql_export import clean_datasets
    reviews = clean_datasets()["reviews"]
    text = reviews[reviews["has_text"]]
    return text["review_text"].to_numpy(dtype=object), rating_to_label(text["rating"].values)


def score(suite: SentimentSuite, texts, y: np.ndarray) -> dict:
    """Metrics for each candidate, with the ensemble weight the suite chose on its own validation data."""
    texts = list(texts)
    p_lin, p_nn = suite.linear.predict_proba(texts), suite.neural.predict_proba(texts)
    w = suite.ensemble_weight
    return {name: _metrics(y, p) for name, p in
            (("linear", p_lin), ("bigru", p_nn), ("ensemble", w * p_lin + (1 - w) * p_nn))}


def suite_for(mode: str, study_x, study_y, train: bool) -> tuple[SentimentSuite | None, str, dict]:
    x, y, src = real_reviews.training_set(mode, study_x, study_y)
    counts = {s: int((src == s).sum()) for s in ("study", "real")}
    suite = SentimentSuite(real_reviews.model_dir(mode))
    if suite.try_load(suite.data_hash(x, y)):
        return suite, "loaded from MarketMind's cache", counts
    if not train:
        return None, "not cached (run MarketMind with this mode, or drop --no-train)", counts
    print(f"   training on {len(x):,} reviews in memory (a few minutes) ...")
    suite.train(x, y, log=lambda m: print("     ", m), sources=None if mode == "study" else src)
    return suite, "trained in memory", counts


def study_score(mode: str, suite: SentimentSuite, study_x, study_y) -> tuple[dict, str]:
    """The study-domain score that is fair for this mode."""
    card = suite.card
    if mode == "real":
        return score(suite, study_x, study_y), f"all {len(study_x):,} study reviews (never seen in training)"
    if mode == "study+real" and "study" in (card.get("test_metrics_by_source") or {}):
        n = card.get("split_sources", {}).get("test", {}).get("study", 0)
        return card["test_metrics_by_source"]["study"], f"{n:,} held-out study reviews"
    return card["test_metrics"], f"{card['n_test']:,} held-out study reviews"


def line(label: str, m: dict) -> str:
    return " | ".join(f"{k} {m[k]['macro_f1']:.3f}" for k in ("linear", "bigru", "ensemble")) + f"   <- {label}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--modes", nargs="+", choices=real_reviews.TRAINING_MODES, default=list(real_reviews.TRAINING_MODES))
    ap.add_argument("--no-train", action="store_true", help="score only models that MarketMind runs have cached")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    missing = [p for p in (real_reviews.REAL_REVIEWS_DIR / "test_data.parquet", SMSA / "test_preprocess.tsv") if not p.exists()]
    if missing or not real_reviews.available():
        print("Missing input files; see docs/DATA_SOURCES.md:", *(missing or [real_reviews.REAL_REVIEWS_DIR]), sep="\n  ")
        return 1

    seen = set(pd.concat([real_reviews.load(s) for s in real_reviews.TRAINING_SPLITS])["text"])
    test = real_reviews.load("test")
    keep = ~test["text"].isin(seen)                          # drop test reviews that also occur in a training split
    te_x, te_y = test.loc[keep, "text"].tolist(), test.loc[keep, "label"].to_numpy()
    sm_x, sm_y = load_smsa("test")
    study_x, study_y = study_reviews()
    dist = lambda y: {LABELS[i]: int(n) for i, n in enumerate(np.bincount(y, minlength=3))}  # noqa: E731
    result = dict(
        run_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        data=dict(study_reviews=dict(n=len(study_x), labels=dist(study_y)),
                  beauty_test=dict(n=len(te_x), removed_overlap=int((~keep).sum()), labels=dist(te_y)),
                  smsa_test=dict(n=len(sm_x), labels=dist(sm_y)),
                  label_rule="reviews: stars 1-2 negative, 3 neutral, 4-5 positive; SmSA: human labels"),
        aspect_coverage_real_beauty=None, modes={})
    found = [detect_aspects(t) for t in te_x]
    result["aspect_coverage_real_beauty"] = dict(
        share_with_aspect=round(float(np.mean([bool(f) for f in found])), 4),
        top_aspects={k: int(v) for k, v in pd.Series([a for f in found for a in f]).value_counts().head(9).items()})

    print("macro-F1 per candidate: linear | bigru | ensemble")
    for mode in args.modes:
        print(f"\nMode '{mode}': {MODE_NAMES[mode]}")
        t0 = time.time()
        suite, status, counts = suite_for(mode, study_x, study_y, train=not args.no_train)
        print(f"   {status}; training data: {counts['study']:,} study + {counts['real']:,} real reviews")
        if suite is None:
            result["modes"][mode] = dict(status=status, training_reviews=counts)
            continue
        on_study, study_basis = study_score(mode, suite, study_x, study_y)
        entry = dict(status=status, seconds=round(time.time() - t0, 1), training_reviews=counts, selected=suite.selected,
                     study_reviews=dict(basis=study_basis, metrics=on_study),
                     beauty_test=score(suite, te_x, te_y), smsa_test=score(suite, sm_x, sm_y))
        result["modes"][mode] = entry
        print("   " + line(f"study reviews ({study_basis})", on_study))
        print("   " + line(f"real beauty reviews ({len(te_x):,}, test split)", entry["beauty_test"]))
        print("   " + line(f"SmSA ({len(sm_x)}, human labels)", entry["smsa_test"]))
        print(f"   selected by validation: {suite.selected}")

    print(f"\nThe aspect lexicon finds at least one aspect in {result['aspect_coverage_real_beauty']['share_with_aspect']:.1%} "
          f"of the real beauty reviews.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved {OUT.relative_to(OUT.parents[1])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
