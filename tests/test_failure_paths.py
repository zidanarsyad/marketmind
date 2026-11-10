"""Failure paths: MarketMind degrades gracefully and says so, instead of crashing or staying silent.

Fast unit tests cover each safeguard on its own; one end-to-end run makes an analysis agent and the Critic
crash and checks that the study still completes, honestly marked as unverified.
"""
from __future__ import annotations

import json

import pytest
import requests

from marketmind.config import DATA_RAW, DATASETS, ROOT
from marketmind.core.agent import RunContext
from marketmind.core.blackboard import Blackboard
from marketmind.core.events import Tracer
from marketmind.core.llm import LLMClient

DATA_READY = all((DATA_RAW / v["file"]).exists() for v in DATASETS.values())
needs_data = pytest.mark.skipif(not DATA_READY, reason="run scripts/generate_data.py first")
CATALOG = dict(brands=["Aurelia Derma", "DewiSkin", "GlowNesia", "Kirana Beauty", "Lumière Lab", "Purabotanica"],
               categories=["Facial Wash", "Moisturizer", "Serum", "Sunscreen", "Toner"],
               channels=["Lazada", "Offline Retail", "Shopee", "TikTok Shop", "Tokopedia"],
               first_month="2023-01-01", last_month="2026-10-01", datasets={})


def context(tmp_path, llm: LLMClient | None = None, **options) -> RunContext:
    return RunContext("test", Blackboard(), Tracer("test"), llm or LLMClient(provider="none"), tmp_path, options)


def warnings_of(ctx: RunContext) -> list[str]:
    return [e.message for e in ctx.tracer.snapshot() if e.kind == "warning"]


def test_client_names_ignore_case_accents_and_spaces(tmp_path):
    from marketmind.agents.director import ResearchDirectorAgent
    for typed in ("lumiere lab", "  LUMIÈRE LAB ", "Lumière Lab"):
        plan = ResearchDirectorAgent(context(tmp_path, client=typed))._rule_plan("Grow the brand", CATALOG)
        assert plan["client"] == "Lumière Lab"


@needs_data
def test_unknown_client_stops_the_run_at_planning_with_a_clear_message(tmp_path):
    from marketmind.agents.director import ResearchDirectorAgent
    with pytest.raises(ValueError, match="Unknown client"):
        ResearchDirectorAgent(context(tmp_path, client="Glow Nation"))._rule_plan("Grow the brand", CATALOG)
    result = ResearchDirectorAgent(context(tmp_path, client="Glow Nation", brief="Grow the brand")).run()
    assert result.status == "failed" and "Kirana Beauty" in result.error   # the message lists the valid brands


@needs_data
def test_missing_dataset_is_skipped_with_a_warning(tmp_path, monkeypatch):
    from marketmind.agents import data_collector
    kept = DATASETS["catalog"]["file"]
    (tmp_path / kept).write_bytes((DATA_RAW / kept).read_bytes())
    monkeypatch.setattr(data_collector, "DATA_RAW", tmp_path)
    ctx = context(tmp_path)
    raw, catalog = data_collector.DataCollectionAgent(ctx)._load_internal()
    assert set(raw) == {"catalog"} and list(catalog["dataset"]) == ["catalog"]
    assert sum("is missing" in w for w in warnings_of(ctx)) == len(DATASETS) - 1


def test_world_bank_outage_falls_back_to_the_cache_then_to_nothing(tmp_path, monkeypatch):
    from marketmind.agents import data_collector

    def offline(*args, **kwargs):
        raise requests.ConnectionError("no network")

    monkeypatch.setattr(data_collector.requests, "get", offline)
    cache = tmp_path / "worldbank.json"
    cache.write_text(json.dumps(dict(fetched="2026-11-01 10:00", records=[
        dict(indicator="Population", code="SP.POP.TOTL", unit="people", year=2024, value=2.8e8)])), encoding="utf-8")
    monkeypatch.setattr(data_collector, "WB_CACHE", cache)
    ctx = context(tmp_path)
    agent = data_collector.DataCollectionAgent(ctx)
    macro, source = agent._fetch_world_bank()
    assert source.startswith("cached World Bank data") and len(macro) == 1
    cache.unlink()
    macro, source = agent._fetch_world_bank()
    assert source == "unavailable" and macro.empty
    assert sum("unreachable" in w for w in warnings_of(ctx)) == 2


