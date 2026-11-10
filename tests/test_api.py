"""The web API (api/) with FastAPI's TestClient, offline (no LLM key).

The fast tests cover the local-only guards, secret scrubbing, request validation and the approval-gate logic (driven
by a stub study). The slow ones read the shared offline run (tests/conftest.py) through every endpoint, and run one
more study through both approval gates over HTTP, following it over server-sent events.
"""
from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

import pytest

from marketmind.config import DATA_RAW, DATASETS, DEFAULT_BRIEF, DEFAULT_CLIENT

DATA_READY = all((DATA_RAW / v["file"]).exists() for v in DATASETS.values())


def make_client(tmp_path, llm=None):
    from fastapi.testclient import TestClient

    from api.app import create_app
    from api.security import LOCAL_HOSTS
    from marketmind.core.llm import LLMClient
    app = create_app(llm=llm or LLMClient(provider="none"), frontend_dist=tmp_path / "no-build", allowed_hosts=LOCAL_HOSTS)
    return TestClient(app, base_url="http://localhost")


@pytest.fixture
def client(tmp_path):
    return make_client(tmp_path)


def sse_events(text: str) -> list[dict]:
    """Parse a text/event-stream body into [{event, id, data}]."""
    events = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        ev = {}
        for line in block.split("\n"):
            if line.startswith(":") or ":" not in line:
                continue
            key, value = line.split(":", 1)
            ev[key] = value.strip()
        if "data" in ev:
            ev["data"] = json.loads(ev["data"])
            events.append(ev)
    return events


# ---------------------------------------------------------------------------------------------- fast
def test_health_config_and_llm_status(client):
    assert client.get("/api/health").json() == {"ok": True}
    cfg = client.get("/api/config").json()
    assert cfg["llm"] == {"available": False, "provider": "none", "model": None,
                          "description": "offline (deterministic reasoning)"}
    assert {"value": "study", "label": "The study's reviews (default)"} in cfg["sentiment_options"]
    assert [d["name"] for d in cfg["datasets"]] == list(DATASETS)
    if DATA_READY:
        assert cfg["data"]["ready"] and DEFAULT_CLIENT in cfg["brands"] and cfg["default_brief"] == DEFAULT_BRIEF
    ping = client.post("/api/llm/ping", json={}).json()
    assert ping["ok"] is False and "offline" in ping["message"]


def test_the_api_answers_only_local_json_requests(client, tmp_path):
    from fastapi.testclient import TestClient
    assert TestClient(client.app, base_url="http://evil.example").get("/api/health").status_code == 400
    assert client.get("/api/health", headers={"host": "127.0.0.1:8000"}).status_code == 200
    # a cross-site form post cannot start a study or ask the LLM
    form = client.post("/api/studies", content="brief=x", headers={"content-type": "application/x-www-form-urlencoded"})
    assert form.status_code == 415
    assert client.post("/api/studies", content='{"brief": "x"}', headers={"content-type": "text/plain"}).status_code == 415
    assert client.post("/api/llm/ping", json={}, headers={"origin": "http://evil.example"}).status_code == 403
    assert client.post("/api/llm/ping", json={}, headers={"origin": "http://localhost"}).status_code == 200


def test_credentials_are_scrubbed_from_responses(tmp_path, monkeypatch):
    from api.security import scrub
    secret = "fake-groq-key-0123456789abcdef"
    monkeypatch.setenv("GROQ_API_KEY", secret)
    assert scrub(f"HTTP 401: invalid key {secret}") == "HTTP 401: invalid key [redacted]"

    class LeakyLLM:  # a provider error message that echoes the key back
        available, provider, model = True, "groq", "some-model"

        def describe(self):
            return f"groq / some-model - last error: bad key {secret}"

        def ping(self):
            return False, f"401 Unauthorized ({secret})"

    c = make_client(tmp_path, llm=LeakyLLM())
    for r in (c.get("/api/llm"), c.get("/api/config"), c.post("/api/llm/ping", json={})):
        assert r.status_code == 200 and secret not in r.text and "[redacted]" in r.text


def test_unknown_paths_and_runs_are_404(client):
    assert client.get("/api/runs/no-such-run").status_code == 404
    assert client.get("/api/runs/..%2F..%2Fapi").status_code == 404
    assert client.get("/api/runs/no-such-run/charts/brand_share").status_code == 404
    assert client.get("/api/nothing-here").status_code == 404
    assert client.get("/api/studies/no-such-study").status_code == 404
    assert client.post("/api/studies/no-such-study/approval", json={"gate": "plan", "approved": True}).status_code == 404
    page = client.get("/runs/x/overview")   # no built front end: a page that says how to build it
    assert page.status_code == 200 and "npm run build" in page.text


