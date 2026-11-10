"""Studies started from the web app: a server-side registry, the live trace over SSE, and the two approval gates.

A study runs ``MarketResearchSystem`` in a background thread, as the Streamlit dashboard does, but the registry lives
in the server rather than in one browser session: reloading the page, or opening the app in another tab, finds the
study again, including one paused at an approval gate. One study runs at a time.
"""
from __future__ import annotations

import asyncio
import json
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from marketmind.core.approval import ApprovalBroker, Decision

from .security import clean, scrub

router = APIRouter(prefix="/api/studies", tags=["studies"])

REVIEWER = "web reviewer"
GATE_TIMEOUT = 1800       # a gate left unanswered for 30 minutes approves automatically, and the record says so


@dataclass
class Study:
    id: str
    system: Any                       # marketmind.system.MarketResearchSystem
    broker: ApprovalBroker | None
    options: dict
    created: float = field(default_factory=time.time)
    thread: threading.Thread | None = None
    result: Any = None                # marketmind.system.RunResult once the study has finished
    error: str | None = None
    finished: float | None = None
    decisions: list[dict] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)
    _answered: Any = None             # the proposal last answered, until the study moves past its gate

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    def pending(self) -> tuple[str, dict] | None:
        """The gate waiting for a decision, if any (not one answered a moment ago that the study has yet to leave)."""
        pending = self.broker.pending if self.broker is not None else None
        if pending is None or pending[1] is self._answered:
            return None
        return pending

    @property
    def state(self) -> str:
        if self.running:
            return "waiting" if self.pending() else "running"
        if self.error:
            return "error"
        return getattr(self.result, "status", None) or "starting"

    def snapshot(self) -> dict:
        pending = self.pending()
        res = self.result
        qa = (getattr(res, "qa", None) or {}) if res is not None else {}
        return clean(dict(
            id=self.id, state=self.state, client=self.options.get("client"), created=self.created, finished=self.finished,
            options={k: v for k, v in self.options.items() if k != "brief"}, brief=self.options.get("brief"),
            review=self.broker is not None,
            pending=dict(gate=pending[0], proposal=pending[1]) if pending else None,
            result=dict(status=res.status, seconds=res.seconds, qa_score=qa.get("score"), qa_passed=qa.get("passed"))
            if res is not None else None,
            error=self.error, saved=(self.system.run_dir / "run_meta.json").is_file(), decisions=self.decisions))


class StudyBusy(RuntimeError):
    pass


class StudyRegistry:
    """The studies this server has started, newest last."""

    def __init__(self, keep: int = 20):
        self.keep = keep
        self._studies: dict[str, Study] = {}
        self._lock = threading.Lock()

    def active(self) -> Study | None:
        with self._lock:
            return next((s for s in self._studies.values() if s.running), None)

    def get(self, study_id: str) -> Study | None:
        with self._lock:
            return self._studies.get(study_id)

    def all(self) -> list[Study]:
        with self._lock:
            return list(self._studies.values())

    def start(self, llm, brief: str, client: str | None, use_llm: bool, sentiment_data: str, retrain: bool,
              parallel: bool, review: bool) -> Study:
        from marketmind import system as system_module
        with self._lock:
            if any(s.running for s in self._studies.values()):
                raise StudyBusy("A study is already running; open it, or wait until it has finished.")
            # run ids are timestamps to the second: never reuse the folder of a run that just ended
            while (system_module.RUNS_DIR / time.strftime("%Y%m%d-%H%M%S")).exists():
                time.sleep(0.2)
            broker = ApprovalBroker(reviewer=REVIEWER, timeout=GATE_TIMEOUT) if review else None
            system = system_module.MarketResearchSystem(
                brief=brief, client=client, use_llm=use_llm, force_retrain=retrain, parallel=parallel, llm=llm,
                sentiment_data=sentiment_data, approver=broker)
            study = Study(id=system.run_id, system=system, broker=broker,
                          options=dict(brief=brief, client=client, use_llm=system.options["use_llm"],
                                       sentiment_data=sentiment_data, retrain=retrain, parallel=parallel, review=review))

            def target() -> None:
                try:
                    study.result = system.run()
                except Exception as exc:  # shown in the live view
                    study.error = f"{type(exc).__name__}: {exc}"
                finally:
                    study.finished = time.time()

            study.thread = threading.Thread(target=target, daemon=True, name=f"study-{system.run_id}")
            self._studies[study.id] = study
            finished = [s for s in self._studies.values() if not s.running and s is not study]
            while len(self._studies) > self.keep and finished:   # forget the oldest finished studies
                self._studies.pop(finished.pop(0).id, None)
            study.thread.start()
            return study


# ------------------------------------------------------------------------------------------------ endpoints
def registry(request: Request) -> StudyRegistry:
    return request.app.state.studies


def get_study(request: Request, study_id: str) -> Study:
    study = registry(request).get(study_id)
    if study is None:
        raise HTTPException(404, f"No study {study_id!r} on this server (it may have been started before a restart; "
                                 "saved runs are under /api/runs).")
    return study


