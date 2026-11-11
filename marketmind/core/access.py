"""Who may use the dashboard and the web app: this computer, or whoever holds the access token.

Both servers listen on this computer only by default, and then nothing is asked. To share one on a network, set
``MARKETMIND_ACCESS_TOKEN`` (``python -m api --host 0.0.0.0`` makes one up and prints a link that carries it). From
then on a browser needs the token before it sees anything, and every API request must carry it. Setting the token
also protects the servers on this computer, for example from other accounts on a shared machine.
"""
from __future__ import annotations

import hmac
import os

TOKEN_ENV = "MARKETMIND_ACCESS_TOKEN"
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


def access_token() -> str | None:
    """The configured access token, or None when there is none."""
    return os.getenv(TOKEN_ENV, "").strip() or None


def hostname(host_header: str) -> str:
    """The host name in a Host header, without the port: 'localhost:8000' -> 'localhost', '[::1]:8000' -> '::1'."""
    host = (host_header or "").strip().lower()
    if host.startswith("["):
        return host[1:host.find("]")] if "]" in host else host
    return host.rsplit(":", 1)[0] if host.count(":") == 1 else host


def is_local(host_header: str) -> bool:
    """True when a request names this computer (localhost, 127.0.0.1 or ::1)."""
    return hostname(host_header) in LOCAL_HOSTS


def token_matches(given: str | None, token: str | None) -> bool:
    """Compare in constant time, so the time a wrong guess takes says nothing about the token."""
    return bool(given and token) and hmac.compare_digest(given.encode("utf-8"), token.encode("utf-8"))
