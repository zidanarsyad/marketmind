"""Agentic behaviour: retries and time limits, the LLM budget, the human approval gates and adaptive re-dispatch.

The fast tests check each mechanism on small stand-in agents; one end-to-end study makes the market analyst fail
until the Research Director sends it back, while a reviewer drops a recommendation.
"""
from __future__ import annotations

import json
import threading
import time

import pytest

from marketmind.config import DATA_RAW, DATASETS
from marketmind.core.agent import OPEN_QUESTION, BaseAgent, RunContext
from marketmind.core.approval import ApprovalBroker, ConsoleApprover, Decision, StudyRejected, _limit, request_approval
from marketmind.core.blackboard import Blackboard
from marketmind.core.events import Tracer
from marketmind.core.findings import Finding
from marketmind.core.llm import LLMClient
from marketmind.core.orchestrator import Task, Workflow

DATA_READY = all((DATA_RAW / v["file"]).exists() for v in DATASETS.values())
CATALOG = dict(brands=["Aurelia Derma", "DewiSkin", "GlowNesia", "Kirana Beauty", "Lumière Lab", "Purabotanica"],
               categories=["Facial Wash", "Moisturizer", "Serum", "Sunscreen", "Toner"],
               channels=["Lazada", "Offline Retail", "Shopee", "TikTok Shop", "Tokopedia"],
               first_month="2023-01-01", last_month="2026-10-01", datasets={})


def context(tmp_path, approver=None, llm=None, **options) -> RunContext:
    return RunContext("test", Blackboard(), Tracer("test"), llm or LLMClient(provider="none"), tmp_path, options,
                      approver=approver)


def events(ctx, kind):
    return [e for e in ctx.tracer.snapshot() if e.kind == kind]


# ------------------------------------------------------------------------------- retries and time limits
def test_a_failing_agent_is_retried_and_a_persistent_failure_is_reported(tmp_path):
    class Flaky(BaseAgent):
        name, calls = "Flaky agent", 0

        def execute(self):
            type(self).calls += 1
            if type(self).calls == 1:
                raise RuntimeError("transient glitch")
            return "done"

    class Broken(BaseAgent):
        name = "Broken agent"

        def execute(self):
            raise RuntimeError("always broken")

    ctx = context(tmp_path)
    res = Workflow([Task("flaky", Flaky), Task("broken", Broken, critical=False)]).run(ctx)
    assert res["flaky"].status == "completed" and res["flaky"].attempts == 2
    assert res["broken"].status == "failed" and res["broken"].attempts == 2 and "always broken" in res["broken"].error
    assert sum("retrying" in e.message for e in events(ctx, "warning")) == 2


def test_an_agent_over_its_time_limit_stops_at_its_next_tool_call_and_is_not_retried(tmp_path):
    class Slow(BaseAgent):
        name = "Slow agent"

        def register_tools(self):
            self.tool("wait", lambda: time.sleep(0.3), "wait a little")

        def execute(self):
            for _ in range(5):
                self.use("wait")
            return "never"

    t0 = time.time()
    res = Workflow([Task("slow", Slow, timeout=0.5)]).run(context(tmp_path))["slow"]
    assert res.status == "failed" and res.error.startswith("AgentTimeout") and res.attempts == 1
    assert time.time() - t0 < 1.5     # stopped after two tool calls, not five


def test_the_llm_budget_stops_llm_calls_and_falls_back(tmp_path):
    class CountingLLM(LLMClient):
        def __init__(self):
            super().__init__(provider="none")
            self.provider = "fake"

        @property
        def available(self) -> bool:
            return True

        def complete(self, system, prompt, max_tokens=1200, json_mode=False, temperature=0.3, agent=""):
            self.stats.calls += 1
            return "a sentence"

    class Writer(BaseAgent):
        name = "Writer"

    ctx = context(tmp_path, llm=CountingLLM(), budget=dict(llm_calls=2))
    agent = Writer(ctx)
    answers = [agent.ask_llm("write", {}) for _ in range(3)]
    assert answers == ["a sentence", "a sentence", None] and ctx.llm.stats.calls == 2
    assert any("budget" in e.message for e in events(ctx, "warning"))