def test_a_built_front_end_is_served_with_client_side_routes(tmp_path):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><div id=app></div>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    from fastapi.testclient import TestClient

    from api.app import create_app
    from marketmind.core.llm import LLMClient
    c = TestClient(create_app(llm=LLMClient(provider="none"), frontend_dist=dist, allowed_hosts=("localhost",)),
                   base_url="http://localhost")
    assert c.get("/").text.startswith("<!doctype html>")
    assert "id=app" in c.get("/runs/20261110-222212/market").text      # a client-side route gets index.html
    assert c.get("/assets/app.js").text == "console.log(1)"
    assert c.get("/favicon.svg").text == "<svg/>"
    assert c.get("/..%2F..%2Fpyproject.toml").text.startswith("<!doctype html>")  # never a file outside dist


def test_study_requests_are_validated(client):
    bad = client.post("/api/studies", json={"brief": "Study the market", "sentiment_data": "everything"})
    assert bad.status_code == 422
    if DATA_READY:
        unknown = client.post("/api/studies", json={"brief": "Study the market", "client": "No Such Brand"})
        assert unknown.status_code == 422 and "Unknown client" in unknown.json()["detail"]
    assert client.get("/api/studies").json() == []


class StubSystem:
    """Stands in for MarketResearchSystem: a tracer and a run folder, nothing else."""

    def __init__(self, tmp_path):
        from marketmind.core.events import Tracer
        self.run_id = "stub-run"
        self.run_dir = tmp_path / "stub-run"
        self.tracer = Tracer(self.run_id)


def start_stub_study(client, tmp_path, gates):
    """Register a stub study whose thread asks the broker each (gate, proposal) in turn."""
    from api.studies import REVIEWER, Study
    from marketmind.core.approval import ApprovalBroker
    system = StubSystem(tmp_path)
    broker = ApprovalBroker(reviewer=REVIEWER, timeout=30)
    study = Study(id=system.run_id, system=system, broker=broker, options=dict(client=DEFAULT_CLIENT, brief="x"))
    answers = []

    def target():
        system.tracer.emit("Research Director", "status", "started")
        for gate, proposal in gates:
            answers.append(broker(gate, proposal))
            system.tracer.emit("Research Director", "approval", f"{gate} answered")
        study.result = SimpleNamespace(status="completed", seconds=1.0, qa={"score": 100.0, "passed": True})

    study.thread = threading.Thread(target=target, daemon=True)
    client.app.state.studies._studies[study.id] = study
    study.thread.start()
    return study, answers


def wait_for(predicate, timeout=30.0, every=0.05):
    end = time.time() + timeout
    while time.time() < end:
        value = predicate()
        if value:
            return value
        time.sleep(every)
    raise AssertionError("timed out waiting")


def test_approval_gates_validate_and_hand_over_decisions(client, tmp_path):
    plan = dict(client=DEFAULT_CLIENT, modules=["market", "competition", "forecast"], questions=[], objectives=[],
                horizon_months=12, concept=None)
    recs = dict(recommendations=[dict(id=f"R{i}", title=f"Do {i}", priority=1.0, horizon="Quick win", evidence=[])
                                 for i in (1, 2)])
    study, answers = start_stub_study(client, tmp_path, [("plan", plan), ("recommendations", recs)])
    url = f"/api/studies/{study.id}"

    pending = wait_for(lambda: client.get(f"{url}/approval").json()["pending"] and client.get(f"{url}/approval").json())
    assert pending["gate"] == "plan" and pending["proposal"]["modules"] == plan["modules"]
    assert client.get(url).json()["state"] == "waiting"
    assert client.get("/api/studies").json()[0]["pending"]["gate"] == "plan"   # any tab can find the waiting gate

    wrong_gate = client.post(f"{url}/approval", json={"gate": "recommendations", "approved": True})
    assert wrong_gate.status_code == 409
    unknown = client.post(f"{url}/approval", json={"gate": "plan", "approved": True, "drop": ["pricing"]})
    assert unknown.status_code == 422
    everything = client.post(f"{url}/approval", json={"gate": "plan", "approved": True, "drop": plan["modules"]})
    assert everything.status_code == 422 and "Nothing would be left" in everything.json()["detail"]

    ok = client.post(f"{url}/approval", json={"gate": "plan", "approved": True, "drop": ["forecast"], "comment": " ok "})
    assert ok.status_code == 200 and ok.json()["drop"] == ["forecast"]
    # a second click on the same gate (another tab, a double submit) cannot answer the next gate by mistake
    again = client.post(f"{url}/approval", json={"gate": "plan", "approved": True})
    assert again.status_code == 409

    wait_for(lambda: (client.get(f"{url}/approval").json()["gate"] == "recommendations"))
    assert client.post(f"{url}/approval", json={"gate": "recommendations", "approved": False,
                                                "comment": "not convinced"}).status_code == 200
    study.thread.join(10)
    assert [(a.approved, a.reviewer, a.comment, a.drop) for a in answers] == [
        (True, "web reviewer", "ok", ["forecast"]), (False, "web reviewer", "not convinced", [])]
    final = client.get(url).json()
    assert final["state"] == "completed" and final["pending"] is None and len(final["decisions"]) == 2

    events = sse_events(client.get(f"{url}/events").text)
    traces = [e for e in events if e.get("event") == "trace"]
    assert [int(e["id"]) for e in traces] == list(range(len(study.system.tracer.events)))
    assert events[-1]["event"] == "end" and events[-1]["data"]["state"] == "completed"
    # a reconnecting browser sends the last id it saw and gets only what it missed
    resumed = sse_events(client.get(f"{url}/events", headers={"last-event-id": traces[-2]["id"]}).text)
    assert [e["id"] for e in resumed if e.get("event") == "trace"] == [traces[-1]["id"]]


