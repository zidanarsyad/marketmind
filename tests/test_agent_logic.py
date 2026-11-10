"""Unit tests for the agents' core logic, on small synthetic inputs whose right answer is known.

Each test pins down one method: the Critic's number checking and citation checks, the workflow's skip
rules, the Van Westendorp price points, the elasticity regression, the complaint-spike detector, the threat
index, label cleaning, price scenarios and the Strategy agent's priority rule.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from marketmind.core.agent import BaseAgent, RunContext
from marketmind.core.blackboard import Blackboard
from marketmind.core.events import Tracer
from marketmind.core.findings import Finding
from marketmind.core.llm import LLMClient


def context(tmp_path, run_id: str = "20990101-000000") -> RunContext:
    return RunContext(run_id, Blackboard(), Tracer(run_id), LLMClient(provider="none"), tmp_path, {})


# ---------------------------------------------------------------- Critic
def test_critic_parses_numbers_with_their_written_precision():
    from marketmind.agents.critic import _numbers
    assert _numbers("Revenue rose 1,234.5 units, then fell -3 points; Macro-F1 has no number") == [
        (1234.5, 1, "1,234.5"), (-3.0, 0, "-3")]


def test_critic_grounds_numbers_at_their_written_precision(tmp_path):
    from marketmind.agents.critic import QualityAssuranceAgent, _expand
    evidence = [0.1234, 38300.0, 1_234_000_000.0, 0.8213]
    allowed = sorted(set().union(*(_expand(v) for v in evidence)))
    md = "\n".join([
        "## Results for 888 brands",                 # headings, tables and quotes are not checked
        "| 777 | a table cell |",
        "> 555 in a quote",
        "Share is 12.3% this year.",                  # 0.1234 as a percentage
        "The market is worth Rp 38.3 trillion.",      # 38,300 billion rupiah
        "Revenue reached Rp 1.2 billion.",            # 1,234,000,000 rupiah, written to one decimal
        "Macro-F1 is 0.82.",                          # 0.8213 to two decimals
        "In 2025, 3 brands grew.",                    # years and small counts always pass
        "LLM support: `groq / qwen/qwen3.8-27b`.",    # code spans are identifiers, not claims
        "Macro-F1 is 0.84 and 999 stores opened.",    # neither is in the evidence
        "<!-- llm:exec_summary -->Sales will hit 4,321 units.<!-- /llm -->",
    ])
    result = QualityAssuranceAgent(context(tmp_path))._grounding(md, allowed)
    assert (result["checked"], result["grounded"]) == (9, 6)
    issues = {i["severity"]: i for i in result["issues"]}
    assert set(issues) == {"critical", "major"}
    assert issues["critical"]["block"] == "exec_summary" and "4,321" in issues["critical"]["message"]
    assert issues["major"]["block"] is None
    assert "0.84" in issues["major"]["message"] and "999" in issues["major"]["message"]


def test_critic_flags_invented_citations_and_unevidenced_recommendations(tmp_path):
    from marketmind.agents.critic import QualityAssuranceAgent
    ctx = context(tmp_path)
    ctx.blackboard.add_finding(Finding(id="CMP-02", agent="x", area="competition", title="t", statement="A real finding."))
    ctx.blackboard.put("strategy.recommendations", [dict(id="R1", evidence=["CMP-02"]), dict(id="R2", evidence=["XYZ-99"])])
    md = "Known [CMP-02].\n<!-- llm:market -->Made up [MKT-42].<!-- /llm -->"
    citations, recs = QualityAssuranceAgent(ctx)._citations(md)
    assert citations["unknown"] == ["MKT-42"]
    assert any(i["severity"] == "critical" and i["block"] == "market" for i in citations["issues"])
    assert recs["unevidenced"] == ["R2"]
    assert any("minimum 3" in i["message"] for i in recs["issues"])     # only two recommendations


# ---------------------------------------------------------------- workflow
class _Fine(BaseAgent):
    name = "Fine"

    def execute(self) -> str:
        return "ok"


class _Broken(BaseAgent):
    name = "Broken"

    def execute(self) -> str:
        raise RuntimeError("down")


def test_workflow_skips_only_what_depends_on_a_failed_critical_task(tmp_path):
    from marketmind.core.orchestrator import Task, Workflow
    wf = Workflow([Task("data", _Broken), Task("report", _Fine, ("data",)),
                   Task("analysis", _Broken, critical=False), Task("strategy", _Fine, ("analysis",)),
                   Task("other", _Fine)])
    results = wf.run(context(tmp_path), parallel=True)
    assert {k: r.status for k, r in results.items()} == {
        "data": "failed", "report": "skipped", "analysis": "failed", "strategy": "completed", "other": "completed"}
    assert "upstream failed" in results["report"].error


# ---------------------------------------------------------------- pricing
def test_van_westendorp_price_points_match_the_analytic_crossings():
    from marketmind.ml.pricing import van_westendorp
    rng = np.random.default_rng(7)
    n = 6000
    df = pd.DataFrame({col: rng.normal(mean, 20_000, n).clip(1_000) for col, mean in
                       (("too_cheap", 50_000), ("cheap", 70_000), ("expensive", 100_000), ("too_expensive", 130_000))})
    points, curves = van_westendorp(df, "too_cheap", "cheap", "expensive", "too_expensive")
    # with equal spreads each pair of normal curves crosses at the midpoint of their means
    for key, expected in (("pmc", 60_000), ("opp", 90_000), ("ipp", 85_000), ("pme", 115_000)):
        assert abs(points[key] - expected) < 1_500, (key, points[key])
    assert points["n"] == n and curves["too_cheap"].is_monotonic_decreasing


def test_curve_crossing_takes_the_middle_of_a_tied_stretch():
    from marketmind.ml.pricing import _cross
    x = np.arange(6.0)
    # clean sign change: linear interpolation
    assert _cross(x, np.array([1, .8, .6, .4, .2, 0]), np.array([0, .2, .4, .6, .8, 1])) == 2.5
    # both curves at zero from 2 to 3 (sparse tails): the middle of the tie, not its left end
    assert _cross(x, np.array([1, .5, 0, 0, 0, 0]), np.array([0, 0, 0, 0, .5, 1])) == 2.5
    assert np.isnan(_cross(x, np.ones(6), np.zeros(6)))


def test_price_bootstrap_reports_how_often_each_price_wins():
    from marketmind.agents.segmentation import recommend_price
    from marketmind.ml.pricing import van_westendorp, van_westendorp_bootstrap
    rng = np.random.default_rng(3)
    df = pd.DataFrame({col: rng.normal(mean, 15_000, 1500).clip(1_000) for col, mean in
                       (("a", 45_000), ("b", 70_000), ("c", 110_000), ("d", 145_000))})
    points, _ = van_westendorp(df, "a", "b", "c", "d")
    st = van_westendorp_bootstrap(df, "a", "b", "c", "d", recommend=recommend_price, n_boot=50)
    assert abs(sum(st["price_shares"].values()) - 1) < 0.01 and st["n_boot"] == 50
    assert st["opp_90"][0] <= points["opp"] <= st["opp_90"][1] and st["ipp_90"][0] <= points["ipp"] <= st["ipp_90"][1]
    assert recommend_price(points) in st["price_shares"]


def test_opp_tail_counts_show_how_many_answers_place_the_optimal_price():
    from marketmind.agents.segmentation import VW_COLS, opp_tail_counts
    df = pd.DataFrame({VW_COLS[0]: [40_000, 76_000, 80_000, 30_000], VW_COLS[1]: 0, VW_COLS[2]: 0,
                       VW_COLS[3]: [150_000, 82_000, 120_000, 84_000]})
    assert opp_tail_counts(df, 80_000) == (2, 2)          # too cheap at >= 76,000; too expensive at <= 84,000
    assert opp_tail_counts(df, float("nan")) == (0, 0)


def test_elasticity_regression_recovers_known_slopes():
    from marketmind.ml.pricing import estimate_elasticities
    rng = np.random.default_rng(11)
    truth = {"Alpha": -1.5, "Beta": -0.7}
    months = pd.date_range("2023-01-01", periods=36, freq="MS")
    rows = []
    for brand, elasticity in truth.items():
        for category in ("Serum", "Toner", "Sunscreen"):
            for channel in ("Shopee", "Offline Retail"):
                level = rng.normal(8, 0.5)
                for i, month in enumerate(months):
                    price_shock = rng.normal(0, 0.15)                    # promotions move the price
                    log_units = (level + 0.01 * i + 0.3 * (month.month == 4)   # trend and a seasonal peak
                                 + elasticity * price_shock + rng.normal(0, 0.05))
                    rows.append(dict(month=month, brand=brand, category=category, channel=channel,
                                     units=float(np.exp(log_units)), price=80_000 * float(np.exp(price_shock)), oos_frac=0.0))
    estimates, _ = estimate_elasticities(pd.DataFrame(rows))
    got = estimates.set_index("brand")
    for brand, elasticity in truth.items():
        assert abs(got.loc[brand, "elasticity"] - elasticity) < 0.1
        assert got.loc[brand, "std_err"] < 0.05
    assert (got.loc["Alpha", "interpretation"], got.loc["Beta", "interpretation"]) == ("elastic", "inelastic")


def test_price_scenarios_follow_the_constant_elasticity_formula():
    from marketmind.ml.pricing import price_scenarios
    row = price_scenarios(-1.5, 1e9, changes=[0.10]).iloc[0]
    assert row["volume_change_pct"] == pytest.approx((1.1 ** -1.5 - 1) * 100, abs=0.05)    # -13.3
    assert row["revenue_change_pct"] == pytest.approx((1.1 ** -0.5 - 1) * 100, abs=0.05)   # -4.7


@pytest.mark.parametrize("horizon", [3, 6, 12])
def test_forecast_growth_compares_the_same_months_a_year_earlier(horizon):
    """A flat market forecast to stay flat grows 0%, whatever the horizon (a 6-month brief once showed -50%)."""
    from marketmind.agents.forecaster import DemandForecastingAgent, comparison_window
    months = pd.date_range("2024-11-01", "2026-10-01", freq="MS")            # 24 actual months
    start, end = comparison_window(pd.Series(months), horizon)
    assert start == pd.Timestamp("2025-11-01")                              # 12 months before the first forecast month
    assert end == start + pd.DateOffset(months=horizon)
    rows = [dict(month=m, brand=b, category=c, units=10.0, revenue=100.0)
            for m in months for b in ("Alpha", "Beta") for c in ("Serum", "Toner")]
    panel = pd.DataFrame(rows)
    future = pd.date_range("2026-11-01", periods=horizon, freq="MS")
    fut = pd.DataFrame([dict(month=m, brand=b, category=c, units=10.0, revenue=100.0, horizon=i + 1)
                        for i, m in enumerate(future) for b in ("Alpha", "Beta") for c in ("Serum", "Toner")])
    agent = DemandForecastingAgent.__new__(DemandForecastingAgent)          # just the table logic, no run context
    agent.client, agent.horizon = "Alpha", horizon
    bt = dict(sigma=dict(market=0.1, brand=0.1), metrics={}, folds=[], detail=pd.DataFrame(), importance=pd.DataFrame())
    tables = agent._tables(panel, fut, bt, pd.DataFrame())
    brands = tables["forecast_summary_brand"].set_index("brand")
    assert brands.loc["Alpha", "revenue_last12"] == brands.loc["Alpha", "revenue_next12"] == 200.0 * horizon
    assert np.allclose(brands["revenue_growth"], 0.0)
    assert np.allclose(tables["forecast_summary_category"]["revenue_growth"], 0.0)
    assert np.allclose(tables["client_category_outlook"]["revenue_growth"], 0.0)


# ---------------------------------------------------------------- consumer insight
def test_complaint_spike_detector_finds_the_planted_episode_and_nothing_else(tmp_path):
    from marketmind.agents.consumer_insight import ConsumerInsightAgent
    months = [f"{y}-{m:02d}" for y in (2025, 2026) for m in range(1, 13)]
    scored = pd.DataFrame([dict(brand="Kirana Beauty", month=m) for m in months for _ in range(100)])
    rows = []
    for i, month in enumerate(months):
        for aspect, n in (("kemasan", 30 if 18 <= i <= 20 else 3), ("harga", 3)):   # packaging spikes Jul-Sep 2026
            rows += [dict(brand="Kirana Beauty", aspect=aspect, month=month, polarity="negative",
                          review_id=f"{aspect}-{month}-{j}") for j in range(n)]
    episodes = ConsumerInsightAgent(context(tmp_path))._anomalies(pd.DataFrame(rows), scored)
    assert len(episodes) == 1
    ep = episodes.iloc[0]
    assert (ep["aspect"], ep["start"], ep["end"], ep["months"]) == ("kemasan", "2026-07", "2026-09", 3)
    assert (ep["peak_rate"], ep["baseline_rate"]) == (30.0, 3.0)


# ---------------------------------------------------------------- competition
def test_threat_index_ranks_the_rival_that_leads_on_every_factor_first(tmp_path):
    from marketmind.agents.competitor_analyst import CompetitiveIntelligenceAgent
    agent = CompetitiveIntelligenceAgent(context(tmp_path))
    agent.client, agent.l12 = "Client", pd.Timestamp("2026-01-01")
    month = pd.Timestamp("2026-06-01")
    sales = pd.DataFrame([
        dict(month=month, brand="Client", category="Serum", channel="Shopee", revenue_idr=100.0),
        dict(month=month, brand="Close Rival", category="Serum", channel="Shopee", revenue_idr=120.0),
        dict(month=month, brand="Distant Rival", category="Toner", channel="Offline Retail", revenue_idr=20.0)])
    brands = ["Client", "Close Rival", "Distant Rival"]
    tables = {"brand_share": pd.DataFrame(dict(brand=brands, growth=[0.05, 0.30, -0.10], share_l12=[0.40, 0.45, 0.15],
                                               share_change_pp=[0.0, 3.0, -1.0])),
              "price_positioning": pd.DataFrame(dict(brand=brands, price_index=[1.0, 1.05, 3.0])),
              "share_of_voice": pd.DataFrame(dict(brand=brands, sov=[0.3, 0.5, 0.2]))}
    threats = agent._threats(sales, tables).set_index("brand")
    assert "Client" not in threats.index
    assert threats.loc["Close Rival", "rank"] == 1 and threats.loc["Close Rival", "threat_index"] == 1.0
    assert threats.loc["Distant Rival", "threat_index"] == 0.0


# ---------------------------------------------------------------- data quality
def test_label_variants_map_to_the_most_frequent_spelling():
    from marketmind.agents.data_quality import _canonical_labels
    labels = pd.Series(["Shopee"] * 50 + ["shopee "] * 3 + ["SHOPEE"] * 2 + ["TikTok Shop"] * 40 + ["Tiktok shop"] * 2
                       + ["TikTok"])
    mapping = _canonical_labels(labels)
    assert {mapping[v] for v in ("Shopee", "shopee ", "SHOPEE")} == {"Shopee"}
    assert {mapping[v] for v in ("TikTok Shop", "Tiktok shop")} == {"TikTok Shop"}
    assert mapping["TikTok"] == "TikTok Shop"      # a rare, truncated spelling joins the label it prefixes


# ---------------------------------------------------------------- strategy (on the shared pipeline run)
def test_recommendations_follow_the_priority_rule_and_cite_real_findings(offline_run):
    from marketmind.agents.strategist import EFFORT
    system, _, _ = offline_run
    recs = system.blackboard.get("strategy.recommendations")
    ids = {f.id for f in system.blackboard.findings()}
    assert [r["id"] for r in recs] == [f"R{i}" for i in range(1, len(recs) + 1)]
    assert [r["priority"] for r in recs] == sorted((r["priority"] for r in recs), reverse=True)
    for r in recs:
        assert r["evidence"] and set(r["evidence"]) <= ids
        # confidence is stored rounded to 2 decimals, so allow for that rounding
        assert r["priority"] == pytest.approx(r["impact"] * r["confidence"] * EFFORT[r["effort"]], abs=0.03)
        horizon = ("Quick win" if r["timeline"].startswith("0-3") else
                   "Core move" if r["timeline"].startswith(("0-6", "0-12")) else "Strategic bet")
        assert r["horizon"] == horizon