# ------------------------------------------------------------------------------- approval gates
def test_console_reviewer_approves_trims_or_rejects():
    answers = iter(["pricing, forecast", "keep it lean", "n", "too risky"])
    reviewer = ConsoleApprover(reviewer="tester", ask=lambda prompt: next(answers), say=lambda text: None)
    plan = dict(client="Kirana Beauty", modules=["market", "pricing"], questions=[dict(id="Q1", area="market", question="?")])
    d = reviewer("plan", plan)
    assert d.approved and d.drop == ["pricing", "forecast"] and d.comment == "keep it lean"
    d = reviewer("recommendations", dict(recommendations=[dict(id="R1", title="t", priority=1.0, evidence=["X-01"])]))
    assert not d.approved and d.comment == "too risky"


def test_decisions_are_traced_and_recorded_and_a_broken_review_screen_stops_the_study(tmp_path):
    ctx = context(tmp_path, approver=lambda gate, proposal: Decision(True, "tester", drop=["R2"]))
    assert request_approval(ctx, "recommendations", {}, "Strategy Agent").drop == ["R2"]
    ctx.approver = lambda gate, proposal: 1 / 0
    d = request_approval(ctx, "plan", {}, "Research Director")   # fails closed: no approval on the reviewer's behalf
    assert not d.approved and d.reviewer == "review screen error" and "ZeroDivisionError" in d.comment
    assert [a["gate"] for a in ctx.blackboard.get("approvals")] == ["recommendations", "plan"]
    assert len(events(ctx, "approval")) == 2


def test_the_dashboard_broker_hands_a_gate_to_another_thread():
    broker, out = ApprovalBroker(), {}
    worker = threading.Thread(target=lambda: out.update(d=broker("plan", {"client": "X"})))
    worker.start()
    for _ in range(100):
        if broker.pending:
            break
        time.sleep(0.01)
    assert broker.pending == ("plan", {"client": "X"})
    broker.decide(Decision(False, "dashboard reviewer", "wrong client"))
    worker.join(2)
    assert not out["d"].approved and out["d"].comment == "wrong client" and broker.pending is None
    unanswered = ApprovalBroker(timeout=0.05)("plan", {})   # nobody answers: the study stops, and the record says why
    assert not unanswered.approved and unanswered.reviewer == "the 0.05-second time limit"
    assert unanswered.comment == "no reviewer answered, so the study stopped instead of going ahead unreviewed"
    assert ApprovalBroker(timeout=1800).timeout == 1800 and _limit(1800) == "30-minute"


def test_the_plan_gate_leaves_out_modules_and_renumbers_the_questions(tmp_path):
    from marketmind.agents.director import ResearchDirectorAgent
    ctx = context(tmp_path, approver=lambda gate, proposal: Decision(True, "tester", drop=["segmentation", "forecast"]))
    director = ResearchDirectorAgent(ctx)
    ctx.blackboard.put("plan", director._rule_plan("Grow Kirana Beauty", CATALOG))
    assert director.review_plan().approved
    plan = ctx.blackboard.get("plan")
    assert not plan["modules"]["segmentation"] and not plan["modules"]["pricing"]   # pricing needs segmentation
    assert not plan["modules"]["forecast"] and plan["modules"]["market"]
    assert [q["id"] for q in plan["questions"]] == [f"Q{i + 1}" for i in range(len(plan["questions"]))]
    assert {q["area"] for q in plan["questions"]} == {"market", "competition", "consumer", "strategy"}
    ctx.approver = lambda gate, proposal: Decision(False, "tester", "not now")
    assert not director.review_plan().approved


