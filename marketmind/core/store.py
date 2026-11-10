"""Run persistence: every pipeline run is saved to ``outputs/runs/<run_id>/`` so the dashboard
can browse, compare and reload past runs without recomputing anything.

Layout::

    run_meta.json      brief, plan, timings, agent results, LLM usage, QA verdict
    findings.json      all published findings
    trace.jsonl        full agent event trace
    report.md / .html  final deliverables
    tables/<key>.csv   every DataFrame artefact on the blackboard
    json/<key>.json    every dict/list artefact on the blackboard
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..config import RUNS_DIR
from .blackboard import Blackboard
from .events import Tracer, load_trace
from .findings import Finding

SKIP_PREFIXES = ("datasets",)


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)


def _to_jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if np.isnan(obj) else float(obj)
    if isinstance(obj, float) and np.isnan(obj):
        return None
    if isinstance(obj, (pd.Timestamp, pd.Period)):
        return str(obj)
    if isinstance(obj, np.ndarray):
        return _to_jsonable(obj.tolist())
    if hasattr(obj, "to_dict") and not isinstance(obj, pd.DataFrame):
        return _to_jsonable(obj.to_dict())
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    return str(obj)


def save_run(run_dir: Path, bb: Blackboard, tracer: Tracer, meta: dict) -> None:
    (run_dir / "tables").mkdir(parents=True, exist_ok=True)
    (run_dir / "json").mkdir(exist_ok=True)
    for key in bb.keys():
        if key.startswith(SKIP_PREFIXES):
            continue
        value = bb.get(key)
        if isinstance(value, pd.DataFrame):
            value.to_csv(run_dir / "tables" / f"{_safe(key)}.csv", index=False)
        elif isinstance(value, dict) and value and all(isinstance(v, pd.DataFrame) for v in value.values()):
            for name, df in value.items():
                df.to_csv(run_dir / "tables" / f"{_safe(key)}.{_safe(name)}.csv", index=False)
        elif isinstance(value, str) and key.startswith("report."):
            ext = {"report.markdown": "md", "report.html": "html"}.get(key)
            if ext:
                (run_dir / f"report.{ext}").write_text(value, encoding="utf-8")
        else:
            try:
                (run_dir / "json" / f"{_safe(key)}.json").write_text(
                    json.dumps(_to_jsonable(value), indent=2, ensure_ascii=False), encoding="utf-8")
            except (TypeError, ValueError):
                pass
    findings = [f.to_dict() for f in bb.findings()]
    (run_dir / "findings.json").write_text(json.dumps(_to_jsonable(findings), indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / "run_meta.json").write_text(json.dumps(_to_jsonable(meta), indent=2, ensure_ascii=False), encoding="utf-8")
    tracer.save(run_dir / "trace.jsonl")


@dataclass
class RunData:
    """Read-only view of a saved run, used by the dashboard and the evaluation script."""
    run_id: str
    path: Path
    meta: dict = field(default_factory=dict)
    _tables: dict = field(default_factory=dict)
    _json: dict = field(default_factory=dict)

    @property
    def findings(self) -> list[Finding]:
        p = self.path / "findings.json"
        return [Finding.from_dict(d) for d in json.loads(p.read_text(encoding="utf-8"))] if p.exists() else []

    def table(self, key: str) -> pd.DataFrame | None:
        if key not in self._tables:
            p = self.path / "tables" / f"{_safe(key)}.csv"
            self._tables[key] = pd.read_csv(p) if p.exists() else None
        return self._tables[key]

    def tables(self, prefix: str = "") -> list[str]:
        return sorted(p.stem for p in (self.path / "tables").glob("*.csv") if p.stem.startswith(prefix))

    def json(self, key: str, default: Any = None) -> Any:
        if key not in self._json:
            p = self.path / "json" / f"{_safe(key)}.json"
            self._json[key] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else default
        return self._json[key]

    def text(self, name: str) -> str:
        p = self.path / name
        return p.read_text(encoding="utf-8") if p.exists() else ""

    @property
    def trace(self) -> list[dict]:
        return load_trace(self.path / "trace.jsonl")


def list_runs() -> list[dict]:
    runs = []
    if not RUNS_DIR.exists():
        return runs
    for d in sorted(RUNS_DIR.iterdir(), reverse=True):
        meta_path = d / "run_meta.json"
        if d.is_dir() and meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            runs.append(dict(run_id=d.name, started=meta.get("started"), status=meta.get("status"),
                             qa_score=(meta.get("qa") or {}).get("score"), client=meta.get("client"),
                             llm=meta.get("llm", {}).get("provider")))
    return runs


def load_run(run_id: str) -> RunData:
    path = RUNS_DIR / run_id
    meta = json.loads((path / "run_meta.json").read_text(encoding="utf-8"))
    return RunData(run_id=run_id, path=path, meta=meta)
