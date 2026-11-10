"""Keep the web API local, and keep secrets out of everything it sends.

* Secrets: the value of every environment variable that names a credential (``GROQ_API_KEY``, ``NEWSAPI_KEY``,
  ``..._TOKEN``, ``..._SECRET``) is replaced by ``[redacted]`` in every JSON response, event stream and report the
  API sends. No endpoint returns a key on purpose; this is the last line of defence, should one turn up in an error
  message an LLM provider sent back.
* Local only: a request must name a local host, which stops a web page that rebinds its own domain to 127.0.0.1 from
  reaching the API through the browser. A request that changes something must be JSON and, when the browser says
  where it comes from, come from the page the API itself serves: a form on another site cannot start a study.
"""
from __future__ import annotations

import json
import math
import os
import re
from typing import Any
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import JSONResponse

SECRET_NAME = re.compile(r"(_KEY|_TOKEN|_SECRET|_PASSWORD)$", re.IGNORECASE)
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")
REDACTED = "[redacted]"


def secret_values() -> list[str]:
    """Values of the credential variables in the environment (``.env`` is loaded into it), longest first."""
    values = {v.strip() for k, v in os.environ.items() if SECRET_NAME.search(k) and v and len(v.strip()) >= 8}
    return sorted(values, key=len, reverse=True)


def scrub(text: str) -> str:
    """Replace any credential value in ``text`` with ``[redacted]``."""
    for value in secret_values():
        if value in text:
            text = text.replace(value, REDACTED)
    return text


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


def _hostname(host_header: str) -> str:
    host = host_header.strip().lower()
    if host.startswith("["):                       # [::1]:8000
        return host[1:host.find("]")] if "]" in host else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


class LocalOnlyMiddleware:
    """Refuse requests for other hosts, and changes that are not JSON from the API's own page.

    ``allowed_hosts`` None turns the host check off (the user chose to serve on their network).
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
        if self.allowed_hosts is not None and _hostname(host) not in self.allowed_hosts:
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
