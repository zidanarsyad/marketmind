"""Human approval gates: the points where a person can approve, trim or stop a study.

There are two gates. The research plan is reviewed after the Research Director has planned and before any analysis
agent runs; the recommendations are reviewed after the Strategy agent has drafted them and before it writes the
executive summary, so nothing the reviewer drops can reach the report.

Whoever answers a gate returns a Decision: a person at the terminal (`run.py --approve`), the dashboard, a test, or
nobody, in which case the gate approves automatically and says so. Every decision is traced as an `approval` event
and kept on the blackboard (`approvals`), so the report and run_meta.json show who approved what.
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

GATES = ("plan", "recommendations")
# exceptions an agent raises on purpose; the workflow does not retry them
NON_RETRYABLE = ("AgentTimeout", "StudyRejected")


class StudyRejected(RuntimeError):
    """Raised when a reviewer rejects the study at a gate: the run stops with status 'rejected'."""


@dataclass
class Decision:
    approved: bool
    reviewer: str = "auto"
    comment: str = ""
    drop: list[str] = field(default_factory=list)  # plan: modules to leave out; recommendations: IDs to remove

    def to_dict(self) -> dict:
        return asdict(self)


Approver = Callable[[str, dict], Decision]


def auto_approve(gate: str, proposal: dict) -> Decision:
    """The default when nobody is asked: approve, and record that no person reviewed it."""
    return Decision(True, reviewer="auto (no reviewer)")


def request_approval(ctx: Any, gate: str, proposal: dict, actor: str) -> Decision:
    """Ask the run's approver (ctx.approver) to decide a gate; trace and record the decision."""
    approver = getattr(ctx, "approver", None) or auto_approve
    try:
        decision = approver(gate, proposal)
    except Exception as exc:  # a broken reviewer UI must not hang or kill the study: approve, and say why
        decision = Decision(True, reviewer="auto (approver failed)", comment=f"{type(exc).__name__}: {exc}")
    if not isinstance(decision, Decision):
        decision = Decision(bool(decision), reviewer="unknown")
    decision.drop = [str(d) for d in decision.drop]
    record = dict(gate=gate, time=time.strftime("%Y-%m-%d %H:%M:%S"), **decision.to_dict())
    ctx.blackboard.put("approvals", list(ctx.blackboard.get("approvals", [])) + [record], agent=actor,
                       description="Decisions taken at the human approval gates")
    verdict = "approved" if decision.approved else "rejected"
    ctx.tracer.emit(actor, "approval", f"{gate} {verdict} by {decision.reviewer}"
                    + (f"; dropped {', '.join(decision.drop)}" if decision.drop else "")
                    + (f" - {decision.comment}" if decision.comment else ""), gate=gate, **decision.to_dict())
    return decision


# ---------------------------------------------------------------------------------------------- reviewers
def _split(answer: str) -> list[str]:
    return [p.strip() for p in answer.replace(";", ",").split(",") if p.strip()]


class ConsoleApprover:
    """Asks at the terminal: Enter or y approves, n rejects, a list of names or IDs drops those items."""

    def __init__(self, reviewer: str = "console reviewer", ask: Callable[[str], str] = input,
                 say: Callable[[str], Any] = print):
        self.reviewer, self.ask, self.say = reviewer, ask, say

    def __call__(self, gate: str, proposal: dict) -> Decision:
        if gate == "plan":
            self.say(f"\n--- Approve the research plan for {proposal['client']} ---")
            self.say(f"Modules: {', '.join(proposal['modules'])}")
            for q in proposal["questions"]:
                self.say(f"  {q['id']} [{q['area']}] {q['question']}")
            prompt = "Approve? Enter = yes, n = reject the study, or modules to leave out (e.g. pricing,forecast): "
        else:
            self.say("\n--- Approve the recommendations ---")
            for r in proposal["recommendations"]:
                self.say(f"  {r['id']}. {r['title']} (priority {r['priority']:.2f}; evidence {', '.join(r['evidence'])})")
            prompt = "Approve? Enter = all, n = reject the study, or IDs to drop (e.g. R2,R5): "
        answer = self.ask(prompt).strip()
        if answer.lower() in ("n", "no", "reject"):
            return Decision(False, self.reviewer, self.ask("Reason (optional): ").strip())
        if answer.lower() in ("", "y", "yes", "ok", "approve"):
            return Decision(True, self.reviewer)
        return Decision(True, self.reviewer, self.ask("Comment (optional): ").strip(), drop=_split(answer))


class ApprovalBroker:
    """Hands a gate from the study's thread to a user interface thread (the dashboard) and waits for the answer.

    The study calls the broker like any approver and blocks; the interface sees `pending`, shows the proposal and
    calls `decide()`. With a timeout, an unanswered gate approves automatically and says so.
    """

    def __init__(self, reviewer: str = "dashboard reviewer", timeout: float | None = None):
        self.reviewer, self.timeout = reviewer, timeout
        self._lock = threading.Lock()
        self._answered = threading.Event()
        self._decision: Decision | None = None
        self.pending: tuple[str, dict] | None = None

    def __call__(self, gate: str, proposal: dict) -> Decision:
        with self._lock:
            self._decision, self.pending = None, (gate, proposal)
            self._answered.clear()
        answered = self._answered.wait(self.timeout)
        with self._lock:
            decision = self._decision if answered and self._decision else Decision(True, "auto (no answer in time)")
            self.pending = None
        return decision

    def decide(self, decision: Decision) -> None:
        with self._lock:
            self._decision = decision
            self._answered.set()
