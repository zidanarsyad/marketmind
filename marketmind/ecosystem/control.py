"""The Global Agentic Control Center's server: enterprise status, agent communication, negotiations, decisions and
changes in the environment, and the place to run a scenario.

    python -m marketmind.ecosystem serve control --port 8100

It reaches the enterprises only through their APIs (``HttpTransport``), so it sees exactly what each one's governance
shares with it. A run resets every enterprise and plays 16 weeks; ``compare`` plays the scenario twice, local
intelligence then ecosystem intelligence, on the same customers, and puts the KPIs side by side. One run at a time.
"""
from __future__ import annotations

import itertools
import threading
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from api.app import FRONTEND_DIST, mount_frontend
from api.security import SafeJSONResponse

from .engine import SCHEMA_MAPPING, Ecosystem, HttpTransport, Transport, compare
from .enterprises import ENTERPRISES, ORDER, PORTS
from .server import peer_urls, secure, transport_urls
from .world import CAMPAIGNS, MODES, SCENARIOS, WEEKS, scenario_info, week_start


class RunRequest(BaseModel):
    scenario: str = "normal"
    mode: str = "compare"          # local | ecosystem | compare
    seed: int = 7


def _without_messages(r: dict) -> dict:
    return {k: v for k, v in r.items() if k != "messages"}


def create_control_app(transport: Transport | None = None, urls: dict[str, str] | None = None,
                       frontend_dist: Path | None = None, allowed_hosts="env", token="env") -> FastAPI:
    if transport is None:
        import os
        from marketmind.core.access import TOKEN_ENV
        transport = HttpTransport({k: (urls or transport_urls())[k] for k in ORDER})
        if os.getenv(TOKEN_ENV):
            transport.client.headers["Authorization"] = f"Bearer {os.environ[TOKEN_ENV]}"
    urls = urls or peer_urls()
    app = FastAPI(title="MarketMind Global Agentic Control Center", version="1.0", docs_url="/api/docs", redoc_url=None,
                  openapi_url="/api/openapi.json", default_response_class=SafeJSONResponse)
    secure(app, allowed_hosts, token)
    state = {"runs": {}, "order": [], "busy": None}
    lock = threading.Lock()
    ids = itertools.count(1)

    @app.get("/api/node")
    def node():
        return {"kind": "control", "name": "Global Agentic Control Center", "url": urls["control"],
                "description": "Watches the six enterprises, their agents' messages and negotiations, the ecosystem "
                               "plans, the decisions and the disruptions; runs and compares scenarios.",
                "enterprises": [{"key": k, "name": ENTERPRISES[k].name, "industry": ENTERPRISES[k].industry,
                                 "accent": ENTERPRISES[k].accent,
                                 "accent_dark": ENTERPRISES[k].accent_dark, "city": ENTERPRISES[k].city,
                                 "url": urls[k], "port": PORTS[k]} for k in ORDER],
                "scenarios": scenario_info(), "modes": list(MODES), "weeks": WEEKS, "schema_mapping": SCHEMA_MAPPING,
                "campaigns": [{"name": c, "weeks": list(ws)} for c, ws in CAMPAIGNS.items()],
                "week_starts": {w: week_start(w).isoformat() for w in range(1, WEEKS + 1)}}

    @app.get("/api/control/enterprises")
    def enterprises():
        out = []
        for k in ORDER:
            try:
                out.append({**transport.status(k), "online": True, "url": urls[k]})
            except Exception as exc:     # an enterprise server that is down shows as offline, it does not break the page
                out.append({"key": k, "name": ENTERPRISES[k].name, "online": False, "url": urls[k],
                            "error": type(exc).__name__})
        return {"enterprises": out}

    @app.get("/api/control/scenarios")
    def scenarios():
        return {"scenarios": scenario_info()}

    def _play(run_id: str, req: RunRequest) -> None:
        rec = state["runs"][run_id]

        def progress(week, note):
            rec["progress"] = {"week": week, "of": WEEKS, "note": note, "phase": rec.get("phase")}
        try:
            modes = ("local", "ecosystem") if req.mode == "compare" else (req.mode,)
            results = {}
            for m in modes:
                rec["phase"] = m
                results[m] = Ecosystem(transport, req.scenario, m, req.seed, progress=progress).run()
            rec["results"] = results
            rec["comparison"] = compare(results["local"], results["ecosystem"]) if req.mode == "compare" else None
            rec["status"] = "done"
        except Exception as exc:
            rec["status"], rec["error"] = "failed", f"{type(exc).__name__}: {exc}"
        finally:
            rec["finished"] = time.time()
            with lock:
                state["busy"] = None

    @app.post("/api/control/runs")
    def start(req: RunRequest):
        if req.scenario not in SCENARIOS:
            raise HTTPException(400, f"unknown scenario {req.scenario}")
        if req.mode not in (*MODES, "compare"):
            raise HTTPException(400, "mode is local, ecosystem or compare")
        with lock:
            if state["busy"]:
                raise HTTPException(409, f"run {state['busy']} is still playing; wait for it to finish")
            run_id = f"RUN-{next(ids):03d}"
            state["busy"] = run_id
        state["runs"][run_id] = {"id": run_id, "scenario": req.scenario, "title": SCENARIOS[req.scenario][0],
                                 "mode": req.mode, "seed": req.seed, "status": "running", "started": time.time(),
                                 "progress": {"week": 0, "of": WEEKS}}
        state["order"].append(run_id)
        threading.Thread(target=_play, args=(run_id, req), daemon=True, name=run_id).start()
        return {"id": run_id, "status": "running"}

    def _summary(rec: dict) -> dict:
        out = {k: v for k, v in rec.items() if k != "results"}
        if rec.get("results"):
            out["results"] = {m: _without_messages(r) for m, r in rec["results"].items()}
        return out

    @app.get("/api/control/runs")
    def runs():
        return {"runs": [{k: v for k, v in state["runs"][i].items() if k not in ("results", "comparison")}
                         for i in reversed(state["order"])], "busy": state["busy"]}

    @app.get("/api/control/runs/latest")
    def latest():
        done = [i for i in reversed(state["order"]) if state["runs"][i]["status"] == "done"]
        if not done:
            raise HTTPException(404, "no finished run yet")
        return _summary(state["runs"][done[0]])

    @app.get("/api/control/runs/{run_id}")
    def run(run_id: str):
        if run_id not in state["runs"]:
            raise HTTPException(404, f"no run {run_id}")
        return _summary(state["runs"][run_id])

    @app.get("/api/control/runs/{run_id}/messages")
    def messages(run_id: str, mode: str = "ecosystem", enterprise: str | None = None, task: str | None = None,
                 limit: int = 500, offset: int = 0):
        rec = state["runs"].get(run_id)
        if not rec or not rec.get("results"):
            raise HTTPException(404, f"no finished run {run_id}")
        result = rec["results"].get(mode) or next(iter(rec["results"].values()))
        rows = [m for m in result["messages"]
                if (not enterprise or enterprise in (m["sender"].split(".")[0], m["receiver"].split(".")[0]))
                and (not task or m["task"] == task)]
        return {"total": len(rows), "rows": rows[offset:offset + max(1, min(limit, 5000))],
                "tasks": sorted({m["task"] for m in result["messages"]})}

    mount_frontend(app, frontend_dist or FRONTEND_DIST)
    return app
