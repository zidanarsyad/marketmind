#!/usr/bin/env python
"""Score a MarketMind run against the ground truth planted in the synthetic data.

    python scripts/evaluate_agents.py            # latest run
    python scripts/evaluate_agents.py 20261104-142242
"""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marketmind.core.store import list_runs, load_run  # noqa: E402
from marketmind.evaluation import evaluate  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    runs = list_runs()
    if not runs:
        print("No runs found - run `python run.py` first.")
        return 1
    run_id = sys.argv[1] if len(sys.argv) > 1 else runs[0]["run_id"]
    run = load_run(run_id)
    result = evaluate(run)
    if not result.get("available", True):
        print(f"Run {run_id}: {result['note']}")
        return 0
    (run.path / "evaluation.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Run {run_id}: {result['passed']}/{result['total']} ground-truth checks passed ({result['score']:.0%})\n")
    for c in result["checks"]:
        mark = "PASS" if c["passed"] else "FAIL"
        print(f"  [{mark}] {c['area']:<12} {c['check']:<52} expected {c['expected']:<38} found {c['found']}"
              + (f"  ({c['detail']})" if c["detail"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