# ---------------------------------------------------------------------------------------------- slow: a saved run
@pytest.fixture
def run_client(offline_run, tmp_path, monkeypatch):
    from marketmind.core import store
    _, result, run = offline_run
    monkeypatch.setattr(store, "RUNS_DIR", result.run_dir.parent)
    return make_client(tmp_path), run


def test_a_saved_run_is_served_through_every_read_endpoint(run_client):
    c, run = run_client
    rid = run.run_id
    assert rid in [r["run_id"] for r in c.get("/api/runs").json()]
    summary = c.get(f"/api/runs/{rid}").json()
    assert summary["meta"]["status"] == run.meta["status"] and summary["horizon_months"] == run.json("strategy.kpis")["horizon_months"]
    assert summary["has_report"] and summary["has_ground_truth"] and "data.catalog" in summary["tables"]
    assert c.get(f"/api/runs/{rid}/kpis").json()["kpis"] == run.json("strategy.kpis")
    assert len(c.get(f"/api/runs/{rid}/findings").json()) == len(run.findings)
    assert [r["id"] for r in c.get(f"/api/runs/{rid}/recommendations").json()] == [r["id"] for r in run.json("strategy.recommendations")]
    assert set(c.get(f"/api/runs/{rid}/swot").json()) == {"Strengths", "Weaknesses", "Opportunities", "Threats"}
    assert c.get(f"/api/runs/{rid}/trace").json()[0]["agent"] == "System"
    assert c.get(f"/api/runs/{rid}/json/consumer.model_card").json()["selected"] in ("linear", "bigru", "ensemble")
    assert c.get(f"/api/runs/{rid}/json/no.such.artefact").status_code == 404

    table = c.get(f"/api/runs/{rid}/tables/competition.tables.brand_share").json()
    assert table["columns"][0] == "brand" and table["total"] == len(table["data"]) and not table["truncated"]
    page = c.get(f"/api/runs/{rid}/tables/segmentation.tables.assignments?limit=10&offset=5").json()
    assert len(page["data"]) == 10 and page["offset"] == 5 and page["truncated"]

    html = c.get(f"/api/runs/{rid}/report.html")
    assert html.status_code == 200 and "sandbox" in html.headers["content-security-policy"]
    md = c.get(f"/api/runs/{rid}/report.md?download=true")
    assert md.headers["content-disposition"] == f'attachment; filename="marketmind_{rid}.md"'

    preview = c.get(f"/api/runs/{rid}/datasets/sales?limit=50").json()
    assert preview["available"] and len(preview["data"]) == 50 and preview["truncated"]
    assert c.get(f"/api/runs/{rid}/datasets/not-a-dataset").status_code == 404


def test_every_chart_serialises_in_both_themes(run_client):
    from marketmind.reporting.charts import CHARTS
    c, run = run_client
    assert c.get(f"/api/runs/{run.run_id}/charts").json() == list(CHARTS)
    for name in CHARTS:
        figures = {theme: c.get(f"/api/runs/{run.run_id}/charts/{name}?theme={theme}").json() for theme in ("light", "dark")}
        for fig in figures.values():
            assert fig is not None and fig["data"] and "layout" in fig, name
        assert figures["light"] != figures["dark"], name     # the palette follows the theme
    assert c.get(f"/api/runs/{run.run_id}/charts/brand_share?theme=sepia").status_code == 422


