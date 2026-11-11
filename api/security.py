"""Keep the web API local (or behind an access token), and keep secrets out of everything it sends.

* Secrets: the value of every environment variable that names a credential (``GROQ_API_KEY``, ``NEWSAPI_KEY``,
  ``..._TOKEN``, ``..._SECRET``) is replaced by ``[redacted]`` in every JSON response, event stream and report the
  API sends (``marketmind/core/redact.py``, which also covers the trace and the saved run files). No endpoint returns
  a key on purpose; this is the last line of defence, should one turn up in an error message an LLM provider sent.
* Local only: a request must name a local host, which stops a web page that rebinds its own domain to 127.0.0.1 from
  reaching the API through the browser. A request that changes something must be JSON and, when the browser says
  where it comes from, come from the page the API itself serves: a form on another site cannot start a study.
* Access token: shared on a network (``python -m api --host 0.0.0.0``), the host check is off and every request must
  carry the access token instead (``marketmind/core/access.py``); without it the API answers 401 and shows nothing.
"""
from __future__ import annotations

import json
import math
from typing import Any
from urllib.parse import urlencode, urlsplit

from starlette.datastructures import Headers
from starlette.requests import HTTPConnection
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from marketmind.core.access import LOCAL_HOSTS, hostname, token_matches
from marketmind.core.redact import REDACTED, SECRET_NAME, scrub, secret_values

__all__ = ["LOCAL_HOSTS", "REDACTED", "SECRET_NAME", "AccessTokenMiddleware", "LocalOnlyMiddleware", "SafeJSONResponse",
           "clean", "scrub", "secret_values"]

TOKEN_COOKIE = "marketmind_token"
NEEDS_TOKEN = ("This MarketMind server needs its access token: open the link with ?token=... that `python -m api` "
               "printed when it started, or send the header Authorization: Bearer <token>.")
NEEDS_TOKEN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>MarketMind: access token needed</title>
<style>body{font:16px/1.6 system-ui,sans-serif;max-width:40rem;margin:3rem auto;padding:0 1rem;color:#0b0b0b;background:#fcfcfb}
code{background:#f0efec;border-radius:6px;padding:2px 6px}
@media (prefers-color-scheme:dark){body{color:#f0efec;background:#1a1a19}code{background:#2c2c2a}}</style></head>
<body><h1>Access token needed</h1><p>This MarketMind server is shared on a network, so it only opens for people who
have its access token. Open the link that <code>python -m api</code> printed when it started: it ends in
<code>?token=...</code>. Your browser then remembers the token until you close it.</p></body></html>"""


def clean(obj: Any) -> Any:
    """Make a value JSON-safe: NaN and infinity become null, numpy scalars become Python numbers."""
    if isinstance(obj, dict):
        return {str(k): clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [clean(v) for v in obj]
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if hasattr(obj, "item") and callable(obj.item):  # numpy scalar
        try:
            return clean(obj.item())
        except (TypeError, ValueError):
            return str(obj)
    if isinstance(obj, (str, int, bool)) or obj is None:
        return obj
    return str(obj)


class SafeJSONResponse(JSONResponse):
    """The API's JSON response: strict JSON (no NaN), with credentials scrubbed."""

    def render(self, content: Any) -> bytes:
        try:
            text = json.dumps(content, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        except (TypeError, ValueError):
            text = json.dumps(clean(content), ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        return scrub(text).encode("utf-8")


class LocalOnlyMiddleware:
    """Refuse requests for other hosts, and changes that are not JSON from the API's own page.

    ``allowed_hosts`` None turns the host check off (the user chose to serve on their network, behind the token).
    """

    def __init__(self, app, allowed_hosts: tuple[str, ...] | None = LOCAL_HOSTS):
        self.app = app
        self.allowed_hosts = None if allowed_hosts is None else {h.lower().strip("[]") for h in allowed_hosts}

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        host = headers.get("host", "")
        if self.allowed_hosts is not None and hostname(host) not in self.allowed_hosts:
            await JSONResponse({"detail": "This server only answers on this computer (localhost)."},
                               status_code=400)(scope, receive, send)
            return
        if scope["method"] in ("POST", "PUT", "PATCH", "DELETE") and scope["path"].startswith("/api/"):
            ctype = headers.get("content-type", "").split(";")[0].strip().lower()
            if ctype != "application/json":
                await JSONResponse({"detail": "Send JSON (Content-Type: application/json)."},
                                   status_code=415)(scope, receive, send)
                return
            origin = headers.get("origin")
            if origin is not None and urlsplit(origin).netloc.lower() != host.lower():
                await JSONResponse({"detail": "Cross-origin request refused."}, status_code=403)(scope, receive, send)
                return
        await self.app(scope, receive, send)


class AccessTokenMiddleware:
    """With an access token set, every request must carry it; with none set, this does nothing.

    A browser carries it as the ``marketmind_token`` cookie, set on the first visit: any page opened with
    ``?token=...`` (the link ``python -m api`` prints) stores the cookie (HttpOnly, SameSite=Strict) and redirects to
    the same page without the token, so it does not stay in the address bar or the history. Scripts send
    ``Authorization: Bearer <token>``. Anything else gets 401 and no data.
    """

    def __init__(self, app, token: str | None = None):
        self.app, self.token = app, token

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self.token:
            await self.app(scope, receive, send)
            return
        conn = HTTPConnection(scope)
        given = conn.query_params.get("token")
        if given is not None:
            if token_matches(given, self.token):
                rest = urlencode([(k, v) for k, v in conn.query_params.multi_items() if k != "token"])
                response = RedirectResponse(scope["path"] + (f"?{rest}" if rest else ""), status_code=303)
                response.set_cookie(TOKEN_COOKIE, self.token, httponly=True, samesite="strict")
                await response(scope, receive, send)
                return
        else:
            auth = conn.headers.get("authorization", "")
            bearer = auth[7:].strip() if auth[:7].lower() == "bearer " else None
            if token_matches(bearer, self.token) or token_matches(conn.cookies.get(TOKEN_COOKIE), self.token):
                await self.app(scope, receive, send)
                return
        if scope["path"].startswith("/api/"):
            response = JSONResponse({"detail": NEEDS_TOKEN}, status_code=401)
        else:
            response = HTMLResponse(NEEDS_TOKEN_PAGE, status_code=401)
        await response(scope, receive, send)
