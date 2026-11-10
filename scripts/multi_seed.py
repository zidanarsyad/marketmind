#!/usr/bin/env python
"""Robustness across data seeds: regenerate the simulated market with other seeds and re-run the whole study.

    python scripts/multi_seed.py                      # seeds 1-5
    python scripts/multi_seed.py --seeds 11 12 13

For each seed the generator writes a fresh dataset (the same planted effects, different random noise) to
outputs/seeds/seed-<n>/data, and a full offline study runs on it with its own outputs folder, so the bundled data,
its runs and its model cache are untouched. Each run is scored against its own ground truth. The summary
(outputs/seeds/summary.json) gives every metric's mean, spread and worst case, and the checks that failed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs" / "seeds"


def numbers(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", str(text).replace(",", ""))]


def study(seed: int) -> dict:
    """Generate, run and score one seed in its own folders; return its metrics."""
    folder = BASE / f"seed-{seed}"
    env = dict(os.environ, MARKETMIND_DATA_DIR=str(folder / "data"), MARKETMIND_OUTPUTS=str(folder / "outputs"),
               PYTHONIOENCODING="utf-8")
    quiet = dict(cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.time()
    subprocess.run([sys.executable, "scripts/generate_data.py", "--seed", str(seed), "--out", str(folder / "data" / "raw")],
                   check=True, **quiet)
    exit_code = subprocess.run([sys.executable, "run.py", "--no-llm", "--quiet"], **quiet).returncode
    subprocess.run([sys.executable, "scripts/evaluate_agents.py"], check=True, **quiet)
    run = sorted((folder / "outputs" / "runs").iterdir())[-1]
    load = lambda name: json.loads((run / name).read_text(encoding="utf-8"))  # noqa: E731
    meta, ev = load("run_meta.json"), load("evaluation.json")
    card, fcard = load("json/consumer.model_card.json"), load("json/forecast.model_card.json")
    truth = json.loads((folder / "data" / "ground_truth.json").read_text(encoding="utf-8"))
    el = pd.read_csv(run / "tables" / "forecast.tables.elasticities.csv")
    el["true"] = el["brand"].map(truth["price_elasticity"])
    found = {c["check"]: numbers(c["found"]) for c in ev["checks"]}
    sel = card["selected"]
    client = el.set_index("brand").loc[truth["client_brand"]]
    return dict(
        seed=seed, status=meta["status"], exit_code=exit_code, minutes=round((time.time() - t0) / 60, 1),
        checks_passed=ev["passed"], checks_total=ev["total"], qa_score=meta["qa"]["score"],
        failed=[c["check"] for c in ev["checks"] if not c["passed"]],
        sentiment_selected=sel, sentiment_macro_f1=card["test_metrics"][sel]["macro_f1"],
        transfer_macro_f1=card.get("transfer_metrics", {}).get(card.get("transfer_model"), {}).get("macro_f1"),
        social_accuracy=(found.get("Sentiment transfer to all social posts (hidden labels)") or [None])[0],
        aspect_precision=(found.get("Aspect detection precision / polarity accuracy") or [None])[0],
        aspect_polarity=(found.get("Aspect detection precision / polarity accuracy") or [None, None])[1],
        segment_ari=(found.get("Segment recovery (ARI)") or [None])[0],
        forecast_wape=fcard["metrics"][fcard["model_key"]]["series_wape"],
        naive_wape=fcard["metrics"]["seasonal_naive"]["series_wape"],
        client_elasticity_error=round(float(client["elasticity"] - client["true"]), 3),
        elasticity_mae=round(float((el["elasticity"] - el["true"]).abs().mean()), 3),
        elasticity_ci_coverage=int(((el["ci_low"] <= el["true"]) & (el["true"] <= el["ci_high"])).sum()),
        recommended_price=(found.get("Recommended concept price") or [None])[0],
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5])
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    rows = []
    for seed in args.seeds:
        row = study(seed)
        rows.append(row)
        print(f"seed {seed}: {row['checks_passed']}/{row['checks_total']} checks, QA {row['qa_score']}, "
              f"{row['minutes']} min" + (f"; failed: {', '.join(row['failed'])}" if row["failed"] else ""), flush=True)
    df = pd.DataFrame(rows).set_index("seed")
    stats = df.select_dtypes("number").drop(columns=["exit_code", "checks_total"]).agg(["mean", "std", "min", "max"]).T
    failures = Counter(check for row in rows for check in row["failed"])
    coverage = df["elasticity_ci_coverage"].sum() / (6 * len(df))
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / "summary.json").write_text(json.dumps(dict(
        seeds=args.seeds, runs=rows, stats=stats.round(4).to_dict(orient="index"), failures=dict(failures),
        all_checks_passed=int((df["checks_passed"] == df["checks_total"]).sum()), elasticity_ci_coverage_rate=round(coverage, 3),
    ), indent=2), encoding="utf-8")
    print("\n" + stats.round(3).to_string())
    print(f"\nAll 25 checks passed in {int((df['checks_passed'] == df['checks_total']).sum())} of {len(df)} seeds; "
          f"failures by check: {dict(failures) or 'none'}; elasticity 95% intervals contain the truth "
          f"{coverage:.0%} of the time.")
    print(f"Saved {(BASE / 'summary.json').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
