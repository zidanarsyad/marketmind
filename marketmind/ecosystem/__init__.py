"""MarketMind's multi-enterprise ecosystem: six heterogeneous enterprises whose agents talk, negotiate and plan
together around Kirana Beauty's moisturizer launch, watched by a Global Agentic Control Center.

    python -m marketmind.ecosystem run --scenario stress      # both modes, in one process, KPIs compared
    python -m marketmind.ecosystem up                          # every enterprise on its own server, plus the Control Center

See docs/ECOSYSTEM.md for the case, the enterprises, the protocol, the planner and the scenarios.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from .engine import Ecosystem, HttpTransport, InProcessTransport, compare
from .enterprises import ENTERPRISES, ORDER, PORTS, create
from .world import MODES, SCENARIOS, scenario_info


def build(data_dir: Path | str, seed: int = 7, research_run: str | None = None) -> dict:
    """All six enterprises in this process, each with its own database under ``data_dir``."""
    return {k: create(k, data_dir, seed, research_run) for k in ORDER}


def run(scenario: str = "normal", mode: str = "ecosystem", seed: int = 7, data_dir: Path | str | None = None,
        research_run: str | None = None) -> dict:
    """Simulate one season in this process and return its summary (KPIs, plans, negotiations, messages)."""
    if data_dir is None:
        data_dir = Path(tempfile.mkdtemp(prefix="marketmind-ecosystem-"))
    enterprises = build(data_dir, seed, research_run)
    try:
        return Ecosystem(InProcessTransport(enterprises), scenario, mode, seed).run()
    finally:
        for e in enterprises.values():
            e.store.close()


__all__ = ["ENTERPRISES", "MODES", "ORDER", "PORTS", "SCENARIOS", "Ecosystem", "HttpTransport", "InProcessTransport",
           "build", "compare", "run", "scenario_info"]