def test_garbled_llm_output_keeps_the_rule_based_plan(tmp_path):
    from marketmind.agents.director import ResearchDirectorAgent

    class GarbledLLM(LLMClient):
        def __init__(self):
            super().__init__(provider="none")
            self.provider, self.model = "fake", "garbled"

        @property
        def available(self) -> bool:
            return True

        def complete(self, system, prompt, max_tokens=1200, json_mode=False, temperature=0.3, agent=""):
            return "Sure! Here is the refined plan: {objectives: [oops"

    ctx = context(tmp_path, llm=GarbledLLM())
    director = ResearchDirectorAgent(ctx)
    plan = director._rule_plan("Grow Kirana Beauty", CATALOG)
    assert director._llm_refine("Grow Kirana Beauty", CATALOG, plan) == plan
    assert any("deterministic reasoning" in w for w in warnings_of(ctx))


@pytest.mark.slow
@needs_data
def test_failed_analyst_and_critic_still_produce_an_honest_report(tmp_path, monkeypatch):
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource

    from marketmind import system as system_module
    from marketmind.agents.critic import QualityAssuranceAgent
    from marketmind.agents.market_analyst import MarketTrendAnalystAgent
    from marketmind.core.store import RunData
    from marketmind.sql_export import connect, create_schema, load_run

    def crash(self):
        raise RuntimeError("simulated crash")

    monkeypatch.setattr(MarketTrendAnalystAgent, "execute", crash)
    monkeypatch.setattr(QualityAssuranceAgent, "execute", crash)
    monkeypatch.setattr(system_module, "RUNS_DIR", tmp_path)
    system = system_module.MarketResearchSystem(use_llm=False, llm=LLMClient(provider="none"))
    res = system.run()

    # the study completes around the two failures, and is marked as not checked
    assert res.status == "unverified"
    assert res.results["market"].status == "failed" and "simulated crash" in res.results["market"].error
    assert res.results["qa"].status == "failed"
    assert all(res.results[k].status == "completed"
               for k in ("collect", "quality", "competition", "consumer", "segmentation", "forecast", "strategy", "report"))
    ids = {f.id for f in system.blackboard.findings()}
    assert not any(i.startswith("MKT-") for i in ids) and {"CMP-01", "CON-01", "SEG-02", "FCT-01"} <= ids
    assert len(system.blackboard.get("strategy.recommendations")) >= 3
    assert {e.agent for e in system.tracer.snapshot() if e.kind == "error"} == {MarketTrendAnalystAgent.name,
                                                                                 QualityAssuranceAgent.name}
    # the report and the saved run say so, and still meet their contracts
    assert "NOT VERIFIED" in (res.run_dir / "report.md").read_text(encoding="utf-8")
    assert "QA not run" in (res.run_dir / "report.html").read_text(encoding="utf-8")
    meta = json.loads((res.run_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == "unverified" and meta["qa"]["score"] is None
    schemas = [json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "docs" / "schemas").rglob("*.schema.json")]
    registry = Registry().with_resources([(s["$id"], Resource.from_contents(s)) for s in schemas])
    run_meta_schema = next(s for s in schemas if s["title"] == "RunMeta")
    assert not list(Draft202012Validator(run_meta_schema, registry=registry).iter_errors(meta))
    conn = connect(":memory:")
    create_schema(conn)
    conn.execute("INSERT INTO dim_brand (brand, is_client) VALUES (?, 1)", (meta["client"],))
    counts = load_run(conn, RunData(run_id=res.run_id, path=res.run_dir, meta=meta))
    assert conn.execute("SELECT status FROM run").fetchone()[0] == "unverified"
    assert counts["finding"] == len(ids) and counts["qa_check"] == 0