def test_the_recommendation_gate_drops_renumbers_reuses_and_rejects(tmp_path):
    from marketmind.agents.strategist import StrategyAgent
    asked = []

    def reviewer(gate, proposal):
        asked.append(gate)
        return Decision(True, "tester", "not this year", drop=["R2"])

    ctx = context(tmp_path, approver=reviewer)
    recs = lambda: [dict(id=f"R{i}", title=f"Play {i}", priority=1.0, horizon="Quick win", evidence=["CMP-01"])  # noqa: E731
                    for i in (1, 2, 3, 4)]
    kept = StrategyAgent(ctx)._seek_approval(recs())
    assert [(r["id"], r["title"]) for r in kept] == [("R1", "Play 1"), ("R2", "Play 3"), ("R3", "Play 4")]
    assert ctx.blackboard.get("strategy.rejected_recommendations")[0]["title"] == "Play 2"
    assert [r["title"] for r in StrategyAgent(ctx)._seek_approval(recs())] == ["Play 1", "Play 3", "Play 4"]
    assert asked == ["recommendations"]            # unchanged recommendations: the earlier decision stands
    ctx.approver = lambda gate, proposal: Decision(False, "tester", "start over")
    changed = recs()[:3]
    with pytest.raises(StudyRejected, match="start over"):
        StrategyAgent(ctx)._seek_approval(changed)
    ctx.approver = lambda gate, proposal: Decision(True, "tester", drop=["R1", "R2"])
    with pytest.raises(StudyRejected, match="every recommendation"):    # nothing left to deliver
        StrategyAgent(ctx)._seek_approval(recs()[:2])


# ------------------------------------------------------------------------------- adaptive re-dispatch
def test_the_director_traces_open_questions_and_missing_sections_to_agents(tmp_path):
    from marketmind.agents.director import ResearchDirectorAgent
    from marketmind.core.agent import AgentResult
    ctx = context(tmp_path)
    director = ResearchDirectorAgent(ctx)
    ctx.blackboard.put("plan", director._rule_plan("Grow Kirana Beauty", CATALOG))
    area = {q["area"]: q["id"] for q in ctx.blackboard.get("plan")["questions"]}
    qa = dict(checks=dict(coverage=dict(unanswered=[area["consumer"], area["pricing"], area["strategy"]]),
                          structure=dict(missing=["Market Overview", "Executive Summary"])))
    results = dict(consumer=AgentResult("Consumer", "failed"), segmentation=AgentResult("Seg", "completed"),
                   market=AgentResult("Market", "completed"))
    todo = director.follow_up_plan(qa, results, {"market", "consumer", "segmentation", "forecast", "strategy"})
    assert set(todo) == {"consumer", "segmentation", "forecast", "market"}   # nothing for strategy or the summary
    assert todo["consumer"]["failed"] and not todo["segmentation"]["failed"] and todo["forecast"]["failed"]
    assert [q["area"] for q in todo["segmentation"]["questions"]] == ["pricing"]
    assert todo["market"] == dict(questions=[], sections=["Market Overview"], failed=False)


def test_an_agent_sent_back_answers_from_its_findings_or_reports_an_open_question(tmp_path):
    class Analyst(BaseAgent):
        name, finding_prefix = "Market & Trend Analyst", "MKT"

    ctx = context(tmp_path)
    bb = ctx.blackboard
    q1 = dict(id="Q1", area="market", question="How large is the market?")
    q2 = dict(id="Q2", area="competition", question="Who is the biggest threat?")
    bb.add_finding(Finding("MKT-01", Analyst.name, "market", "Size", "The market is large."))
    for q in (q1, q2):
        bb.post("Research Director", Analyst.name, f"Answer {q['id']}", question=q)
    res = Analyst(ctx).run_follow_up()
    assert res.status == "completed" and "Q1 is answered by MKT-01" in res.summary
    open_q = {f.id: f for f in bb.findings()}["MKT-92"]
    assert OPEN_QUESTION in open_q.tags and open_q.area == "competition" and open_q.metrics["question"] == "Q2"
    assert [m.recipient for m in bb.messages()][-2:] == ["Research Director", "Research Director"]
    assert Analyst(ctx).run_follow_up().summary == "no open requests"     # each question is answered once


def test_the_critic_gives_half_credit_to_open_questions(tmp_path):
    from marketmind.agents.critic import QualityAssuranceAgent
    ctx = context(tmp_path)
    bb = ctx.blackboard
    bb.put("plan", dict(modules={}, questions=[dict(id="Q1", area="market", question="?"),
                                                dict(id="Q2", area="consumer", question="?")]))
    bb.add_finding(Finding("MKT-01", "M", "market", "t", "s"))
    bb.add_finding(Finding("CON-92", "C", "consumer", "Open question: Q2", "s", tags=[OPEN_QUESTION]))
    _, coverage, _ = QualityAssuranceAgent(ctx)._structure("## Executive Summary\nsimulated limitations")
    assert coverage["open"] == ["Q2"] and coverage["unanswered"] == [] and coverage["score"] == 0.75
    assert not coverage["issues"]


