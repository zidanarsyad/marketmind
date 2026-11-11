"""Event tracing: every thought, tool call, finding and status change an agent makes is recorded.

The trace powers the dashboard's live agent console and is saved as ``trace.jsonl`` per run,
which makes each run auditable (who concluded what, from which tool output, and when).
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .redact import scrub, scrub_obj

KINDS =("status", "thought", "action", "observation", "finding", "message", "llm", "warning", "error")


@dataclass
class Event:
    ts: float
    agent: str
    kind: str
    message: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["time"] = time.strftime("%H:%M:%S", time.localtime(self.ts))
        return d


class Tracer:
    def __init__(self, run_id: str, echo: bool = False):
        self.run_id = run_id
        self.echo = echo
        self.events: list[Event] = []
        self._lock = threading.Lock()
        self._listeners: list[Callable[[Event], None]] = []

    def subscribe(self, fn: Callable[[Event], None]) -> None:
        self._listeners.append(fn)

    def emit(self, agent: str, kind: str, message: str, **data: Any) -> Event:
        # scrubbed here, so no credential reaches the live console, trace.jsonl or a listener (core/redact.py)
        ev = Event(time.time(), agent, kind, scrub(message), scrub_obj(_jsonable(data)))
        with self._lock:
            self.events.append(ev)
        if self.echo:
            print(f"[{time.strftime('%H:%M:%S')}] {agent:<26} {kind:<11} {ev.message}", flush=True)
        for fn in self._listeners:
            try:
                fn(ev)
            except Exception:  # a broken listener must never break the pipeline
                pass
        return ev

    def snapshot(self) -> list[Event]:
        with self._lock:
            return list(self.events)

    def save(self, path: Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            for ev in self.snapshot():
                f.write(json.dumps(ev.to_dict(), ensure_ascii=False) + "\n")


def load_trace(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    if hasattr(obj, "item"):  # numpy scalar
        try:
            return obj.item()
        except Exception:
            pass
    return str(obj)
