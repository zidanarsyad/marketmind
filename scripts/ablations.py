#!/usr/bin/env python
"""Ablations: switch off one design choice at a time and measure what it was buying.

    python scripts/ablations.py

Runs the offline study on the bundled data once per variant (the sentiment models are cached, so a few minutes
each) and scores every run against the ground truth. Runs go to outputs/ablations/runs, the comparison to
outputs/ablations/summary.json. The Critic's contribution needs an LLM, so it is measured by scripts/llm_runs.py.
`--only "BiGRU only"` re-runs chosen variants and keeps the other rows of an existing summary.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marketmind.config import OUTPUTS  # noqa: E402

VARIANTS = {
    "full system": {},
    "no transfer check": {"skip_transfer_check": True},   # social posts scored by the model chosen on reviews
    "BiGRU only": {"sentiment_model": "bigru"},
    "linear model only": {"sentiment_model": "linear"},     # no deep learning at all
    "no social-media rules": {"no_social_rules": True},     # no hashtag stripping, question rule or neutral band
}


def numbers(text: str) -> list[float]:
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", str(text).replace(",", ""))]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only", nargs="+", choices=list(VARIANTS), help="variants to run (default: all)")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from marketmind import system as system_module
    from marketmind.core.llm import LLMClient
    from marketmind.core.store import RunData
    from marketmind.evaluation import evaluate

    out = OUTPUTS / "ablations"
    system_module.RUNS_DIR = out / "runs"          # keep these runs apart from real studies
    previous = {}
    if args.only and (out / "summary.json").exists():
        previous = {r["variant"]: r for r in json.loads((out / "summary.json").read_text(encoding="utf-8"))}
    rows = []
    for name, options in VARIANTS.items():
        if args.only and name not in args.only:
            if name in previous:
                rows.append(previous[name])
            continue
        system = system_module.MarketResearchSystem(use_llm=False, llm=LLMClient(provider="none"))
        system.options.update(options)
        res = system.run()
        meta = json.loads((res.run_dir / "run_meta.json").read_text(encoding="utf-8"))
        ev = evaluate(RunData(run_id=res.run_id, path=res.run_dir, meta=meta))
        found = {c["check"]: numbers(c["found"]) for c in ev["checks"]}
        card = json.loads((res.run_dir / "json" / "consumer.model_card.json").read_text(encoding="utf-8"))
        aspects = found.get("Aspect detection precision / polarity accuracy") or [None, None]
        row = dict(variant=name, options=options, checks_passed=ev["passed"], checks_total=ev["total"],
                   failed=[c["check"] for c in ev["checks"] if not c["passed"]], qa_score=meta["qa"]["score"],
                   scorer=card["selected"], social_scorer=card.get("transfer_model", card["selected"]),
                   review_macro_f1=card["test_metrics"][card["selected"]]["macro_f1"],
                   social_accuracy=(found.get("Sentiment transfer to all social posts (hidden labels)") or [None])[0],
                   aspect_polarity=aspects[1] if len(aspects) > 1 else None)
        rows.append(row)
        print(f"{name:<20} {row['checks_passed']}/{row['checks_total']} checks | reviews F1 {row['review_macro_f1']:.3f} | "
              f"social accuracy {row['social_accuracy']} | aspect polarity {row['aspect_polarity']}"
              + (f" | failed: {', '.join(row['failed'])}" if row["failed"] else ""), flush=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Saved {(out / 'summary.json').relative_to(OUTPUTS.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
