#!/usr/bin/env python
"""Run a MarketMind market research study from the command line.

Examples:
    python run.py                                   # default brief, LLM if a key is configured
    python run.py --no-llm                          # fully offline, deterministic reasoning
    python run.py --brief "GlowNesia wants to ..." --client GlowNesia
    python run.py --retrain                         # force the deep-learning model to retrain
    python run.py --sentiment-data study+real       # also learn sentiment from real reviews (docs/DATA_SOURCES.md)
"""
from __future__ import annotations

import argparse
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

from marketmind.config import DEFAULT_BRIEF
from marketmind.system import MarketResearchSystem


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
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    brief = args.brief_file.read_text(encoding="utf-8") if args.brief_file else (args.brief or DEFAULT_BRIEF)
    system = MarketResearchSystem(brief=brief, client=args.client, use_llm=not args.no_llm,
                                  force_retrain=args.retrain, parallel=not args.sequential, echo=not args.quiet,
                                  sentiment_data=args.sentiment_data)
    print(f"\nMarketMind run {system.run_id} - LLM: {system.llm.describe()}\n")
    res = system.run()
    bb = system.blackboard
    print("\n" + "=" * 78)
    print(f"Status: {res.status} in {res.seconds}s | QA score: {res.qa.get('score')} "
          f"({'passed' if res.qa.get('passed') else 'not passed'}) | findings: {len(bb.findings())}")
    for name, r in res.results.items():
        print(f"  {r.agent:<34} {r.status:<10} {r.seconds:>6.1f}s  {r.summary or r.error or ''}"[:150])
    recs = bb.get("strategy.recommendations") or []
    if recs:
        print("\nTop recommendations:")
        for r in recs[:5]:
            print(f"  {r['id']}. {r['title']}")
    print(f"\nOutputs: {res.run_dir}")
    print(f"  report: {res.run_dir / 'report.html'}")
    print("  dashboard: streamlit run app/dashboard.py")
    return 0 if res.status == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
