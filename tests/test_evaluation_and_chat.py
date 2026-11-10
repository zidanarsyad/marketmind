"""The ground-truth evaluation and the Analyst Chat agent, on the shared offline run (tests/conftest.py).

The first test is a regression guard for the whole system: a change that stops the agents from finding a
planted market fact fails here, with the checks that broke listed.
"""
from __future__ import annotations


def test_the_offline_run_recovers_every_planted_insight(offline_run):
    from marketmind.evaluation import evaluate
    _, _, run = offline_run
    result = evaluate(run)
    failed = [f"{c['area']}: {c['check']} (expected {c['expected']}, found {c['found']})"
              for c in result["checks"] if not c["passed"]]
    assert result["total"] == 25 and not failed, failed


def test_analyst_chat_answers_from_the_run_and_cites_its_sources(offline_run):
    from marketmind.agents.analyst_chat import AnalystChatAgent
    from marketmind.core.llm import LLMClient
    _, _, run = offline_run
    chat = AnalystChatAgent(run, llm=LLMClient(provider="none"))
    problem = chat.answer("What is our biggest problem?")
    assert problem["mode"] == "retrieval (offline)" and problem["sources"]
    top = problem["sources"][0]
    assert top["swot"] in ("W", "T") or "pain point" in top["tags"]
    assert f"[{top['id']}]" in problem["answer"]
    price = chat.answer("What price should we launch the concept at?")
    assert any(s["area"] == "pricing" or "concept" in s["tags"] for s in price["sources"][:3])
    nothing = chat.answer("qwerty zxcvb")
    assert nothing["sources"] == [] and "could not find evidence" in nothing["answer"]
