"""Blackboard: the shared memory through which agents cooperate.

Agents never call each other directly. They read inputs from the blackboard, write their
artefacts back with provenance, publish ``Finding`` objects, and leave messages for other
agents (e.g. the Critic sends revision requests to the Report Writer). This is the classic
blackboard architecture for multi-agent problem solving, made thread-safe so independent
analysis agents can run concurrently.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

from .findings import Finding


@dataclass
class Message:
    sender: str
    recipient: str
    content: str
    data: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


class Blackboard:
    def __init__(self):
        self._data: dict[str, Any] = {}
        self._meta: dict[str, dict] = {}
        self._findings: list[Finding] = []
        self._messages: list[Message] = []
        self._lock = threading.RLock()

    # -- artefacts -----------------------------------------------------------
    def put(self, key: str, value: Any, agent: str = "system", description: str = "") -> None:
        with self._lock:
            self._data[key] = value
            self._meta[key] = dict(agent=agent, description=description, ts=time.time(),
                                   type=type(value).__name__, shape=_shape(value))

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def require(self, key: str) -> Any:
        with self._lock:
            if key not in self._data:
                raise KeyError(f"Blackboard has no '{key}' - did the upstream agent run?")
            return self._data[key]

    def has(self, key: str) -> bool:
        with self._lock:
            return key in self._data

    def keys(self, prefix: str = "") -> list[str]:
        with self._lock:
            return sorted(k for k in self._data if k.startswith(prefix))

    def meta(self) -> dict[str, dict]:
        with self._lock:
            return dict(self._meta)

    # -- findings ------------------------------------------------------------
    def add_finding(self, finding: Finding) -> None:
        with self._lock:
            self._findings = [f for f in self._findings if f.id != finding.id] + [finding]

    def findings(self, area: str | None = None, agent: str | None = None) -> list[Finding]:
        with self._lock:
            out = list(self._findings)
        if area:
            out = [f for f in out if f.area == area]
        if agent:
            out = [f for f in out if f.agent == agent]
        return out

    # -- agent-to-agent messages ----------------------------------------------
    def post(self, sender: str, recipient: str, content: str, **data: Any) -> Message:
        msg = Message(sender, recipient, content, data)
        with self._lock:
            self._messages.append(msg)
        return msg

    def inbox(self, recipient: str, since: float = 0.0) -> list[Message]:
        with self._lock:
            return [m for m in self._messages if m.recipient == recipient and m.ts >= since]

    def messages(self) -> list[Message]:
        with self._lock:
            return list(self._messages)


def _shape(value: Any) -> str:
    if hasattr(value, "shape"):
        return "x".join(str(s) for s in value.shape)
    if isinstance(value, (list, dict, tuple, set)):
        return str(len(value))
    return ""