class StudyIn(BaseModel):
    brief: str = Field(min_length=1, max_length=4000)
    client: str | None = Field(None, max_length=120)
    use_llm: bool = True
    sentiment_data: Literal["study", "study+real", "real"] = "study"
    retrain: bool = False
    parallel: bool = True
    review: bool = False


@router.get("")
def list_studies(request: Request) -> list[dict]:
    """Studies started since the server started, newest first; ``state`` is running, waiting (at a gate) or how it ended."""
    return [s.snapshot() for s in reversed(registry(request).all())]


@router.post("", status_code=201)
def start_study(body: StudyIn, request: Request) -> dict:
    """Start a study in the background. With ``review`` it pauses at the plan and recommendation gates."""
    from marketmind.ml import real_reviews

    from .system_info import brands_in_data, data_ready
    if not data_ready():
        raise HTTPException(409, "No datasets found. Generate them first (POST /api/data/generate).")
    brands = brands_in_data()
    client = (body.client or "").strip() or None
    if client and client.lower() not in {b.lower() for b in brands}:
        raise HTTPException(422, f"Unknown client {client!r}; the data covers: {', '.join(brands)}")
    if body.sentiment_data != "study" and not real_reviews.available():
        raise HTTPException(422, "The real review corpus is not downloaded (docs/DATA_SOURCES.md); train on the study's reviews.")
    llm = request.app.state.llm
    try:
        study = registry(request).start(llm, body.brief.strip(), client, body.use_llm and llm.available,
                                        body.sentiment_data, body.retrain, body.parallel, body.review)
    except StudyBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    return study.snapshot()


@router.get("/{study_id}")
def study_status(study_id: str, request: Request) -> dict:
    return get_study(request, study_id).snapshot()


@router.get("/{study_id}/approval")
def pending_approval(study_id: str, request: Request) -> dict:
    """The proposal waiting at a gate: the research plan, or the recommendations before the report is written."""
    pending = get_study(request, study_id).pending()
    return clean(dict(pending=pending is not None, gate=pending[0] if pending else None,
                      proposal=pending[1] if pending else None))


class DecisionIn(BaseModel):
    gate: Literal["plan", "recommendations"]
    approved: bool
    comment: str = Field("", max_length=1000)
    drop: list[str] = Field(default_factory=list, max_length=50)


@router.post("/{study_id}/approval")
def decide(study_id: str, body: DecisionIn, request: Request) -> dict:
    """Approve (optionally leaving out modules or recommendations) or reject the study at the waiting gate."""
    study = get_study(request, study_id)
    if study.broker is None:
        raise HTTPException(409, "This study runs without review: its gates approve automatically.")
    with study.lock:
        pending = study.pending()
        if pending is None:
            raise HTTPException(409, "No approval is waiting (it may just have been answered).")
        gate, proposal = pending
        if body.gate != gate:
            raise HTTPException(409, f"The study is waiting at the {gate} gate, not the {body.gate} gate.")
        items = proposal["modules"] if gate == "plan" else [r["id"] for r in proposal["recommendations"]]
        unknown = [d for d in body.drop if d not in items]
        if unknown:
            raise HTTPException(422, f"Not in the proposal: {', '.join(unknown)}")
        drop = list(dict.fromkeys(body.drop)) if body.approved else []
        if body.approved and len(drop) == len(items):
            raise HTTPException(422, "Nothing would be left. Keep at least one item, or reject the study.")
        decision = Decision(body.approved, study.broker.reviewer, body.comment.strip(), drop=drop)
        study._answered = proposal
        study.decisions.append(dict(gate=gate, **decision.to_dict()))
        study.broker.decide(decision)
    return dict(ok=True, gate=gate, approved=body.approved, drop=drop)


def sse(data: Any, event: str | None = None, event_id: int | None = None) -> str:
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    if event:
        lines.append(f"event: {event}")
    lines.append("data: " + scrub(json.dumps(clean(data), ensure_ascii=False, separators=(",", ":"))))
    return "\n".join(lines) + "\n\n"


@router.get("/{study_id}/events")
async def stream_events(study_id: str, request: Request, after: int = -1) -> StreamingResponse:
    """Server-sent events: every trace event (``trace``, with its index as the event id), the study's state when it
    changes (``state``, with the proposal when a gate waits) and ``end`` when it has finished.

    A reconnecting browser sends Last-Event-ID and gets only the events it missed.
    """
    study = get_study(request, study_id)
    last = request.headers.get("last-event-id", "")
    start = int(last) + 1 if last.isdigit() else max(after + 1, 0)

    async def events():
        sent, last_state, quiet = start, None, 0.0
        yield "retry: 2000\n\n"
        while True:
            trace = study.system.tracer.snapshot()
            for i in range(sent, len(trace)):
                yield sse(trace[i].to_dict(), "trace", i)
            sent = max(sent, len(trace))
            state = study.snapshot()
            if state != last_state:
                yield sse(state, "state")
                last_state, quiet = state, 0.0
            if not study.running and sent >= len(study.system.tracer.events):
                yield sse(state, "end")
                return
            if await request.is_disconnected():
                return
            await asyncio.sleep(0.4)
            quiet += 0.4
            if quiet >= 15:                   # keep idle proxies from closing the stream while a gate waits
                yield ": keep-alive\n\n"
                quiet = 0.0

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
