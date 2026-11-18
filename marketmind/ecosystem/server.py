"""One enterprise's own server: its A2A endpoint, its governed data API and its dashboard, on its own port.

    python -m marketmind.ecosystem serve kirana --port 8101

The same security as the MarketMind API (``api/security.py``): only local hosts are answered (or the access token is
required when shared on a network), a request that changes something must be JSON from the same origin, and every
response is scrubbed of secrets. The A2A routes are what other enterprises and the Control Center call; the data
routes are what this enterprise's own dashboard calls, filtered by the role the user picked.
"""
from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from api.app import FRONTEND_DIST, allowed_hosts_from_env, mount_frontend
from api.security import AccessTokenMiddleware, LocalOnlyMiddleware, SafeJSONResponse
from marketmind.config import OUTPUTS
from marketmind.core.access import access_token

from .enterprises import ENTERPRISES, ORDER, PORTS, create
from .protocol import Message, agent_card

DATA_DIR = OUTPUTS / "ecosystem"
JSON_FIELDS = ("payload", "inputs", "outputs", "messages", "orders", "campaigns", "commitments", "weeks")


def decoded(rows: list[dict]) -> list[dict]:
    """The stores keep nested values as JSON text; the dashboards want them as objects again."""
    import json
    out = []
    for r in rows:
        r = dict(r)
        for k in JSON_FIELDS:
            if isinstance(r.get(k), str) and r[k][:1] in "[{":
                try:
                    r[k] = json.loads(r[k])
                except ValueError:
                    pass
        out.append(r)
    return out


def peer_urls() -> dict[str, str]:
    """Where every node of the ecosystem listens, as a browser opens it (MARKETMIND_ECOSYSTEM_HOST overrides localhost)."""
    host = os.getenv("MARKETMIND_ECOSYSTEM_HOST", "localhost")
    return {k: f"http://{host}:{p}" for k, p in PORTS.items()}


def transport_urls() -> dict[str, str]:
    """Where the Control Center calls the enterprises: the same servers, by address. On Windows a client that asks
    for "localhost" tries IPv6 first and waits about two seconds before falling back to 127.0.0.1, on every new
    connection: a season over HTTP took two minutes instead of five seconds."""
    host = os.getenv("MARKETMIND_ECOSYSTEM_HOST", "127.0.0.1")
    return {k: f"http://{host}:{p}" for k, p in PORTS.items()}


class Tick(BaseModel):
    week: int
    signals: dict[str, Any] = {}


class EndWeek(BaseModel):
    week: int


class Reset(BaseModel):
    mode: str = "ecosystem"
    scenario: str = "normal"
    seed: int = 7


def secure(app: FastAPI, allowed_hosts="env", token="env") -> None:
    app.add_middleware(AccessTokenMiddleware, token=access_token() if token == "env" else token)
    app.add_middleware(LocalOnlyMiddleware, allowed_hosts=allowed_hosts_from_env() if allowed_hosts == "env" else allowed_hosts)


def create_enterprise_app(key: str, data_dir: Path | str | None = None, seed: int = 7, research_run: str | None = "latest",
                          frontend_dist: Path | None = None, allowed_hosts="env", token="env") -> FastAPI:
    ent = create(key, Path(data_dir or DATA_DIR), seed, research_run)
    lock = threading.RLock()
    app = FastAPI(title=f"{ent.name} API", version="1.0", description=ent.description, docs_url="/api/docs",
                  redoc_url=None, openapi_url="/api/openapi.json", default_response_class=SafeJSONResponse)
    app.state.enterprise = ent
    secure(app, allowed_hosts, token)

    @app.get("/api/node")
    def node():
        urls = peer_urls()
        return {**ent.node(), "url": urls[key], "control_center": urls["control"],
                "peers": {k: u for k, u in urls.items() if k not in (key, "control")},
                "directory": [{"key": k, "name": ENTERPRISES[k].name, "industry": ENTERPRISES[k].industry,
                               "city": ENTERPRISES[k].city, "accent": ENTERPRISES[k].accent,
                               "accent_dark": ENTERPRISES[k].accent_dark, "url": urls[k], "port": PORTS[k]} for k in ORDER]}

    @app.get("/.well-known/agent-card.json")
    @app.get("/api/a2a/agent-card")
    def card(request: Request):
        return agent_card(ent, str(request.base_url))

    @app.post("/api/a2a/messages")
    def messages(m: Message):
        if m.receiver_enterprise != key:
            raise HTTPException(400, f"this is {key}'s endpoint; the message is for {m.receiver_enterprise}")
        with lock:
            return {"replies": [r.model_dump() for r in ent.receive(m)]}

    @app.post("/api/a2a/tick")
    def tick(t: Tick):
        with lock:
            return {"messages": [r.model_dump() for r in ent.tick(t.week, t.signals)]}

    @app.post("/api/a2a/end-week")
    def end_week(t: EndWeek):
        with lock:
            return {"messages": [r.model_dump() for r in ent.end_week(t.week)]}

    @app.post("/api/a2a/reset")
    def reset(r: Reset):
        with lock:
            ent.reset(r.mode, r.scenario, r.seed)
            return {"ok": True, "mode": ent.mode, "scenario": ent.scenario}

    @app.get("/api/a2a/shared")
    def shared(audience: str = "partner"):
        if audience not in ("partner", "control"):
            raise HTTPException(400, "audience is partner or control")
        with lock:
            return {"enterprise": key, "audience": audience, "mode": ent.mode, "view": ent.shared(audience)}

    @app.get("/api/status")
    def status():
        with lock:
            return ent.status()

    @app.get("/api/kpis")
    def kpis():
        with lock:
            return ent.kpis()

    @app.get("/api/data")
    def datasets(role: str | None = None):
        with lock:
            return {"role": ent.role(role).name, "store": ent.store.kind, "datasets": ent.datasets(role)}

    @app.get("/api/data/{table}")
    def dataset(table: str, role: str | None = None, limit: int = 200, offset: int = 0):
        with lock:
            if table not in ent.store.tables():
                raise HTTPException(404, f"{ent.name} has no dataset {table}")
            try:
                return ent.dataset(table, role, max(1, min(limit, 1000)), max(0, offset))
            except PermissionError as exc:
                raise HTTPException(403, str(exc)) from exc

    @app.get("/api/messages")
    def message_log(limit: int = 300, offset: int = 0):
        with lock:
            rows = ent.store.rows("messages")
            rows.reverse()
            return {"total": len(rows), "rows": decoded(rows[offset:offset + max(1, min(limit, 2000))])}

    @app.get("/api/decisions")
    def decisions(limit: int = 300):
        with lock:
            rows = ent.store.rows("decisions")
            rows.reverse()
            return {"total": len(rows), "rows": decoded(rows[:max(1, min(limit, 2000))])}

    @app.get("/api/negotiations")
    def negotiations():
        with lock:
            return {"threads": [{"conversation_id": k, **v} for k, v in ent.negotiations.items()]}

    mount_frontend(app, frontend_dist or FRONTEND_DIST)
    return app
