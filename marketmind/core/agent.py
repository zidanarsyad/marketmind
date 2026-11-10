"""Agent abstraction.

Every agent follows the same loop: perceive (read the blackboard) -> reason (think, optionally
with the LLM) -> act (call its registered tools) -> publish (artefacts + findings). Tool calls,
thoughts and findings are traced, so the dashboard can replay exactly how each conclusion
was reached.
"""
from __future__ import annotations

import json
import time
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from .blackboard import Blackboard
from .events import Tracer
from .findings import Finding
from .llm import LLMClient

OPEN_QUESTION = "open question"   # tag of the finding an agent publishes when it cannot answer a follow-up question

GROUNDING_RULES = (
    "Ground rules: use only the FACTS provided. Never invent numbers - every number you write must appear in the "
    "facts (rounding is fine). Do not speculate about data you were not given. When you use a finding, cite its ID "
    "in square brackets, e.g. [CMP-02]. Write concise, specific business English for a marketing director."
)


class AgentTimeout(RuntimeError):
    """Raised at an agent's next tool or LLM call once it has used up its time limit (a cooperative timeout)."""


@dataclass
class RunContext:
    run_id: str
    blackboard: Blackboard
    tracer: Tracer
    llm: LLMClient
    run_dir: Path
    options: dict[str, Any] = field(default_factory=dict)
    approver: Callable[[str, dict], Any] | None = None   # answers the human approval gates (core/approval.py)
    llm_baseline: tuple[int, int] = (0, 0)              # LLM calls and tokens already used when the run started


@dataclass
class AgentResult:
    agent: str
    status: str                  # completed | failed | skipped
    summary: str = ""
    seconds: float = 0.0
    findings: int = 0
    tool_calls: int = 0
    llm_calls: int = 0
    error: str | None = None
    attempts: int = 1            # more than 1 when the workflow retried the agent after a failure

    def to_dict(self) -> dict:
        return asdict(self)


