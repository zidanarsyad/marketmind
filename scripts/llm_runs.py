#!/usr/bin/env python
"""Run the study with real LLMs and measure what the language layer does, and what the Critic catches.

    python scripts/llm_runs.py                         # every provider with a key in .env
    python scripts/llm_runs.py --providers gemini groq

For each provider: a full study with the LLM on, then the Critic's first-pass verdict (score, issues, ungrounded
numbers it caught), the revisions needed, the final verdict, LLM calls, failures, models used and tokens, and the
25 ground-truth checks. What the Critic catches on the first pass is what would reach the report without it.
Results: outputs/llm_runs/summary.json (runs in outputs/llm_runs/runs). Responses are cached in outputs/cache/llm.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marketmind.config import OUTPUTS  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--providers", nargs="+", default=["gemini", "groq", "openrouter"])
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    from marketmind import system as system_module
    from marketmind.core.llm import LLMClient
    from marketmind.core.store import RunData
    from marketmind.evaluation import evaluate

    out = OUTPUTS / "llm_runs"
    system_module.RUNS_DIR = out / "runs"
    rows = []
    for provider in args.providers:
        llm = LLMClient(provider=provider)
        if not llm.available:
            print(f"{provider}: skipped ({llm.describe()})")
            continue
        t0 = time.time()
        system = system_module.MarketResearchSystem(use_llm=True, llm=llm)
        res = system.run()
        meta = json.loads((res.run_dir / "run_meta.json").read_text(encoding="utf-8"))
        ev = evaluate(RunData(run_id=res.run_id, path=res.run_dir, meta=meta))
        history = meta["qa"]["history"]
        first_issues = next((m.data.get("issues", []) for m in system.blackboard.messages()
                             if m.sender == "Critic Agent (QA)"), [])
        ungrounded = [i for i in first_issues if i["check"] == "grounding"]
        report = system.blackboard.get("report.markdown") or ""
        log = llm.stats.log
        row = dict(
            provider=provider, model=llm.model, fallback=llm.fallback_model, minutes=round((time.time() - t0) / 60, 1),
            status=res.status, checks_passed=ev["passed"], checks_total=ev["total"],
            llm_calls=llm.stats.calls, llm_failures=llm.stats.failures, cache_hits=llm.stats.cache_hits,
            prompt_tokens=llm.stats.prompt_tokens, completion_tokens=llm.stats.completion_tokens,
            models_used=sorted({e["model"] for e in log if e.get("model")}),
            planner=(system.blackboard.get("plan") or {}).get("planner"),
            first_pass_score=history[0]["score"] if history else None,
            first_pass_passed=history[0]["passed"] if history else None,
            first_pass_issues=len(first_issues), first_pass_grounding_issues=len(ungrounded),
            ungrounded_numbers_caught=sum(int(m.group(1)) for i in ungrounded
                                          for m in [re.match(r"(\d+) number", i["message"])] if m),
            revisions=meta["qa"]["revisions"], final_score=meta["qa"]["score"], final_passed=meta["qa"]["passed"],
            llm_blocks_in_final_report=report.count("<!-- llm:"),
            rejected_blocks=system.options.get("rejected_blocks", []),
            last_error=llm.last_error,
        )
        rows.append(row)
        print(f"{provider:<11} {row['llm_calls']} calls ({row['llm_failures']} failed) via {row['models_used'] or '-'} | "
              f"first QA {row['first_pass_score']} ({row['first_pass_issues']} issues, {row['ungrounded_numbers_caught']} "
              f"ungrounded numbers) -> {row['revisions']} revision(s) -> final QA {row['final_score']} | "
              f"{row['checks_passed']}/{row['checks_total']} checks | {row['minutes']} min", flush=True)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.json").write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
    print(f"Saved {(out / 'summary.json').relative_to(OUTPUTS.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