# ------------------------------------------------------------------------------- end to end
@pytest.mark.slow
@pytest.mark.skipif(not DATA_READY, reason="run scripts/generate_data.py first")
def test_the_director_sends_a_failed_agent_back_and_the_reviewer_shapes_the_plan(tmp_path, monkeypatch):
    import pandas as pd

    from marketmind import system as system_module
    from marketmind.agents.data_collector import DataCollectionAgent
    from marketmind.agents.market_analyst import MarketTrendAnalystAgent

    # The Data Collector's macro finding (MAC-01) keeps the market question answered while the market agent is down,
    # so the Director asks only for the missing section. MAC-01 needs World Bank data, which the GitHub runner could
    # not fetch (and the cache in data/external/ is not committed): give it fixed figures instead of the live API.
    macro = pd.DataFrame([dict(indicator="Population", code="SP.POP.TOTL", unit="people", year=2025, value=285_721_236.0),
                          dict(indicator="Internet users", code="IT.NET.USER.ZS", unit="% of population", year=2024, value=72.8)])
    monkeypatch.setattr(DataCollectionAgent, "_fetch_world_bank", lambda self: (macro, "fixed figures for this test"))
    original, calls = MarketTrendAnalystAgent.execute, []

    def fails_twice(self):              # the first attempt and the workflow's retry fail; the Director's re-dispatch works
        calls.append(1)
        if len(calls) <= 2:
            raise RuntimeError("market data service unavailable")
        return original(self)

    proposals = []

    def reviewer(gate, proposal):
        proposals.append((gate, proposal))
        return Decision(True, "test reviewer", "focus", drop=["R2"]) if gate == "recommendations" else Decision(True, "test reviewer")

    monkeypatch.setattr(MarketTrendAnalystAgent, "execute", fails_twice)
    monkeypatch.setattr(system_module, "RUNS_DIR", tmp_path)
    system = system_module.MarketResearchSystem(use_llm=False, llm=LLMClient(provider="none"), approver=reviewer)
    res = system.run()
    bb = system.blackboard

    assert res.status == "completed" and len(calls) == 3
    assert res.results["market"].status == "failed" and res.results["market"].attempts == 2
    assert res.results["market_followup"].status == "completed"
    assert all(res.results[k].status == "completed" for k in ("strategy_followup", "report_followup", "qa_followup"))
    (adaptation,) = bb.get("director.adaptations")
    assert adaptation["action"] == "re-dispatched" and adaptation["sections"] == ["Market Overview"]
    assert any(m.content.startswith("Re-run your analysis") for m in bb.inbox(MarketTrendAnalystAgent.name))
    assert {f.id for f in bb.findings()} >= {"MKT-01", "MKT-03"} and res.qa["passed"]
    # the reviewer saw the plan, then each new set of recommendations, and R2 of the last one is gone
    gates = [g for g, _ in proposals]
    assert gates[0] == "plan" and set(gates[1:]) == {"recommendations"}
    last = proposals[-1][1]["recommendations"]
    final = bb.get("strategy.recommendations")
    assert len(final) == len(last) - 1 and last[1]["title"] not in {r["title"] for r in final}
    report = (res.run_dir / "report.md").read_text(encoding="utf-8")
    assert "Market Overview" in report and "Adaptive coordination" in report and "test reviewer" in report
    meta = json.loads((res.run_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["adaptations"] == bb.get("director.adaptations") and meta["approvals"][0]["gate"] == "plan"


@pytest.mark.slow
@pytest.mark.skipif(not DATA_READY, reason="run scripts/generate_data.py first")
def test_a_rejected_plan_stops_the_study_before_any_analysis(tmp_path, monkeypatch):
    from marketmind import system as system_module
    monkeypatch.setattr(system_module, "RUNS_DIR", tmp_path)
    system = system_module.MarketResearchSystem(use_llm=False, llm=LLMClient(provider="none"),
                                                approver=lambda gate, proposal: Decision(False, "test reviewer", "wrong scope"))
    res = system.run()
    assert res.status == "rejected" and set(res.results) == {"plan"}
    meta = json.loads((res.run_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "rejected" and meta["approvals"][0]["comment"] == "wrong scope"
    assert not (res.run_dir / "report.md").exists()
