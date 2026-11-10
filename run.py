#!/usr/bin/env python
"""Run a MarketMind market research study from the command line.

Examples:
    python run.py                                   # default brief, LLM if a key is configured
    python run.py --no-llm                          # fully offline, deterministic reasoning
    python run.py --brief "GlowNesia wants to ..." --client GlowNesia
    python run.py --retrain                         # force the deep-learning model to retrain
    python run.py --sentiment-data study+real       # also learn sentiment from real reviews (docs/DATA_SOURCES.md)
    python run.py --approve                         # approve the plan and the recommendations yourself
    python run.py --agent-timeout 300 --max-llm-calls 20
    python run.py --data-dir data/real/tokopedia-2025 --client "<brand>"   # a study on imported real data
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
# MarketMind is imported inside main(), after --data-dir has chosen the data folder that its paths are built from


def main() -> int:
    ap = argparse.ArgumentParser(description="MarketMind - multi-agent market research system")
    ap.add_argument("--brief", help="research brief (free text)")
    ap.add_argument("--brief-file", type=Path, help="read the brief from a text file")
    ap.add_argument("--client", help="client brand (defaults to the brand named in the brief)")
    ap.add_argument("--no-llm", action="store_true", help="disable the LLM even if an API key is configured")
    ap.add_argument("--retrain", action="store_true", help="force retraining of the sentiment models")
    ap.add_argument("--sentiment-data", choices=["study", "study+real", "real"], default="study",
                    help="train the sentiment models on the study's reviews (default), on them plus the real reviews "
                         "in data/external/ulasan-beauty-products, or on the real reviews only")
    ap.add_argument("--sequential", action="store_true", help="run analysis agents one at a time")
    ap.add_argument("--quiet", action="store_true", help="do not stream the agent trace")
    ap.add_argument("--approve", action="store_true",
                    help="review the research plan and the recommendations at the terminal before the study goes on")
    ap.add_argument("--retries", type=int, default=1, help="extra attempts for an agent that fails (default 1)")
    ap.add_argument("--agent-timeout", type=float, help="time limit per agent in seconds (default 900)")
    ap.add_argument("--max-llm-calls", type=int, help="LLM calls allowed per run (default 40)")
    ap.add_argument("--max-llm-tokens", type=int, help="LLM tokens allowed per run (default 300,000)")
    ap.add_argument("--data-dir", type=Path,
                    help="study another data folder (with raw/ inside), e.g. one written by scripts/import_tokopedia.py")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if args.data_dir:
        if not (args.data_dir / "raw").is_dir():
            print(f"{args.data_dir} has no raw/ folder; give the folder that contains raw/ (and manifest.json).")
            return 2
        os.environ["MARKETMIND_DATA_DIR"] = str(args.data_dir.resolve())
    from marketmind.config import DATA_RAW, DEFAULT_BRIEF, DEFAULT_REAL_BRIEF, data_manifest
    from marketmind.core.approval import ConsoleApprover
    from marketmind.system import MarketResearchSystem

    default_brief = DEFAULT_REAL_BRIEF if data_manifest(DATA_RAW)["kind"] == "real" else DEFAULT_BRIEF
    brief = args.brief_file.read_text(encoding="utf-8") if args.brief_file else (args.brief or default_brief)
    system = MarketResearchSystem(brief=brief, client=args.client, use_llm=not args.no_llm,
                                  force_retrain=args.retrain, parallel=not args.sequential,
                                  echo=not args.quiet and not args.approve,  # keep the trace from burying the prompts
                                  sentiment_data=args.sentiment_data, approver=ConsoleApprover() if args.approve else None,
                                  retries=args.retries, agent_timeout=args.agent_timeout,
                                  budget={k: v for k, v in dict(llm_calls=args.max_llm_calls,
                                                                llm_tokens=args.max_llm_tokens).items() if v is not None})
    llm_text = system.llm.describe() if system.options["use_llm"] else "off (deterministic reasoning)"
    print(f"\nMarketMind run {system.run_id} - LLM: {llm_text}\n")
    res = system.run()
    bb = system.blackboard
    print("\n" + "=" * 78)
    qa = (f"QA score: {res.qa.get('score')} ({'passed' if res.qa.get('passed') else 'not passed'})" if res.qa
          else "no report: stopped by the reviewer" if res.status == "rejected" else "QA: not run, report unverified")
    print(f"Status: {res.status} in {res.seconds}s | {qa} | findings: {len(bb.findings())}")
    for a in bb.get("approvals", []):
        print(f"  Approval - {a['gate']}: {'approved' if a['approved'] else 'REJECTED'} by {a['reviewer']}"
              + (f", removed {', '.join(a['drop'])}" if a["drop"] else "") + (f" ({a['comment']})" if a["comment"] else ""))
    for a in bb.get("director.adaptations", []):
        print(f"  Follow-up - {a['agent']}: {a['action']} because {a['reason']} -> {a['status']}")
    for r in res.results.values():
        line = f"  {r.agent:<34} {r.status:<10} {r.seconds:>6.1f}s  {r.summary or r.error or ''}"
        print(line if r.error else line[:150])  # errors are printed in full
    recs = bb.get("strategy.recommendations") or []
    if recs:
        print("\nTop recommendations:")
        for r in recs[:5]:
            print(f"  {r['id']}. {r['title']}")
    print(f"\nOutputs: {res.run_dir}")
    if (res.run_dir / "report.html").exists():
        print(f"  report: {res.run_dir / 'report.html'}")
    print("  dashboard: streamlit run app/dashboard.py")
    return 0 if res.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