def test_evaluation_chat_and_sentiment_tester(run_client):
    c, run = run_client
    rid = run.run_id
    (run.path / "evaluation.json").unlink(missing_ok=True)
    assert c.get(f"/api/runs/{rid}/evaluation").json() == {"available": True, "evaluated": False, "result": None}
    scored = c.post(f"/api/runs/{rid}/evaluation", json={}).json()
    assert scored["evaluated"] and scored["result"]["total"] == 25
    assert c.get(f"/api/runs/{rid}/evaluation").json()["result"] == scored["result"]

    answer = c.post(f"/api/runs/{rid}/chat", json={"question": "What is our biggest problem?", "history": []}).json()
    assert answer["mode"] == "retrieval (offline)" and answer["sources"]
    assert f"[{answer['sources'][0]['id']}]" in answer["answer"]
    assert c.post(f"/api/runs/{rid}/chat", json={"question": ""}).status_code == 422

    if c.get(f"/api/runs/{rid}/sentiment").json()["available"]:
        out = c.post(f"/api/runs/{rid}/sentiment", json={"text": "Teksturnya ringan, tapi pump-nya rusak 😭"}).json()
        assert out["label"] in ("negative", "neutral", "positive")
        assert abs(sum(out["probabilities"].values()) - 1) < 1e-3
        assert out["attention"] and {a["aspect"] for a in out["aspects"]} >= {"Packaging"}


# ---------------------------------------------------------------------------------------------- slow: a study end to end
@pytest.mark.slow
@pytest.mark.skipif(not DATA_READY, reason="run scripts/generate_data.py first")
def test_a_study_runs_through_both_gates_over_the_api(tmp_path, monkeypatch):
    from marketmind import system as system_module
    from marketmind.core import store
    monkeypatch.setattr(system_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(store, "RUNS_DIR", tmp_path / "runs")
    c = make_client(tmp_path)

    started = c.post("/api/studies", json=dict(brief=DEFAULT_BRIEF, client=DEFAULT_CLIENT, use_llm=False, review=True))
    assert started.status_code == 201
    sid = started.json()["id"]
    assert c.post("/api/studies", json=dict(brief=DEFAULT_BRIEF, review=True)).status_code == 409   # one at a time

    def at_gate(gate):
        state = c.get(f"/api/studies/{sid}").json()
        assert state["state"] not in ("failed", "error", "rejected"), state
        return state if state["pending"] and state["pending"]["gate"] == gate else None

    plan = wait_for(lambda: at_gate("plan"), timeout=600, every=0.5)
    assert "segmentation" in plan["pending"]["proposal"]["modules"]
    # leave out segmentation: pricing goes with it, so the concept KPIs stay empty (the UI then shows no tile for them)
    assert c.post(f"/api/studies/{sid}/approval", json=dict(gate="plan", approved=True, drop=["segmentation"])).status_code == 200

    recs = wait_for(lambda: at_gate("recommendations"), timeout=900, every=0.5)
    last = recs["pending"]["proposal"]["recommendations"][-1]["id"]
    assert c.post(f"/api/studies/{sid}/approval", json=dict(gate="recommendations", approved=True, drop=[last])).status_code == 200

    final = wait_for(lambda: (s := c.get(f"/api/studies/{sid}").json())["state"] not in ("running", "waiting", "starting") and s,
                     timeout=900, every=0.5)
    assert final["state"] in ("completed", "unverified") and final["saved"], final

    events = sse_events(c.get(f"/api/studies/{sid}/events").text)
    assert any(e.get("event") == "trace" and e["data"]["kind"] == "approval" for e in events)
    assert events[-1]["event"] == "end"

    run = c.get(f"/api/runs/{sid}").json()
    approvals = run["meta"]["approvals"]
    assert [(a["gate"], a["reviewer"], a["drop"]) for a in approvals] == [
        ("plan", "web reviewer", ["segmentation"]), ("recommendations", "web reviewer", [last])]
    assert run["meta"]["plan"]["modules"]["segmentation"] is False and run["meta"]["plan"]["modules"]["pricing"] is False
    assert run["kpis"].get("target_segment") is None and run["kpis"].get("recommended_price_idr") is None
    assert last not in [r["id"] for r in c.get(f"/api/runs/{sid}/recommendations").json()]
    assert c.get(f"/api/runs/{sid}/charts/segment_map").json() is None       # a skipped module's chart is null
