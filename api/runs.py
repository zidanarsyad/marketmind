"""Read endpoints over the run store (``outputs/runs/<run_id>/``), plus the tools that work on a saved run:
the charts, the report, the ground-truth evaluation, Ask the analyst (agentic RAG), Ask the data (the ReAct Data
Agent) and the sentiment model tester.

Runs are read through ``marketmind.core.store`` exactly as the Streamlit dashboard reads them; nothing here writes to
a run except ``evaluation.json``, which the dashboard writes too.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Literal

import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from marketmind.config import DATA_RAW, DATASETS, MODELS_DIR, ROOT
from marketmind.core import store
from marketmind.core.store import RunData
from marketmind.reporting.charts import CHARTS, TableSource

from .security import clean, scrub

router = APIRouter(prefix="/api/runs", tags=["runs"])

RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
ARTEFACT_KEY = re.compile(r"^[A-Za-z0-9_.-]{1,120}$")
_runs: dict[tuple, RunData] = {}
_charts: dict[tuple, str] = {}
_cache_lock = threading.Lock()


# ------------------------------------------------------------------------------------------------ helpers
def run_dir(run_id: str) -> Path:
    if not RUN_ID.match(run_id) or ".." in run_id:
        raise HTTPException(404, f"No saved run {run_id!r}")
    path = store.RUNS_DIR / run_id
    if not (path / "run_meta.json").is_file():
        raise HTTPException(404, f"No saved run {run_id!r}")
    return path


def get_run(run_id: str) -> RunData:
    """The saved run, cached while its run_meta.json is unchanged (a finished run never changes)."""
    path = run_dir(run_id)
    key = (str(path), (path / "run_meta.json").stat().st_mtime_ns)
    with _cache_lock:
        run = _runs.get(key)
    if run is None:
        try:
            run = store.load_run(run_id)
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(500, f"Run {run_id} could not be read: {type(exc).__name__}") from exc
        with _cache_lock:
            if len(_runs) >= 12:
                _runs.pop(next(iter(_runs)))
            _runs[key] = run
    return run


def run_key(run: RunData) -> tuple:
    return str(run.path), (run.path / "run_meta.json").stat().st_mtime_ns


def horizon_of(run: RunData) -> int:
    """Forecast months: the plan's horizon, as the KPIs record it (never a fixed 12)."""
    kpis = run.json("strategy.kpis", {}) or {}
    return int(kpis.get("horizon_months") or (run.json("plan", {}) or {}).get("horizon_months") or 12)


def frame(df: pd.DataFrame | None, limit: int | None = None, offset: int = 0) -> dict | None:
    """A DataFrame as {columns, data, total, offset, truncated}; NaN becomes null."""
    if df is None:
        return None
    total = len(df)
    part = df.iloc[offset: offset + limit] if limit is not None else df.iloc[offset:]
    payload = json.loads(part.to_json(orient="split", index=False, date_format="iso", force_ascii=False))
    return dict(columns=[str(c) for c in payload["columns"]], data=payload["data"], total=total, offset=offset,
                truncated=offset + len(part) < total)


def run_summary(run: RunData) -> dict:
    from marketmind.evaluation import has_ground_truth
    meta = run.meta
    recs = run.json("strategy.recommendations", []) or []
    return dict(run_id=run.run_id, meta=meta, kpis=run.json("strategy.kpis", {}) or {}, horizon_months=horizon_of(run),
                counts=dict(findings=len(run.findings), recommendations=len(recs)), tables=run.tables(),
                has_report=(run.path / "report.html").is_file(), has_markdown=(run.path / "report.md").is_file(),
                has_ground_truth=has_ground_truth(run), evaluated=(run.path / "evaluation.json").is_file())