class BaseAgent:
    name = "Agent"
    role = ""
    goal = ""
    ml_capability = ""           # non-empty for agents that train / apply ML or DL models
    finding_prefix = ""          # ID prefix of this agent's findings, e.g. "MKT" (used to answer follow-up requests)
    requires: tuple[str, ...] = ()   # datasets the agent cannot work without; the Director plans around missing ones

    def __init__(self, ctx: RunContext):
        self.ctx = ctx
        self.bb: Blackboard = ctx.blackboard
        self.tracer: Tracer = ctx.tracer
        self.llm: LLMClient = ctx.llm
        self.tools: dict[str, tuple[Callable, str]] = {}
        self._tool_calls = 0
        self._llm_calls = 0
        self._findings = 0
        self.time_limit: float | None = None   # seconds, set by the workflow; enforced at tool and LLM calls
        self.deadline: float | None = None
        self.register_tools()

    # ---------------------------------------------------------------- tools
    def register_tools(self) -> None:
        """Subclasses register the tools they are allowed to use."""

    def tool(self, name: str, fn: Callable, description: str) -> None:
        self.tools[name] = (fn, description)

    def use(self, name: str, *args, **kwargs) -> Any:
        self._check_deadline()
        fn, description = self.tools[name]
        self.emit("action", f"{name} - {description}", tool=name)
        t0 = time.time()
        result = fn(*args, **kwargs)
        self._tool_calls += 1
        self.emit("observation", f"{name} done in {time.time() - t0:.1f}s{_describe(result)}", tool=name)
        return result

    # ---------------------------------------------------------------- tracing helpers
    def emit(self, kind: str, message: str, **data: Any) -> None:
        self.tracer.emit(self.name, kind, message, **data)

    def think(self, message: str, **data: Any) -> None:
        self.emit("thought", message, **data)

    def warn(self, message: str, **data: Any) -> None:
        self.emit("warning", message, **data)

    def put(self, key: str, value: Any, description: str = "") -> None:
        self.bb.put(key, value, agent=self.name, description=description)

    def publish(self, finding: Finding) -> Finding:
        finding.agent = self.name
        self.bb.add_finding(finding)
        self._findings += 1
        self.emit("finding", finding.as_text(), id=finding.id, impact=finding.impact,
                  confidence=finding.confidence, area=finding.area)
        return finding

    def tell(self, recipient: str, content: str, **data: Any) -> None:
        self.bb.post(self.name, recipient, content, **data)
        self.emit("message", f"-> {recipient}: {content}")

    @property
    def options(self) -> dict:
        return self.ctx.options

    # ---------------------------------------------------------------- LLM reasoning
    def ask_llm(self, task: str, facts: Any, max_tokens: int = 700, as_json: bool = False):
        if not self.llm.available or not self.options.get("use_llm", True):
            return None
        self._check_deadline()
        spent = self._llm_budget_spent()
        if spent:
            self.warn(f"LLM budget for this run is used up ({spent}); using deterministic reasoning")
            return None
        system = f"You are the {self.name} in a multi-agent market research team. Role: {self.role} " \
                 f"Goal: {self.goal}\n{GROUNDING_RULES}"
        payload = json.dumps(facts, ensure_ascii=False, default=str)
        if len(payload) > 14000:
            payload = payload[:14000] + " ...(truncated)"
        prompt = f"{task}\n\nFACTS (JSON):\n{payload}"
        self._llm_calls += 1
        self.emit("llm", f"asking {self.llm.describe()}: {task[:90]}")
        if as_json:
            out = self.llm.complete_json(system, prompt, max_tokens=max_tokens, agent=self.name)
        else:
            out = self.llm.complete(system, prompt, max_tokens=max_tokens, agent=self.name)
        if out is None:
            self.warn(f"LLM unavailable ({self.llm.last_error}); using deterministic reasoning")
        return out

    def _llm_budget_spent(self) -> str:
        """Non-empty when the run's LLM budget (options['budget']: llm_calls, llm_tokens) is used up."""
        budget = self.options.get("budget") or {}
        stats, (calls0, tokens0) = self.llm.stats, self.ctx.llm_baseline
        calls, tokens = stats.calls - calls0, stats.prompt_tokens + stats.completion_tokens - tokens0
        if budget.get("llm_calls") is not None and calls >= budget["llm_calls"]:
            return f"{calls} of {budget['llm_calls']} calls"
        if budget.get("llm_tokens") is not None and tokens >= budget["llm_tokens"]:
            return f"{tokens:,} of {budget['llm_tokens']:,} tokens"
        return ""

    def _check_deadline(self) -> None:
        if self.deadline is not None and time.time() > self.deadline:
            raise AgentTimeout(f"{self.name} used up its {self.time_limit:.0f}s time limit")

    # ---------------------------------------------------------------- follow-up requests from the Research Director
    def requests(self) -> list[dict]:
        """Research questions the Director has sent this agent back to answer and that it has not answered yet."""
        answered = set(self.bb.get("followups.answered", []))
        return [m.data["question"] for m in self.bb.inbox(self.name)
                if isinstance(m.data.get("question"), dict) and f"{self.name}|{m.data['question']['id']}" not in answered]

    def answer_requests(self) -> list[str]:
        """Answer each follow-up question from this agent's findings, or say plainly that it stays open.

        A question is answered when the agent has a finding in the question's area. Otherwise it publishes an
        'open question' finding (ID <prefix>-9<n> for question Qn), which the Critic counts as addressed but not
        answered and the report lists under its limitations, so a gap is never passed off as an answer.
        """
        replies, answered = [], list(self.bb.get("followups.answered", []))
        for q in self.requests():
            areas = {q["area"]} | ({"pricing"} if q["area"] == "segmentation" else set())
            mine = [f for f in self.bb.findings(agent=self.name) if f.area in areas and OPEN_QUESTION not in f.tags]
            if mine:
                reply = f"{q['id']} is answered by {', '.join(f.id for f in mine[:4])}"
            else:
                fid = f"{self.finding_prefix or 'GEN'}-9{q['id'].lstrip('Q')[-1]}"
                self.publish(Finding(
                    id=fid, agent=self.name, area=q["area"], title=f"Open question: {q['id']}",
                    statement=(f"Asked by the Research Director to answer {q['id']} ('{q['question']}'), the {self.name} "
                               f"found no evidence strong enough to report, so this question stays open."),
                    metrics=dict(question=q["id"]), evidence=["follow-up request from the Research Director"],
                    impact=1, confidence=0.5, tags=[OPEN_QUESTION]))
                reply = f"{q['id']} has no conclusive answer; published {fid} as an open question"
            answered.append(f"{self.name}|{q['id']}")
            self.tell("Research Director", reply, question_id=q["id"])
            replies.append(reply)
        if replies:
            self.put("followups.answered", answered, "Follow-up questions already answered, as agent|question")
        return replies

    def run_follow_up(self) -> AgentResult:
        """Answer the Director's follow-up requests from what this agent already found, without redoing its work."""
        self.emit("status", "started", role=self.role, follow_up=True)
        t0 = time.time()
        try:
            summary = "; ".join(self.answer_requests()) or "no open requests"
        except Exception as exc:
            self.emit("error", f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc(limit=6))
            self.emit("status", "failed", seconds=round(time.time() - t0, 2))
            return AgentResult(self.name, "failed", seconds=round(time.time() - t0, 2),
                               error=f"{type(exc).__name__}: {exc}", findings=self._findings)
        seconds = round(time.time() - t0, 2)
        self.emit("status", "completed", seconds=seconds, summary=summary)
        return AgentResult(self.name, "completed", summary=summary, seconds=seconds, findings=self._findings,
                           tool_calls=self._tool_calls, llm_calls=self._llm_calls)

    # ---------------------------------------------------------------- lifecycle
    def execute(self) -> str:
        raise NotImplementedError

    def run(self) -> AgentResult:
        self.emit("status", "started", role=self.role)
        t0 = time.time()
        if self.time_limit:
            self.deadline = t0 + self.time_limit
        try:
            summary = self.execute() or ""
            if self.requests():           # sent back by the Director: answer its questions as part of this run
                summary = "; ".join([summary] + self.answer_requests())
        except Exception as exc:
            tb = traceback.format_exc(limit=6)
            self.emit("error", f"{type(exc).__name__}: {exc}", traceback=tb)
            self.emit("status", "failed", seconds=round(time.time() - t0, 2))
            return AgentResult(self.name, "failed", seconds=round(time.time() - t0, 2), error=f"{type(exc).__name__}: {exc}",
                               tool_calls=self._tool_calls, llm_calls=self._llm_calls, findings=self._findings)
        seconds = round(time.time() - t0, 2)
        self.emit("status", "completed", seconds=seconds, summary=summary)
        return AgentResult(self.name, "completed", summary=summary, seconds=seconds, findings=self._findings,
                           tool_calls=self._tool_calls, llm_calls=self._llm_calls)


def _describe(result: Any) -> str:
    if hasattr(result, "shape"):
        return f" -> {result.shape[0]:,} rows" if len(result.shape) else ""
    if isinstance(result, dict):
        return f" -> {len(result)} items"
    if isinstance(result, (list, tuple)):
        return f" -> {len(result)} items"
    return ""
