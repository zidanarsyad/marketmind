"""The ground-truth evaluation and the Analyst Chat agent, on the shared offline run (tests/conftest.py).

The first test is a regression guard for the whole system: a change that stops the agents from finding a
planted market fact fails here, with the checks that broke listed.
"""
from __future__ import annotations

# On the bundled data the concept price is a known, documented miss (docs/EVALUATION.md, section 4.5): the planted
# optimum, Rp 89,900, sits just above the cut between Rp 79,900 and Rp 89,900, and the optimal price point rests on
# the one to three respondents in each tail near it, so misassigned respondents or noise decide which side it falls.
NOISY = "Recommended concept price"


def test_the_offline_run_recovers_every_planted_insight(offline_run):
    from marketmind.evaluation import evaluate
    _, _, run = offline_run
    result = evaluate(run)
    failed = [f"{c['area']}: {c['check']} (expected {c['expected']}, found {c['found']})"
              for c in result["checks"] if not c["passed"] and c["check"] != NOISY]
    assert result["total"] == 25 and not failed, failed
    price = next(c for c in result["checks"] if c["check"] == NOISY)
    if not price["passed"]:
        # the miss must be flagged: the pick is not settled and the runner-up lies inside the true band
        seg04 = {f.id: f for f in run.findings}["SEG-04"]
        assert seg04.metrics["price_settled"] is False and 80_000 <= seg04.metrics["alternative_price"] <= 100_000
        assert "not settled" in seg04.statement


def test_analyst_chat_answers_from_the_run_and_cites_its_sources(offline_run):
    from marketmind.agents.analyst_chat import AnalystChatAgent
    from marketmind.core.llm import LLMClient
    _, _, run = offline_run
    chat = AnalystChatAgent(run, llm=LLMClient(provider="none"))
    problem = chat.answer("What is our biggest problem?")
    assert problem["mode"] == "agentic RAG (offline)" and problem["sources"]
    top = problem["sources"][0]
    assert top["swot"] in ("W", "T") or "pain point" in top["tags"]
    assert f"[{top['id']}]" in problem["answer"]
    price = chat.answer("What price should we launch the concept at?")
    assert any(s["area"] == "pricing" or "concept" in s["tags"] for s in price["sources"][:3])
    nothing = chat.answer("qwerty zxcvb")
    assert nothing["sources"] == [] and "could not find evidence" in nothing["answer"]
