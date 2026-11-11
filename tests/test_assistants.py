"""The two on-demand agents: the agentic-RAG Analyst Chat and the ReAct Data Agent, on a small run built here.

The run has a handful of findings, recommendations and report sections, and a data folder with a small sales panel
and Indonesian reviews, so every expected answer is known exactly. A scripted model stands in for the LLM where the
loop's own behaviour is tested: a rejected draft, a bad tool call, a repeated call, an invented number.
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

from marketmind.core.llm import LLMClient

OFFLINE = LLMClient(provider="none")


class ScriptedLLM:
    """Stands in for LLMClient: replies with the next scripted answer for each kind of call."""

    available = True
    last_error = None

    def __init__(self, json_replies=(), text_replies=()):
        self.json_replies, self.text_replies = list(json_replies), list(text_replies)
        self.prompts: list[str] = []

    def describe(self) -> str:
        return "scripted / test-model"

    def complete_json(self, system, prompt, max_tokens=1500, agent=""):
        self.prompts.append(prompt)
        reply = self.json_replies.pop(0) if self.json_replies else None
        return reply(prompt) if callable(reply) else reply

    def complete(self, system, prompt, max_tokens=1200, json_mode=False, temperature=0.3, agent=""):
        self.prompts.append(prompt)
        return self.text_replies.pop(0) if self.text_replies else None


# ---------------------------------------------------------------------------------------------- the small study
def sales_panel() -> pd.DataFrame:
    rows = []
    for year, scale in ((2024, 1.0), (2025, 1.2)):
        for month in range(1, 13):
            for brand, b in (("Alpha", 1.0), ("Beta", 2.0)):
                for channel, c in (("Shopee", 3.0), ("Tokopedia", 1.0)):
                    units = int(100 * scale * b * c)
                    rows.append(dict(month=f"{year}-{month:02d}-01", brand=brand, category="Moisturizer", channel=channel,
                                     region="Jawa Barat", units=units, revenue_idr=units * 50_000, list_price_idr=55_000,
                                     avg_selling_price_idr=50_000, discount_pct=0.1, promo_flag=0, stockout_days=0))
    return pd.DataFrame(rows)


REVIEWS = [  # (brand, category, rating, text)
    ("Alpha", "Moisturizer", 2, "teksturnya lengket banget di muka"),
    ("Alpha", "Moisturizer", 2, "lengket dan berat, tidak meresap"),
    ("Alpha", "Moisturizer", 5, "teksturnya ringan dan cepat meresap, suka"),
    ("Alpha", "Moisturizer", 1, "pump rusak, kemasan bocor. hubungi 0812-3456-7890"),
    ("Alpha", "Moisturizer", 2, "kemasan bocor waktu sampai"),
    ("Beta", "Serum", 4, "wangi enak, harga murah"),
    ("Beta", "Serum", 5, "harga murah tapi bagus"),
    ("Beta", "Serum", 3, "biasa saja, wangi terlalu kuat"),
]


def reviews_table() -> pd.DataFrame:
    return pd.DataFrame([dict(review_id=f"R{i:06d}", review_date=f"2025-0{1 + i % 6}-1{i % 9}", brand=b, sku_id=f"SKU-{i}",
                              product_name=f"{b} {cat}", category=cat, channel="Shopee", region="Jawa Barat",
                              rating=r, review_text=t, helpful_votes=i, verified_purchase=True, reviewer_id=f"U{i}",
                              reviewer_skin_type="oily") for i, (b, cat, r, t) in enumerate(REVIEWS, start=1)])


@pytest.fixture
def study(tmp_path, monkeypatch):
    """A saved run (client Alpha) with its own data folder, loaded through the run store."""
    from marketmind.core import store
    from marketmind.core.blackboard import Blackboard
    from marketmind.core.events import Tracer
    from marketmind.core.findings import Finding

    data = tmp_path / "data" / "raw"
    data.mkdir(parents=True)
    sales_panel().to_csv(data / "market_sales_panel.csv", index=False)
    reviews_table().to_csv(data / "product_reviews.csv", index=False)
    bb = Blackboard()
    bb.add_finding(Finding("CON-03", "Consumer Insight Agent", "consumer", "Complaint spike: Packaging",
                           "Packaging complaints about Alpha spiked to 28.9 per 100 reviews in March 2025 (baseline 2.6).",
                           metrics=dict(peak=28.9, baseline=2.6), impact=5, confidence=0.9, swot="W",
                           tags=["pain point", "packaging"]))
    bb.add_finding(Finding("CMP-05", "Competitive Intelligence Agent", "competition", "Top competitive threat: Beta",
                           "Beta is the most serious competitive threat (threat index 0.80) with 66.7% of revenue.",
                           metrics=dict(threat_index=0.8, brand="Beta"), impact=4, confidence=0.8, swot="T",
                           tags=["threat", "competitor"]))
    bb.add_finding(Finding("FCT-04", "Demand Forecasting Agent", "pricing", "Alpha price elasticity",
                           "Alpha's demand is price-elastic (elasticity -1.29): a 5% price rise would cut revenue 1.4%.",
                           metrics=dict(elasticity=-1.29), impact=4, confidence=0.8, swot="W", tags=["price"]))
    bb.put("strategy.recommendations", [dict(id="R1", title="Fix the pump", action="Replace the pump supplier.",
                                             rationale="Packaging complaints spiked [CON-03].", kpi="Complaints back to 2.6",
                                             priority=4.2, evidence=["CON-03"])])
    bb.put("plan", dict(client="Alpha", competitors=["Beta"], categories=["Moisturizer", "Serum"]))
    bb.put("report.markdown", "# Alpha market research\n\n## 1. Executive Summary\nAlpha must fix its pump.\n\n"
                              "## 9. Risks and Limitations\nAll datasets are simulated for demonstration purposes. "
                              "The panel tracks two brands, not the whole market.\n")
    run_dir = tmp_path / "runs" / "r1"
    store.save_run(run_dir, bb, Tracer("r1"), dict(run_id="r1", client="Alpha", status="completed",
                                                   options=dict(data_dir=str(tmp_path / "data"))))
    monkeypatch.setattr(store, "RUNS_DIR", tmp_path / "runs")
    return store.load_run("r1")


@pytest.fixture
def tables(study):
    from marketmind.agents.data_tools import load_tables, run_data_dir
    return load_tables(run_data_dir(study))


# ---------------------------------------------------------------------------------------------- ReAct: the tools
def test_the_data_tools_compute_exact_answers_and_explain_wrong_arguments(tables):
    from marketmind.agents.data_tools import DataToolkit
    t = DataToolkit(tables)
    top = t.run("aggregate", dict(table="sales", measure="revenue_idr", by="channel", start="2025", end="2025")).data
    # 2025: Shopee 12 x (360 + 720) x 50,000, Tokopedia 12 x (120 + 240) x 50,000
    assert [(g["channel"], g["value"]) for g in top["groups"]] == [("Shopee", 648_000_000), ("Tokopedia", 216_000_000)]
    shares = t.run("share", dict(table="sales", measure="revenue_idr", by="brand")).data["groups"]
    assert [(g["brand"], g["share_pct"]) for g in shares] == [("Beta", 66.67), ("Alpha", 33.33)]
    growth = t.run("compare", dict(table="sales", measure="units", period_a="2024", period_b="2025")).data
    assert growth["change_pct"] == 20.0
    trend = t.run("trend", dict(table="sales", measure="units", freq="year")).data
    assert (trend["first"]["period"], trend["last"]["period"]) == ("2024", "2025")
    # English aspect words also match the Indonesian review text, which is masked for personal details
    texture = t.run("search_text", dict(query="texture", filters={"brand": "alpha"})).data
    assert texture["matches"] == 3 and texture["mean_rating"] == 3.0
    pump = t.run("search_text", dict(query="pump")).data
    assert pump["matches"] == 2 and "[phone]" in " ".join(e["text"] for e in pump["examples"])   # pump, kemasan
    assert t.run("calculate", dict(expression="(648 - 216) / 216 * 100")).data["value"] == 200.0
    for action, args, hint in [
        ("calculate", dict(expression="__import__('os').system('dir')"), "only numbers"),
        ("aggregate", dict(table="sales", measure="profit"), "has no column 'profit'"),
        ("aggregate", dict(table="sales", filters={"channel": "TikTok"}), "no rows where channel = 'TikTok'"),
        ("aggregate", dict(table="ledger"), "there is no table 'ledger'"),
        ("explode", {}, "there is no tool 'explode'"),
        ("aggregate", dict(table="sales", group="brand"), "wrong arguments"),
    ]:
        obs = t.run(action, args)
        assert obs.error and hint in obs.text, (action, obs.text)


# ---------------------------------------------------------------------------------------------- ReAct: the loop
def test_offline_the_rule_policy_answers_from_one_observation_and_cites_it(study):
    from marketmind.agents.data_agent import ReActDataAgent
    agent = ReActDataAgent(study, OFFLINE)
    top = agent.answer("Which channel had the highest revenue in 2025?")
    assert top["mode"] == "ReAct with rule-based policy (offline)" and top["verified"]
    assert top["steps"][0]["action"] == "aggregate" and top["steps"][-1]["kind"] == "answer"
    assert top["answer"].startswith("Shopee has the highest revenue in 2025: Rp 648.00 million") and "[O1]" in top["answer"]
    ours = agent.answer("How did our revenue change from 2024 to 2025?")    # "our" is the client, Alpha
    assert ours["steps"][0]["args"]["filters"] == {"brand": "Alpha"} and "+20.0% [O1]" in ours["answer"]
    talk = agent.answer("How many reviews mention packaging?")
    assert talk["steps"][0]["action"] == "search_text" and talk["answer"].startswith("2 of 8 reviews")
    lost = agent.answer("Tell me a joke")
    assert lost["steps"][0]["action"] == "list_tables" and "does not say which data" in lost["answer"]


def test_with_a_model_a_draft_with_an_invented_number_goes_back_until_it_is_grounded(study):
    from marketmind.agents.data_agent import ReActDataAgent
    llm = ScriptedLLM(json_replies=[
        {"thought": "I need revenue per channel in 2025.", "action": "aggregate",
         "args": {"table": "sales", "measure": "revenue_idr", "by": "channel", "start": "2025", "end": "2025"}},
        {"thought": "Shopee leads.", "answer": "Shopee leads with Rp 999 million in 2025 [O1]."},
        {"thought": "Use the observed value.", "answer": "Shopee leads with Rp 648 million of revenue in 2025 [O1]."},
    ])
    out = ReActDataAgent(study, llm).answer("Which channel sold most in 2025?")
    assert out["verified"] and out["mode"] == "ReAct with scripted / test-model"
    assert [s["kind"] for s in out["steps"]] == ["action", "check", "answer"]
    assert "999" in out["steps"][1]["observation"] and out["answer"].startswith("Shopee leads with Rp 648 million")
    assert "Observation O1" in llm.prompts[1]          # the model re-reads its observations at every step


def test_with_a_model_a_bad_call_is_corrected_and_a_repeated_call_is_refused(study):
    from marketmind.agents.data_agent import ReActDataAgent
    call = {"thought": "Units by brand.", "action": "aggregate", "args": {"table": "sales", "measure": "units", "by": "brand"}}
    llm = ScriptedLLM(json_replies=[
        {"thought": "Try a tool.", "action": "sql", "args": {"query": "select 1"}},
        call, call,
        {"thought": "O1 has it.", "answer": "Beta sold the most units [O1]."},
    ])
    out = ReActDataAgent(study, llm).answer("Which brand sold the most units?")
    errors = [s for s in out["steps"] if s.get("error")]
    assert "there is no tool 'sql'" in errors[0]["observation"] and "already made this exact call" in errors[1]["observation"]
    assert out["verified"] and out["answer"] == "Beta sold the most units [O1]."


def test_with_a_model_that_gives_no_usable_steps_the_rules_answer_and_say_so(study):
    from marketmind.agents.data_agent import ReActDataAgent
    out = ReActDataAgent(study, ScriptedLLM(json_replies=[None, "not json"])).answer("Which channel had the highest revenue?")
    assert out["mode"].startswith("ReAct with rule-based policy (the LLM gave no usable steps")
    assert out["answer"].startswith("Shopee has the highest revenue")


# ---------------------------------------------------------------------------------------------- agentic RAG
def test_offline_the_chat_plans_retrieves_grades_and_cites(study):
    from marketmind.agents.analyst_chat import AnalystChatAgent
    chat = AnalystChatAgent(study, OFFLINE)
    out = chat.answer("What is our biggest problem?")
    assert out["mode"] == "agentic RAG (offline)" and out["verified"]
    assert out["sources"][0]["id"] == "CON-03" and "[CON-03]" in out["answer"]
    assert [s["step"] for s in out["trace"]][:3] == ["plan", "retrieve", "grade"]
    limits = chat.answer("What are the limitations of this study?")
    assert limits["sources"][0]["id"].startswith("REP-9.") and "simulated" in limits["answer"]
    method = chat.answer("How did you estimate price elasticity?")
    assert "methods" in method["trace"][0]["sources"] and any(s["id"] == "FCT-04" for s in method["sources"])
    nothing = chat.answer("qwerty zxcvb")
    assert nothing["sources"] == [] and "could not find evidence" in nothing["answer"]


def test_a_weak_search_of_reviews_is_rewritten_with_indonesian_terms(study):
    from marketmind.agents.analyst_chat import AnalystChatAgent
    out = AnalystChatAgent(study, OFFLINE).answer("What do customers say about the texture of Alpha's moisturizer?")
    steps = [s["step"] for s in out["trace"]]
    assert "rewrite" in steps and "lengket" in next(s for s in out["trace"] if s["step"] == "rewrite")["query"]
    reviews = [s for s in out["sources"] if s["kind"] == "review"]
    assert reviews and all("Alpha review" in s["title"] for s in reviews)     # the brand the question named
    assert reviews[0]["id"].startswith("REV-R") and reviews[0]["id"] in out["answer"]


def test_a_follow_up_question_borrows_the_previous_one(study):
    from marketmind.agents.analyst_chat import AnalystChatAgent
    history = [dict(role="user", content="Who is our biggest competitor?"), dict(role="assistant", content="Beta.")]
    out = AnalystChatAgent(study, OFFLINE).answer("and why?", history)
    plan = out["trace"][0]
    assert plan["standalone"] == "Who is our biggest competitor? and why?" and "follow-up" in plan["detail"]
    assert out["sources"][0]["id"] == "CMP-05"


def test_with_a_model_an_answer_that_fails_verification_twice_is_replaced_by_the_evidence(study):
    from marketmind.agents.analyst_chat import AnalystChatAgent
    llm = ScriptedLLM(
        json_replies=[{"standalone": "What is Alpha's biggest problem?", "sub_questions": ["What is Alpha's biggest problem?"],
                       "sources": ["findings"]},
                      {"relevant": ["CON-03", "FCT-04"]}],
        text_replies=["Packaging complaints hit 77.7 per 100 reviews [CON-03].",
                      "Packaging complaints hit 28.9 per 100 reviews [CON-03] [XYZ-01]."])
    out = AnalystChatAgent(study, llm).answer("What is our biggest problem?")
    verifies = [s for s in out["trace"] if s["step"] == "verify"]
    assert len(verifies) == 2 and "77.7" in verifies[0]["detail"] and "XYZ-01" in verifies[1]["detail"]
    assert not out["verified"] and "failed verification" in out["mode"]
    assert out["answer"].startswith("Here is what the evidence says") and "[CON-03]" in out["answer"]
    assert "rejected" in llm.prompts[-1]          # the second draft was asked for with the reasons


def test_with_a_model_a_grounded_answer_is_released(study):
    from marketmind.agents.analyst_chat import AnalystChatAgent
    llm = ScriptedLLM(json_replies=[{"standalone": "Who threatens Alpha?", "sub_questions": ["Who threatens Alpha?"],
                                     "sources": ["findings"]}, {"relevant": ["CMP-05"]}],
                      text_replies=["Beta is the most serious threat, with a threat index of 0.80 [CMP-05]."])
    out = AnalystChatAgent(study, llm).answer("Who is our biggest competitor?")
    assert out["verified"] and out["answer"].startswith("Beta is the most serious threat")
    assert out["mode"] == "agentic RAG (scripted / test-model)"


# ---------------------------------------------------------------------------------------------- the API
def test_the_api_returns_the_chat_trace_and_the_data_agent_steps(study, tmp_path):
    from fastapi.testclient import TestClient

    from api.app import create_app
    from api.security import LOCAL_HOSTS
    app = create_app(llm=OFFLINE, frontend_dist=tmp_path / "no-build", allowed_hosts=LOCAL_HOSTS, token=None)
    c = TestClient(app, base_url="http://localhost")
    chat = c.post("/api/runs/r1/chat", json={"question": "What is our biggest problem?", "history": []}).json()
    assert chat["sources"][0]["id"] == "CON-03" and chat["trace"][0]["step"] == "plan" and chat["verified"] is True
    data = c.post("/api/runs/r1/ask-data", json={"question": "Which channel had the highest revenue in 2025?"}).json()
    assert data["verified"] and data["steps"][0]["action"] == "aggregate" and "[O1]" in data["answer"]
    assert json.dumps(data)                                   # strict JSON, nothing a browser cannot parse
    assert c.post("/api/runs/r1/ask-data", json={"question": ""}).status_code == 422
