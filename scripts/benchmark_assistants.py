#!/usr/bin/env python
"""Benchmark the two on-demand agents: the ReAct Data Agent and the agentic-RAG Analyst Chat.

    python scripts/benchmark_assistants.py                 # offline: the rule-based policy and rule-based RAG steps
    python scripts/benchmark_assistants.py --llm           # also with the LLM configured in .env
    python scripts/benchmark_assistants.py --run 20261110-222212

ReAct Data Agent: 12 questions about the bundled datasets whose answers are computed here directly with pandas, so
each answer is scored against the truth (the right brand, channel or number in the answer), with whether it was
verified, the tool calls it took and the time.

Analyst Chat: 12 questions about a saved run, each with the evidence that answers it (finding IDs, a report section,
a method note or customer reviews). Scored by whether that evidence is among the first five sources, for the classic
single-shot retrieval the chat used before (findings and recommendations only) and for the agentic RAG loop; with an
LLM, also whether the written answer passed verification.

Results: outputs/assistants/summary.json (a copy is in docs/results/assistants.json).
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

import pandas as pd  # noqa: E402

from marketmind.config import DATA_RAW, OUTPUTS  # noqa: E402


def data_questions(t: dict[str, pd.DataFrame], client: str) -> list[dict]:
    """(question, the expected answer key, how to check it), with the truth computed straight from the tables."""
    s, r, so, sv, m = t["sales"], t["reviews"], t["social"], t["survey"], t["market_size"]
    y = s["month"].dt.year
    rev25 = s[y == 2025].groupby("channel")["revenue_idr"].sum()
    brand25 = s[y == 2025].groupby("brand")["revenue_idr"].sum()
    cl = s[s["brand"] == client].groupby(s["month"].dt.year)["revenue_idr"].sum()
    cat = s.groupby([s["month"].dt.year, "category"])["revenue_idr"].sum().unstack(0)
    cat_growth = (cat[2025] / cat[2024] - 1).sort_values(ascending=False)
    units25 = s[y == 2025].groupby("region")["units"].sum()
    rating = r.groupby("brand")["rating"].mean()
    text = r[r["review_text"].notna()]
    from marketmind.agents.data_tools import _mentions, search_terms
    from marketmind.ml.text import normalize
    groups = search_terms("packaging")
    packaging = int(text["review_text"].map(normalize).map(lambda x: all(_mentions(x, g) for g in groups)).sum())
    platform = so["platform"].value_counts(normalize=True)
    nps = sv.groupby("main_brand")["nps_main_brand"].mean()
    disc = s.groupby("channel")["discount_pct"].mean()
    market25 = m[m["year"] == 2025]["market_value_idr_bn"].sum()
    # an expected name must appear in the answer; an expected number must appear at the precision it is written at
    return [
        dict(q="Which channel had the highest revenue in 2025?", expect=[rev25.idxmax()]),
        dict(q="Which brand had the highest revenue in 2025?", expect=[brand25.idxmax()]),
        dict(q=f"How did {client}'s revenue change from 2024 to 2025?", expect=[(cl[2025] / cl[2024] - 1) * 100]),
        dict(q="What is each brand's share of revenue in 2025?",
             expect=[brand25.idxmax(), brand25.max() / brand25.sum() * 100]),
        dict(q="Which category grew fastest from 2024 to 2025?", expect=[cat_growth.index[0]]),
        dict(q="Which region sold the most units in 2025?", expect=[units25.idxmax()]),
        dict(q="Which brand has the highest average rating?", expect=[rating.idxmax()]),
        dict(q="How many reviews mention packaging?", expect=[float(packaging)]),
        dict(q="What share of social posts does each platform have?", expect=[platform.idxmax(), platform.max() * 100]),
        dict(q="Which main brand has the highest average NPS in the survey?", expect=[nps.idxmax()]),
        dict(q="Which channel has the highest average discount?", expect=[disc.idxmax()]),
        dict(q="How big was the market in 2025?", expect=[float(market25)]),
    ]


def contains(answer: str, expected) -> bool:
    """A name appears in the answer (ignoring case), or the number does, matched as core/grounding.py matches: within
    half a unit of its last written decimal or 0.5%, also in thousands to trillions (38.3 for 38,300), but without the
    free pass that check gives small integers and years."""
    if isinstance(expected, str):
        return expected.lower() in answer.lower()
    from marketmind.core.grounding import expand, numbers_in
    targets = [abs(t) for t in expand(float(expected))]
    for x, dec, _ in numbers_in(answer.replace("−", "-")):
        tol = 0.5 * 10 ** (-dec) + 1e-9
        if any(abs(abs(x) - t) <= max(tol, 0.005 * t) for t in targets):
            return True
    return False


RAG_QUESTIONS = [  # (question, evidence that answers it: IDs, or a prefix such as REV- or a report section title)
    ("What is our biggest problem right now?", ["CON-03", "CMP-02", "CON-06"]),
    ("Who is our biggest competitor?", ["CMP-05"]),
    ("How price-sensitive are our customers?", ["FCT-04"]),
    ("What price should we launch the new concept at?", ["SEG-04"]),
    ("Which consumer segment should we target first?", ["SEG-02"]),
    ("Which sales channel is growing fastest?", ["MKT-03", "CMP-02"]),
    ("What is the demand outlook for the next year?", ["FCT-01", "FCT-02"]),
    ("What do customers say about our packaging?", ["REV-", "CON-03"]),
    ("How did you estimate price elasticity?", ["DOC-3.8", "EVL-4.4"]),
    ("What are the limitations of this study?", ["report:Risks and Limitations"]),
    ("How accurate is the sentiment model?", ["CON-01", "EVL-4.1", "EVL-4.2"]),
    ("What should we do first?", ["R1"]),
]


def matches(source: dict, expected: list[str]) -> bool:
    for e in expected:
        if e.startswith("report:") and source.get("kind") == "report section" and e[7:] in source.get("title", ""):
            return True
        if e.endswith("-") and source["id"].startswith(e):
            return True
        if source["id"] == e or (e.startswith(("DOC-", "EVL-")) and source["id"].startswith(e)):
            return True
    return False


def run_data(llm, tables, client) -> list[dict]:
    from marketmind.agents.data_agent import ReActDataAgent
    agent = ReActDataAgent(llm=llm, tables=tables, client=client)
    rows = []
    for item in data_questions(tables, client):
        out = agent.answer(item["q"])
        correct = all(contains(out["answer"], e) for e in item["expect"])
        rows.append(dict(question=item["q"], expected=[e if isinstance(e, str) else round(float(e), 4) for e in item["expect"]],
                         correct=correct, verified=out["verified"],
                         tool_calls=sum(1 for s in out["steps"] if s["kind"] == "action"),
                         rejected_drafts=sum(1 for s in out["steps"] if s["kind"] == "check"),
                         seconds=out["seconds"], mode=out["mode"], answer=out["answer"][:400]))
        print(f"  [{'ok' if correct else '--'}] {item['q']} -> {out['answer'][:110]}", flush=True)
    return rows


def run_rag(llm, run) -> list[dict]:
    from marketmind.agents.analyst_chat import AnalystChatAgent
    chat = AnalystChatAgent(run, llm)
    rows = []
    for q, expected in RAG_QUESTIONS:
        classic = [dict(id=d["id"], kind=d["kind"], title=d["title"]) for d in chat.retrieve(q)][:5]
        t0 = time.time()
        out = chat.answer(q)
        top = out["sources"][:5]
        steps = [s["step"] for s in out["trace"]]
        rows.append(dict(question=q, expected=expected, classic_hit=any(matches(s, expected) for s in classic),
                         agentic_hit=any(matches(s, expected) for s in top), verified=out["verified"],
                         rewrites=steps.count("rewrite"), sources_searched=out["trace"][0].get("sources"),
                         seconds=round(time.time() - t0, 2), mode=out["mode"], top_sources=[s["id"] for s in top]))
        print(f"  classic {'ok' if rows[-1]['classic_hit'] else '--'} | agentic {'ok' if rows[-1]['agentic_hit'] else '--'}"
              f" | {q} -> {[s['id'] for s in top]}", flush=True)
    return rows


def summary(rows: list[dict], keys: list[str]) -> dict:
    n = len(rows)
    return dict(questions=n, **{k: sum(bool(r[k]) for r in rows) for k in keys},
                mean_seconds=round(sum(r["seconds"] for r in rows) / n, 2) if n else None)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--llm", action="store_true", help="also run with the LLM configured in .env")
    ap.add_argument("--run", help="the saved run for the chat questions (default: the newest completed run)")
    ap.add_argument("--rescore", action="store_true",
                    help="score the saved answers in outputs/assistants/summary.json again, without asking anything")
    args = ap.parse_args()

    from marketmind.agents.data_tools import load_tables
    from marketmind.core.llm import LLMClient
    from marketmind.core.store import list_runs, load_run
    if args.rescore:
        return rescore(load_tables(DATA_RAW.parent))
    run_id = args.run or next((r["run_id"] for r in list_runs() if r["status"] == "completed"), None)
    if run_id is None:
        print("No completed run found: run `python run.py` first.")
        return 1
    run = load_run(run_id)
    client = run.meta.get("client") or "Kirana Beauty"
    tables = load_tables(DATA_RAW.parent)
    modes = [("offline", LLMClient(provider="none"))]
    if args.llm:
        llm = LLMClient()
        if not llm.available:
            print(f"No LLM is configured ({llm.describe()}); running offline only.")
        else:
            modes.append((llm.describe(), llm))
    result = dict(run=run_id, client=client, modes={})
    for name, llm in modes:
        print(f"\nReAct Data Agent ({name})")
        data = run_data(llm, tables, client)
        print(f"\nAnalyst Chat ({name})")
        rag = run_rag(llm, run)
        result["modes"][name] = dict(
            react=dict(summary=summary(data, ["correct", "verified"]), rows=data),
            rag=dict(summary=summary(rag, ["classic_hit", "agentic_hit", "verified"]), rows=rag))
        print(f"\n{name}: ReAct {result['modes'][name]['react']['summary']}")
        print(f"{name}: RAG {result['modes'][name]['rag']['summary']}")
    save(result)
    return 0


def save(result: dict) -> None:
    out_dir = OUTPUTS / "assistants"
    out_dir.mkdir(parents=True, exist_ok=True)
    text = json.dumps(result, indent=2, ensure_ascii=False, default=str)
    (out_dir / "summary.json").write_text(text, encoding="utf-8")
    docs = Path(__file__).resolve().parents[1] / "docs" / "results"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "assistants.json").write_text(re.sub(r"\r\n", "\n", text), encoding="utf-8")
    print(f"\nWrote {out_dir / 'summary.json'} and docs/results/assistants.json")


def rescore(tables: dict) -> int:
    """Score the saved ReAct answers again with the current checker (the answers are kept, up to 400 characters)."""
    path = OUTPUTS / "assistants" / "summary.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    truth = {d["q"]: d["expect"] for d in data_questions(tables, result["client"])}
    for name, mode in result["modes"].items():
        rows = mode["react"]["rows"]
        for r in rows:
            expect = truth.get(r["question"], [])
            r["correct"] = bool(expect) and all(contains(r["answer"], e) for e in expect)
            r["expected"] = [e if isinstance(e, str) else round(float(e), 4) for e in expect]
        keep = {k: v for k, v in mode["react"]["summary"].items() if k == "mean_seconds"}
        mode["react"]["summary"] = dict(summary(rows, ["correct", "verified"]), **keep)
        print(f"{name}: ReAct {mode['react']['summary']}")
    save(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
