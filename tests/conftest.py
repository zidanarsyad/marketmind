"""Shared fixtures: one offline pipeline run per test session, written to a temporary folder."""
from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings("ignore")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from marketmind.config import DATA_RAW, DATASETS  # noqa: E402

DATA_READY = all((DATA_RAW / v["file"]).exists() for v in DATASETS.values())


@pytest.fixture(scope="session")
def offline_run(tmp_path_factory):
    """(system, result, RunData) for a full offline study saved outside outputs/."""
    if not DATA_READY:
        pytest.skip("run scripts/generate_data.py first")
    from marketmind import system as system_module
    from marketmind.core.llm import LLMClient
    from marketmind.core.store import RunData

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(system_module, "RUNS_DIR", tmp_path_factory.mktemp("runs"))
        system = system_module.MarketResearchSystem(use_llm=False, llm=LLMClient(provider="none"))
        result = system.run()
    meta = json.loads((result.run_dir / "run_meta.json").read_text(encoding="utf-8"))
    return system, result, RunData(run_id=result.run_id, path=result.run_dir, meta=meta)
