"""MarketMind Research: the existing multi-agent research system, as the ecosystem's market-intelligence provider.

Its eleven pipeline agents (Research Director to Critic) produce a study; in the ecosystem an Insight Service Agent
sells the aggregated result of the latest study to Kirana: the concept's weekly demand at maturity (year-1 revenue
of the launch opportunity / price / 52 weeks), the season, the price elasticity and the target segment. Raw reviews,
social posts and survey answers stay inside, as the study's privacy rules require. With no saved study (a fresh
checkout, CI) it answers from documented defaults and says so.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from ..governance import Governance, Role
from ..world import PRICE
from .base import Agent, Enterprise

FEE = 75_000_000
DEFAULTS = {"base_weekly_units": 14_800, "launch_ramp": {"1": 0.55, "2": 0.75, "3": 0.90, "4": 0.95},
            "season": {"12": 1.08, "13": 1.08, "14": 1.22, "15": 1.22, "16": 1.12}, "weekly_growth": 0.01,
            "marketplace_share": 0.75, "price_elasticity": -1.29, "recommended_price_idr": PRICE,
            "target_segment": "Gentle Glow Seekers", "concept_top2box": 0.826}
PIPELINE = ("Research Director", "Data Collection", "Data Quality", "Market & Trend Analyst",
            "Competitive Intelligence", "Consumer Insight (BiGRU)", "Segmentation (K-Means)",
            "Demand Forecasting (gradient boosting)", "Strategy", "Report Writer", "Critic (QA)")


def study_intelligence(run_dir: Path | None) -> dict:
    """The aggregated figures of a saved study, falling back to the defaults for anything the study lacks."""
    intel = json.loads(json.dumps(DEFAULTS))
    if run_dir is None or not run_dir.is_dir():
        return {**intel, "source": "documented defaults (no saved study)"}
    try:
        kpis = json.loads((run_dir / "json" / "strategy.kpis.json").read_text(encoding="utf-8"))
        price = float(kpis.get("recommended_price_idr") or PRICE)
        opp = run_dir / "tables" / "strategy.opportunities.csv"
        rows = list(csv.DictReader(opp.open(encoding="utf-8"))) if opp.exists() else []
        launch = next((r for r in rows if r.get("id") == "OPP-2"), None)
        if launch and launch.get("value_idr"):
            intel["base_weekly_units"] = int(round(float(launch["value_idr"]) / price / 52, -2))
        intel.update({k: v for k, v in {"price_elasticity": kpis.get("elasticity"), "recommended_price_idr": price,
                                        "target_segment": kpis.get("target_segment"),
                                        "concept_top2box": kpis.get("concept_t2b")}.items() if v is not None})
        return {**intel, "source": f"MarketMind study {run_dir.name}"}
    except (OSError, ValueError, KeyError):
        return {**intel, "source": "documented defaults (the saved study could not be read)"}


class Research(Enterprise):
    key = "research"
    name = "MarketMind Research"
    industry = "Market research agency (multi-agent AI)"
    city = "Yogyakarta"
    accent, accent_dark = "#0b6e5f", "#3fbfa4"
    description = ("The MarketMind system: eleven agents that turn a brief into a certified market study; here it "
                   "sells the study's aggregated demand intelligence.")
    roles = (Role("Research Lead", "Owns studies and what they may share"),
             Role("Client Service", "Answers clients' requests", datasets=("intelligence", "client_contracts", "messages",
                                                                            "decisions"), hidden_fields=("fee_idr",)))
    modules = (("Studies", "The 11-agent pipeline and its saved runs"),
               ("Insight service", "Aggregated market intelligence for clients"))
    platform = {"database": "file-based run store (CSV and JSON per study) + SQLite log",
                "api": "REST + JSON (the MarketMind API) and this A2A endpoint", "units": "rupiah, units, shares",
                "time": "study date", "stack": "FastAPI on its own port"}
    governance = Governance(public=("services",), partner=("market_intelligence",), control=("market_intelligence",),
                            private=("reviews", "social posts", "survey responses"),
                            policies={"shares": "aggregated findings and forecasts only, never respondent-level data"})
    private_datasets = ()

    def __init__(self, data_dir, seed: int = 7, run: str | None = None):
        self.run = run
        super().__init__(data_dir, seed)

    def make_agents(self):
        return [Agent("insight_service", "Insight Service Agent", "service",
                      "Answers clients' requests for market intelligence from the latest certified study",
                      "aggregates the study's findings"),
                Agent("pipeline", "Research pipeline (11 agents)", "planning", ", ".join(PIPELINE), "see docs/AGENTS.md")]

    def _run_dir(self) -> Path | None:
        if not self.run:
            return None
        from marketmind.config import RUNS_DIR
        if self.run == "latest":
            runs = sorted((p for p in RUNS_DIR.glob("*") if (p / "json" / "strategy.kpis.json").exists()), reverse=True)
            return runs[0] if runs else None
        return RUNS_DIR / self.run

    def setup(self):
        self.intel = study_intelligence(self._run_dir())
        self.requests = 0
        self.store.insert("intelligence", {"item": "base weekly units", "value": self.intel["base_weekly_units"],
                                           "source": self.intel["source"]})
        for k in ("price_elasticity", "recommended_price_idr", "target_segment", "concept_top2box"):
            self.store.insert("intelligence", {"item": k, "value": str(self.intel.get(k)), "source": self.intel["source"]})

    def on_request_market_intelligence(self, m):
        self.requests += 1
        self.book(m.sender_enterprise, "intelligence fee", FEE)
        self.store.insert("client_contracts", {"week": self.now, "client": m.sender_enterprise, "service": "market intelligence",
                                               "study": self.intel["source"], "fee_idr": FEE})
        self.decide("insight_service", "Send Kirana the launch demand intelligence",
                    f"Aggregated figures from {self.intel['source']}; no respondent-level data leaves the agency.",
                    outputs={"base_weekly_units": self.intel["base_weekly_units"]}, refs=[m.message_id])
        return [self.reply(m, "insight_service", "INFORM", {**self.intel, "fee_idr": FEE}, task="market_intelligence")]

    def view(self):
        return {"services": ["market_intelligence"],
                "market_intelligence": {k: self.intel[k] for k in ("base_weekly_units", "price_elasticity", "source")}}

    def kpis(self):
        revenue = self.ledger_total("intelligence fee")
        return {"requests_served": self.requests, "source": self.intel["source"], "revenue_idr": round(revenue),
                "profit_idr": round(revenue)}
