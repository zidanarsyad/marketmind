"""Keep credentials out of everything MarketMind writes or shows.

API keys live in ``.env`` (git-ignored) and are only ever sent in request headers: never in URLs, prompts or files.
As a last line of defence, the value of every environment variable that names a credential (``GROQ_API_KEY``,
``..._TOKEN``, ``..._SECRET``, ``..._PASSWORD``) is replaced by ``[redacted]`` wherever text leaves the process: the
agent trace (the live console and ``trace.jsonl``), every file a run saves, LLM error messages, the dashboard's error
boxes and the web API's responses. Should a provider ever echo a key back in an error, it still goes no further.
"""
from __future__ import annotations

import os
import re
from typing import Any

SECRET_NAME = re.compile(r"(_KEY|_TOKEN|_SECRET|_PASSWORD)$", re.IGNORECASE)
REDACTED = "[redacted]"


def secret_values() -> list[str]:
    """Values of the credential variables in the environment (``.env`` is loaded into it), longest first."""
    values = {v.strip() for k, v in os.environ.items() if SECRET_NAME.search(k) and v and len(v.strip()) >= 8}
    return sorted(values, key=len, reverse=True)


def scrub(text: str) -> str:
    """Replace any credential value in ``text`` with ``[redacted]``."""
    if not text:
        return text
    for value in secret_values():
        if value in text:
            text = text.replace(value, REDACTED)
    return text


def scrub_obj(obj: Any) -> Any:
    """``scrub`` every string inside dicts, lists and tuples; other values come back as they are."""
    if isinstance(obj, str):
        return scrub(obj)
    if isinstance(obj, dict):
        return {(scrub(k) if isinstance(k, str) else k): scrub_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub_obj(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(scrub_obj(v) for v in obj)
    return obj
