"""The FastAPI application: the JSON API under /api, and the built Vue front end (frontend/dist) everywhere else."""
from __future__ import annotations

import os
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from marketmind.config import ROOT
from marketmind.core.access import access_token

from . import runs, studies, system_info
from .security import LOCAL_HOSTS, AccessTokenMiddleware, LocalOnlyMiddleware, SafeJSONResponse

FRONTEND_DIST = ROOT / "frontend" / "dist"

NOT_BUILT = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>MarketMind</title>
<style>body{font:16px/1.6 system-ui,sans-serif;max-width:40rem;margin:3rem auto;padding:0 1rem;color:#0b0b0b;background:#fcfcfb}
code,pre{background:#f0efec;border-radius:6px;padding:2px 6px}pre{padding:12px;overflow:auto}
@media (prefers-color-scheme:dark){body{color:#f0efec;background:#1a1a19}code,pre{background:#2c2c2a}}</style></head>
<body><h1>MarketMind API is running</h1><p>The web app has not been built yet. Build it once (Node.js 20 or newer):</p>
<pre>cd frontend
npm install
npm run build</pre><p>then reload this page. The API itself is documented at <a href="/api/docs">/api/docs</a>.</p></body></html>"""


def warm_up() -> None:
    """Import the heavy modules (scikit-learn, the review corpus helpers) in the background, so the first page the
    browser opens after a start does not wait seconds for them."""
    try:
        import marketmind.agents.analyst_chat  # noqa: F401
        import marketmind.evaluation  # noqa: F401
        import marketmind.ml.real_reviews  # noqa: F401
        system_info.brands_in_data()
    except Exception:  # only a speed-up; the endpoints import what they need themselves
        pass


def allowed_hosts_from_env() -> tuple[str, ...] | None:
    """MARKETMIND_ALLOWED_HOSTS: extra host names to answer to, or * for any (set by ``python -m api --host``)."""
    extra = [h.strip() for h in os.getenv("MARKETMIND_ALLOWED_HOSTS", "").split(",") if h.strip()]
    if "*" in extra:
        return None
    return LOCAL_HOSTS + tuple(extra)


def create_app(llm=None, frontend_dist: Path | None = None, allowed_hosts: tuple[str, ...] | None | str = "env",
               token: str | None = "env") -> FastAPI:
    """Build the app. ``llm`` defaults to an LLMClient configured from .env (offline when no key is set).

    ``allowed_hosts`` and ``token`` default to the environment (MARKETMIND_ALLOWED_HOSTS, MARKETMIND_ACCESS_TOKEN).
    """
    if llm is None:
        from marketmind.core.llm import LLMClient
        llm = LLMClient()
    app = FastAPI(title="MarketMind API", version="1.0",
                  description="Runs, charts, studies and approval gates of the MarketMind multi-agent research system.",
                  docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json",
                  default_response_class=SafeJSONResponse)
    app.state.llm = llm
    app.state.studies = studies.StudyRegistry()
    threading.Thread(target=warm_up, daemon=True, name="warm-up").start()
    # the middleware added last runs first: the host check, then the access token
    app.add_middleware(AccessTokenMiddleware, token=access_token() if token == "env" else token)
    app.add_middleware(LocalOnlyMiddleware,
                       allowed_hosts=allowed_hosts_from_env() if allowed_hosts == "env" else allowed_hosts)
    app.include_router(system_info.router)
    app.include_router(runs.router)
    app.include_router(studies.router)
    mount_frontend(app, frontend_dist or FRONTEND_DIST)
    return app


def mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built single-page app; any path that is not an API path or a file gets index.html (client routing)."""
    dist = dist.resolve()
    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

    @app.get("/api/{path:path}", include_in_schema=False)
    def unknown_api_path(path: str):
        raise HTTPException(404, f"No API endpoint /api/{path}")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        index = dist / "index.html"
        if not index.is_file():
            return HTMLResponse(NOT_BUILT)
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(dist):
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
