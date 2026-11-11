"""Smoke test: the Streamlit dashboard renders every tab for a saved run without an error.

Runs the real app script with Streamlit's test runner, pointed at the shared offline run (tests/conftest.py).
Each tab is wrapped in a guard that turns an exception into an on-page error, so the test also looks for those.
"""
from __future__ import annotations

import pytest

from marketmind.config import ROOT


def test_every_dashboard_tab_renders_for_a_saved_run(offline_run, monkeypatch):
    from streamlit.testing.v1 import AppTest

    from marketmind.core import store

    _, result, _ = offline_run
    monkeypatch.setattr(store, "RUNS_DIR", result.run_dir.parent)
    app = AppTest.from_file(str(ROOT / "app" / "dashboard.py"), default_timeout=300)
    app.run()
    assert not app.exception, [e.value for e in app.exception]
    errors = [str(e.value) for e in app.error]
    assert not any("could not be rendered" in e for e in errors), errors
    assert any("Market Research" in t.value for t in app.title)
    assert len(app.tabs) == 12


def test_a_rejected_run_shows_who_stopped_it(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    from marketmind import system as system_module
    from marketmind.core import store
    from marketmind.core.approval import Decision
    from marketmind.core.llm import LLMClient

    monkeypatch.setattr(system_module, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(store, "RUNS_DIR", tmp_path)
    system_module.MarketResearchSystem(use_llm=False, llm=LLMClient(provider="none"),
                                       approver=lambda gate, proposal: Decision(False, "test reviewer", "wrong scope")).run()
    app = AppTest.from_file(str(ROOT / "app" / "dashboard.py"), default_timeout=120)
    app.run()
    assert not app.exception, [e.value for e in app.exception]
    assert any("stopped at the plan approval gate by test reviewer: wrong scope" in str(e.value) for e in app.error)


@pytest.mark.slow   # renders the dashboard (about half a minute)
def test_with_an_access_token_set_the_dashboard_shows_nothing_until_it_is_given(tmp_path, monkeypatch):
    from streamlit.testing.v1 import AppTest

    from marketmind.core import store

    monkeypatch.setattr(store, "RUNS_DIR", tmp_path)             # no saved runs: the welcome page, quick to render
    monkeypatch.setenv("MARKETMIND_ACCESS_TOKEN", "s3cret-token-123")
    app = AppTest.from_file(str(ROOT / "app" / "dashboard.py"), default_timeout=120)
    app.run()
    assert [t.label for t in app.text_input] == ["Access token"] and not app.header and not app.sidebar.button
    app.text_input[0].input("wrong").run()
    assert any("not right" in str(e.value) for e in app.error) and not app.header
    app.text_input[0].input("s3cret-token-123").run()
    assert not app.exception, [e.value for e in app.exception]
    assert "Access token" not in [t.label for t in app.text_input] and app.header[0].value == "Welcome to MarketMind"
