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

GROUNDING_RULES = (
    "Ground rules: use only the FACTS provided. Never invent numbers - every number you write must appear in the "
    "facts (rounding is fine). Do not speculate about data you were not given. When you use a finding, cite its ID "
    "in square brackets, e.g. [CMP-02]. Write concise, specific business English for a marketing director."
)


@dataclass
class RunContext:
    run_id: str
    blackboard: Blackboard
    tracer: Tracer
    llm: LLMClient
    run_dir: Path
    options: dict[str, Any] = field(default_factory=dict)


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

    def to_dict(self) -> dict:
        return asdict(self)


class BaseAgent:
    name = "Agent"
    role = ""
    goal = ""
    ml_capability = ""           # non-empty for agents that train / apply ML or DL models

    def __init__(self, ctx: RunContext):
        self.ctx = ctx
        self.bb: Blackboard = ctx.blackboard
        self.tracer: Tracer = ctx.tracer
        self.llm: LLMClient = ctx.llm
        self.tools: dict[str, tuple[Callable, str]] = {}
        self._tool_calls = 0
        self._llm_calls = 0
        self._findings = 0
        self.register_tools()

    # ---------------------------------------------------------------- tools
    def register_tools(self) -> None:
        """Subclasses register the tools they are allowed to use."""

    def tool(self, name: str, fn: Callable, description: str) -> None:
        self.tools[name] = (fn, description)

    def use(self, name: str, *args, **kwargs) -> Any:
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

    # ---------------------------------------------------------------- lifecycle
    def execute(self) -> str:
        raise NotImplementedError

    def run(self) -> AgentResult:
        self.emit("status", "started", role=self.role)
        t0 = time.time()
        try:
            summary = self.execute() or ""
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