# ------------------------------------------------------------------------------------------------ the run
@router.get("")
def list_saved_runs() -> list[dict]:
    """Saved runs, newest first (a study still running has no run_meta.json yet and is not listed)."""
    runs = store.list_runs()
    for r in runs:
        try:
            meta = json.loads((store.RUNS_DIR / r["run_id"] / "run_meta.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        opts = meta.get("options") or {}
        r.update(seconds=meta.get("seconds"), use_llm=bool(opts.get("use_llm")), review=opts.get("approval") == "human",
                 qa_passed=(meta.get("qa") or {}).get("passed"))
    return runs


@router.get("/{run_id}")
def get_run_summary(run_id: str) -> dict:
    """The run's meta (plan, options, agents, workflow, QA, approvals, LLM use), its KPIs and what it holds."""
    return run_summary(get_run(run_id))


@router.get("/{run_id}/kpis")
def get_kpis(run_id: str) -> dict:
    run = get_run(run_id)
    return dict(kpis=run.json("strategy.kpis", {}) or {}, horizon_months=horizon_of(run))


@router.get("/{run_id}/findings")
def get_findings(run_id: str) -> list[dict]:
    return [f.to_dict() for f in get_run(run_id).findings]


@router.get("/{run_id}/recommendations")
def get_recommendations(run_id: str) -> list[dict]:
    return get_run(run_id).json("strategy.recommendations", []) or []


@router.get("/{run_id}/swot")
def get_swot(run_id: str) -> dict:
    return get_run(run_id).json("strategy.swot", {}) or {}


@router.get("/{run_id}/trace")
def get_trace(run_id: str) -> list[dict]:
    return get_run(run_id).trace


@router.get("/{run_id}/tables")
def list_tables(run_id: str) -> list[str]:
    return get_run(run_id).tables()


@router.get("/{run_id}/tables/{key}")
def get_table(run_id: str, key: str, limit: int = Query(5000, ge=1, le=50_000), offset: int = Query(0, ge=0)) -> dict:
    """One table artefact, e.g. ``competition.tables.brand_share`` or ``data.catalog``."""
    run = get_run(run_id)
    if not ARTEFACT_KEY.match(key) or key not in run.tables():
        raise HTTPException(404, f"Run {run_id} has no table {key!r}")
    return dict(key=key, **frame(run.table(key), limit, offset))


@router.get("/{run_id}/json/{key}")
def get_artefact(run_id: str, key: str):
    """One JSON artefact, e.g. ``consumer.model_card`` or ``plan``."""
    run = get_run(run_id)
    if not ARTEFACT_KEY.match(key):
        raise HTTPException(404, f"Run {run_id} has no artefact {key!r}")
    value = run.json(key)
    if value is None:
        raise HTTPException(404, f"Run {run_id} has no artefact {key!r}")
    return value


# ------------------------------------------------------------------------------------------------ charts
@router.get("/{run_id}/charts")
def list_charts(run_id: str) -> list[str]:
    get_run(run_id)
    return list(CHARTS)


@router.get("/{run_id}/charts/{name}")
def get_chart(run_id: str, name: str, theme: Literal["light", "dark"] = "light") -> Response:
    """A chart from ``marketmind.reporting.charts`` as Plotly figure JSON, or ``null`` when the run has no data for it."""
    if name not in CHARTS:
        raise HTTPException(404, f"No chart {name!r}; the charts are: {', '.join(CHARTS)}")
    run = get_run(run_id)
    key = (*run_key(run), name, theme)
    with _cache_lock:
        body = _charts.get(key)
    if body is None:
        fig = CHARTS[name](TableSource.from_run(run), theme)
        body = fig.to_json() if fig is not None else "null"
        with _cache_lock:
            if len(_charts) >= 400:
                _charts.pop(next(iter(_charts)))
            _charts[key] = body
    return Response(body, media_type="application/json")


# ------------------------------------------------------------------------------------------------ report
def _report(run_id: str, name: str, media: str, download: bool) -> Response:
    run = get_run(run_id)
    text = run.text(name)
    if not text:
        raise HTTPException(404, f"Run {run_id} has no {name}")
    headers = {"Cache-Control": "no-cache"}
    if media == "text/html":   # the report runs its own chart scripts, isolated from this app's origin
        headers["Content-Security-Policy"] = "sandbox allow-scripts allow-popups allow-popups-to-escape-sandbox allow-downloads"
    if download:
        headers["Content-Disposition"] = f'attachment; filename="marketmind_{run.run_id}.{name.rsplit(".", 1)[1]}"'
    return Response(scrub(text), media_type=f"{media}; charset=utf-8", headers=headers)


@router.get("/{run_id}/report.html")
def get_report_html(run_id: str, download: bool = False) -> Response:
    return _report(run_id, "report.html", "text/html", download)


@router.get("/{run_id}/report.md")
def get_report_markdown(run_id: str, download: bool = False) -> Response:
    return _report(run_id, "report.md", "text/markdown", download)


# ------------------------------------------------------------------------------------------------ evaluation
@router.get("/{run_id}/evaluation")
def get_evaluation(run_id: str) -> dict:
    """The saved ground-truth evaluation, if the run has been evaluated."""
    from marketmind.evaluation import has_ground_truth
    run = get_run(run_id)
    path = run.path / "evaluation.json"
    result = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
    return dict(available=has_ground_truth(run), evaluated=result is not None, result=result)


@router.post("/{run_id}/evaluation")
def run_evaluation(run_id: str) -> dict:
    """Score the run against the truth planted in the simulated data, and save it as evaluation.json."""
    from marketmind.evaluation import evaluate, has_ground_truth
    run = get_run(run_id)
    if not has_ground_truth(run):
        raise HTTPException(409, "This run studied real data, which has no planted answers to score against.")
    result = clean(evaluate(run))
    (run.path / "evaluation.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return dict(available=True, evaluated=True, result=result)


# ------------------------------------------------------------------------------------------------ ask the analyst
class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class ChatQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)


@router.post("/{run_id}/chat")
def ask_the_analyst(run_id: str, body: ChatQuestion, request: Request) -> dict:
    """Answer one question with the agentic-RAG Analyst Chat: plan, retrieve, grade, rewrite, answer, verify.

    The sources are the run's findings, recommendations and report, the method notes and the customer reviews; the
    reply carries the trace of the agent's steps. Asked once per call: the browser keeps the conversation, so
    reloading the page never asks again.
    """
    from marketmind.agents.analyst_chat import AnalystChatAgent
    run = get_run(run_id)
    question = body.question.strip()
    if not question:
        raise HTTPException(422, "Ask a question.")
    out = AnalystChatAgent(run, request.app.state.llm).answer(question, [t.model_dump() for t in body.history])
    sources = [{k: s.get(k) for k in ("id", "kind", "title", "area", "source", "score", "collection")}
               for s in out["sources"]]
    return clean(dict(answer=out["answer"], sources=sources, mode=out["mode"], verified=out.get("verified", True),
                      trace=out.get("trace", [])))


class DataQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


@router.post("/{run_id}/ask-data")
def ask_the_data(run_id: str, body: DataQuestion, request: Request) -> dict:
    """Answer one question from the run's datasets with the ReAct Data Agent (reason, call a read-only tool, observe,
    repeat). The reply carries every step: thought, tool call, observation, and the verified answer."""
    from marketmind.agents.data_agent import ReActDataAgent
    run = get_run(run_id)
    question = body.question.strip()
    if not question:
        raise HTTPException(422, "Ask a question.")
    try:
        agent = ReActDataAgent(run, request.app.state.llm)
    except Exception as exc:
        raise HTTPException(409, f"The run's datasets could not be loaded ({type(exc).__name__}).") from exc
    out = agent.answer(question, [t.model_dump() for t in body.history])
    return clean(out)


# ------------------------------------------------------------------------------------------------ sentiment model tester
_suites: dict[tuple[str, str], object] = {}
_suite_lock = threading.Lock()


def sentiment_suite(run: RunData):
    """The run's trained sentiment models, loaded once; None when they are not on disk (or were retrained since)."""
    card = run.json("consumer.model_card", {}) or {}
    if not card:
        return None, card
    model_dir = (card.get("training_data") or {}).get("model_dir", "")
    key = (card.get("data_hash", ""), model_dir)
    with _suite_lock:
        if key not in _suites:
            from marketmind.ml.sentiment import SentimentSuite
            suite = SentimentSuite(ROOT / model_dir if model_dir else MODELS_DIR / "sentiment")
            if not suite.try_load(key[0]):
                return None, card
            _suites[key] = suite
        return _suites[key], card


class SentimentText(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


@router.get("/{run_id}/sentiment")
def sentiment_status(run_id: str) -> dict:
    suite, card = sentiment_suite(get_run(run_id))
    return dict(available=suite is not None, has_model_card=bool(card), real_text_note=card.get("real_text_note"))


@router.post("/{run_id}/sentiment")
def try_the_sentiment_model(run_id: str, body: SentimentText) -> dict:
    """Score a review with the run's deep-learning model: label, probabilities, attention and aspect sentiment."""
    from marketmind.ml.text import ASPECT_LABELS, detect_aspects, split_clauses
    suite, _ = sentiment_suite(get_run(run_id))
    if suite is None:
        raise HTTPException(409, "The trained model is not on disk for this run (retrain by starting a new run).")
    text = body.text.strip()
    with _suite_lock:   # one prediction at a time on the shared models
        p = suite.predict_proba([text])[0]
        attention = suite.neural.explain(text) if suite.neural is not None else []
        aspects = []
        for clause in split_clauses(text):
            for a in detect_aspects(clause):
                s = float(suite.score_clauses([clause])[0])
                aspects.append(dict(clause=clause, aspect=ASPECT_LABELS[a], score=round(s, 3),
                                    polarity="positive" if s > 0.2 else "negative" if s < -0.2 else "neutral"))
    labels = ["negative", "neutral", "positive"]
    return dict(label=labels[int(p.argmax())], probabilities={k: round(float(v), 4) for k, v in zip(labels, p, strict=True)},
                attention=[[str(t), float(w)] for t, w in attention], aspects=aspects)


# ------------------------------------------------------------------------------------------------ data
@router.get("/{run_id}/datasets/{name}")
def preview_dataset(run_id: str, name: str, limit: int = Query(2000, ge=1, le=10_000)) -> dict:
    """The first rows of a raw dataset the run studied."""
    if name not in DATASETS:
        raise HTTPException(404, f"No dataset {name!r}; the datasets are: {', '.join(DATASETS)}")
    run = get_run(run_id)
    spec = DATASETS[name]
    f = Path((run.meta.get("options") or {}).get("data_dir") or DATA_RAW.parent) / "raw" / spec["file"]
    info = dict(name=name, file=spec["file"], description=spec["description"], source=spec["source"])
    if not f.is_file():
        return dict(info, available=False, columns=[], data=[], total=0, offset=0, truncated=False)
    df = pd.read_csv(f, nrows=limit + 1)      # one row more than shown tells whether the file goes on
    return dict(info, available=True, **dict(frame(df.head(limit)), truncated=len(df) > limit))
