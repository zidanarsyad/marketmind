"""End-to-end and unit tests for MarketMind.

Run with:  python -m pytest -q
The full-pipeline tests take ~1-2 minutes (the sentiment model is cached after the first run).
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

import pytest

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from marketmind.config import DATA_RAW, DATASETS  # noqa: E402
from marketmind.core.llm import LLMClient, parse_json  # noqa: E402
from marketmind.core.orchestrator import Task, Workflow  # noqa: E402
from marketmind.core.agent import BaseAgent  # noqa: E402
from marketmind.ml.calendar_id import eid_date, month_features  # noqa: E402
from marketmind.ml.text import detect_aspects, normalize, split_clauses  # noqa: E402

DATA_READY = all((DATA_RAW / v["file"]).exists() for v in DATASETS.values())


class FakeLLM(LLMClient):
    """Deterministic stand-in for a real provider. It writes an executive summary containing an invented
    number, so the Critic must catch it and the Director must trigger a revision."""

    def __init__(self):
        super().__init__(provider="none")
        self.provider, self.model = "fake", "fake-1"
        self.prompts = []

    @property
    def available(self) -> bool:
        return True

    def complete(self, system, prompt, max_tokens=1200, json_mode=False, temperature=0.3, agent=""):
        self.prompts.append((agent, prompt[:200]))
        if json_mode and "research plan" in prompt.lower():
            return ('{"objectives": ["Size the market", "Benchmark competitors", "Find pain points", '
                    '"Pick a target segment"], "questions": [], "concept": "Barrier moisturizer"}')
        if json_mode and "persona name" in prompt.lower():
            return "{}"
        if "executive summary" in prompt.lower():
            return "- The market will triple to Rp 999 trillion next year [MKT-01].\n- Fix packaging first [CON-03]."
        if "so what" in prompt.lower():
            return "This matters for the client because growth is concentrated in a few channels [MKT-03]."
        return "OK"


def test_text_normalisation_and_aspects():
    assert normalize("Bagusss bgt, gak lengket 😍") == "bagus banget tidak lengket emopos"
    clauses = split_clauses("Teksturnya ringan, tapi pump-nya rusak")
    assert len(clauses) == 2
    assert "kemasan" in detect_aspects("pump-nya rusak")
    assert "tekstur" in detect_aspects("teksturnya ringan")


def test_ramadan_calendar_features():
    # Ramadan 2026 runs 18 February - 19 March and Eid is 20 March. Of March's 31 days, 19 fall in Ramadan,
    # 14 of them in the two weeks before Eid (6-19 March), and 7 in the Eid holiday week (20-26 March).
    f = month_features("2026-03-01")
    assert (f["ramadan_share"], f["pre_eid_share"], f["post_eid_share"]) == (19 / 31, 14 / 31, 7 / 31)
    assert eid_date(2026).date().isoformat() == "2026-03-20"


def test_timedeltas_carry_an_explicit_unit():
    # Under pandas 2.3, pd.Timedelta(days=...) / (hours=...) builds a numpy timedelta without a unit, which numpy 2.5
    # deprecates. pyproject.toml turns that warning into an error, but only numpy 2.5 or later (CI) emits it, so this
    # scan catches the keyword form on any numpy.
    import re

    import pandas as pd

    from marketmind.agents.data_tools import period_bounds

    keyword_form = re.compile(r"Timedelta\(\s*(weeks|days|hours|minutes|seconds|milliseconds|microseconds)\s*=")
    root = Path(__file__).resolve().parents[1]
    offenders = [f"{path.relative_to(root)}:{n}" for folder in ("marketmind", "api", "app", "scripts")
                 for path in sorted((root / folder).rglob("*.py"))
                 for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
                 if keyword_form.search(line) and not line.lstrip().startswith("#")]
    assert offenders == [], f"write pd.Timedelta(n, unit=...) instead: {offenders}"
    assert period_bounds("2025-02") == (pd.Timestamp("2025-02-01"), pd.Timestamp("2025-02-28 23:59:59"))
    assert period_bounds("2024-07..2025-06-30") == (pd.Timestamp("2024-07-01"), pd.Timestamp("2025-06-30 23:59:59"))


def test_html_report_stamps_evidence_and_carries_the_qa_seal():
    # the HTML report typesets the Markdown the Critic checked, without changing its words
    from marketmind.reporting.html_report import _font_face, _present, qa_certificate_html, qa_seal_html

    html = _present("<h2>11. Recommendations</h2><h3>R1. Fix it</h3>"
                    "<p>Spike [CON-03]; see [CMP-08, SEG-02] and <code>[CON-09]</code>, worth Rp 8.7 bn.</p>")
    assert '<span class="sec-num">11</span>Recommendations' in html and '<span class="stamp">R1</span>Fix it' in html
    assert html.count('class="stamp"') == 5 and "[" not in html and "Rp&nbsp;8.7&nbsp;bn" in html
    assert "QA not run" in qa_seal_html(None) and ">96<" in qa_seal_html({"score": 95.6, "passed": True})
    cert = qa_certificate_html({"score": 88.0, "passed": False, "revision": 2, "numbers_grounded": 9, "numbers_checked": 10,
                                "checks": {"grounding": {"score": 0.9}}, "issues": [{"severity": "major", "message": "<b>x</b>"}]})
    assert "Not passed." in cert and "after 2 revisions" in cert and "width:90%" in cert and "&lt;b&gt;x&lt;/b&gt;" in cert
    assert _font_face().startswith("@font-face{font-family:Archivo")   # the typeface ships with the code


def test_parse_json_tolerates_fences():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert parse_json('Sure! {"b": [1, 2]} hope this helps') == {"b": [1, 2]}


def test_workflow_detects_cycles():
    class A(BaseAgent):
        name = "A"

    with pytest.raises(ValueError):
        Workflow([Task("a", A, ("b",)), Task("b", A, ("a",))])


def test_offline_llm_is_unavailable():
    llm = LLMClient(provider="none")
    assert not llm.available and llm.complete("s", "p") is None


@pytest.mark.skipif(not DATA_READY, reason="run scripts/generate_data.py first")
def test_full_pipeline_offline(offline_run):
    system, res, _ = offline_run  # one shared session run (tests/conftest.py), saved outside outputs/
    bb = system.blackboard
    assert res.status == "completed"
    assert res.qa["passed"] and res.qa["score"] >= 85
    ids = {f.id for f in bb.findings()}
    assert {"MKT-01", "CMP-01", "CON-01", "SEG-02", "FCT-01"} <= ids
    assert len(bb.get("strategy.recommendations")) >= 3
    assert (res.run_dir / "report.html").exists() and (res.run_dir / "findings.json").exists()


@pytest.mark.slow
@pytest.mark.skipif(not DATA_READY, reason="run scripts/generate_data.py first")
def test_critic_catches_invented_numbers_and_revision_fixes_them(tmp_path, monkeypatch):
    from marketmind.system import MarketResearchSystem

    monkeypatch.setattr("marketmind.system.RUNS_DIR", tmp_path)

    fake = FakeLLM()
    system = MarketResearchSystem(use_llm=True, llm=fake)
    res = system.run()
    history = system.blackboard.get("qa.history")
    assert history[0]["passed"] is False, "the invented 'Rp 999 trillion' must fail the first QA pass"
    assert res.qa["passed"], "after revision the report must pass"
    assert "Rp 999 trillion" not in system.blackboard.get("report.markdown")
    assert any(m.recipient == "Report Writer Agent" for m in system.blackboard.messages())
