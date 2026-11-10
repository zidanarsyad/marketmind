"""MarketResearchSystem: the entry point that wires the agents together and runs a study."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .config import DEFAULT_BRIEF, RUNS_DIR, ensure_dirs
from .core.agent import AgentResult, RunContext
from .core.blackboard import Blackboard
from .core.events import Tracer
from .core.llm import LLMClient
from .core.store import save_run
from .ml.real_reviews import TRAINING_MODES
from .agents import PIPELINE_AGENTS, ResearchDirectorAgent
from .agents.director import DEFAULT_AGENT_TIMEOUT

# per-run LLM budget: a full study uses about 9 calls (more with revisions); free tiers allow far more per day
DEFAULT_BUDGET = dict(llm_calls=40, llm_tokens=300_000)


@dataclass
class RunResult:
    run_id: str
    run_dir: Path
    status: str
    seconds: float
    qa: dict
    results: dict[str, AgentResult]


class MarketResearchSystem:
    """Run a complete market research study: plan -> approve -> collect -> clean -> analyse -> strategise (approve the
    recommendations) -> report -> QA, with the Research Director sending agents back for questions left open.

    approver answers the two human approval gates (core/approval.py); without one they approve automatically.
    retries, agent_timeout and budget bound each agent's attempts and time and the run's LLM use.
    """

    def __init__(self, brief: str | None = None, client: str | None = None, use_llm: bool = True,
                 force_retrain: bool = False, parallel: bool = True, llm: LLMClient | None = None,
                 echo: bool = False, max_revisions: int = 2, sentiment_data: str = "study",
                 approver: Callable[[str, dict], Any] | None = None, retries: int = 1,
                 agent_timeout: float | None = None, budget: dict | None = None):
        if sentiment_data not in TRAINING_MODES:
            raise ValueError(f"sentiment_data must be one of {TRAINING_MODES}, not {sentiment_data!r}")
        ensure_dirs()
        self.run_id = time.strftime("%Y%m%d-%H%M%S")
        self.run_dir = RUNS_DIR / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.tracer = Tracer(self.run_id, echo=echo)
        self.blackboard = Blackboard()
        self.llm = llm or LLMClient()
        self.options = dict(brief=brief or DEFAULT_BRIEF, client=client, use_llm=use_llm and self.llm.available,
                            force_retrain=force_retrain, parallel=parallel, sentiment_data=sentiment_data,
                            retries=retries, agent_timeout=agent_timeout or DEFAULT_AGENT_TIMEOUT,
                            budget={**DEFAULT_BUDGET, **(budget or {})}, approval="human" if approver else "auto")
        self.max_revisions = max_revisions
        stats = self.llm.stats   # a dashboard reuses one client across runs: the budget counts from here
        self.ctx = RunContext(self.run_id, self.blackboard, self.tracer, self.llm, self.run_dir, self.options,
                              approver=approver, llm_baseline=(stats.calls, stats.prompt_tokens + stats.completion_tokens))
        self.status = "created"
        self.workflow = None

    def run(self) -> RunResult:
        t0 = time.time()
        self.status = "running"
        self.tracer.emit("System", "status", "run started", llm=self.llm.describe(), run_id=self.run_id)
        director = ResearchDirectorAgent(self.ctx)
        results = {"plan": director.run()}
        if results["plan"].status != "completed":
            return self._finish(t0, results, "failed")
        if not director.review_plan().approved:
            return self._finish(t0, results, "rejected")
        self.workflow = director.build_workflow()
        results.update(self.workflow.run(self.ctx, parallel=self.options["parallel"]))
        if results.get("qa") and results["qa"].status == "completed":
            results = director.supervise(results, self.workflow)
            results = director.quality_loop(results, self.max_revisions)
        if any(not a["approved"] for a in self.blackboard.get("approvals", [])):
            return self._finish(t0, results, "rejected")
        critical = [k for k in ("collect", "quality", "strategy", "report") if results.get(k) and results[k].status != "completed"]
        # a report the Critic never checked is not "completed": it is released, but marked unverified
        status = "failed" if critical else "completed" if self.blackboard.has("qa.result") else "unverified"
        return self._finish(t0, results, status)

    def _finish(self, t0: float, results: dict[str, AgentResult], status: str) -> RunResult:
        self.status = status
        seconds = round(time.time() - t0, 1)
        qa = self.blackboard.get("qa.result") or {}
        self._append_qa_certificate(qa)
        plan = self.blackboard.get("plan") or {}
        wf = self.workflow
        meta = dict(
            run_id=self.run_id, status=status, started=time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t0)),
            seconds=seconds, brief=self.options["brief"], client=plan.get("client"), plan=plan,
            options={k: v for k, v in self.options.items() if k != "brief"},
            llm=dict(provider=self.llm.provider, model=self.llm.model, description=self.llm.describe(),
                     stats=self.llm.stats.to_dict(), last_error=self.llm.last_error),
            agents={k: r.to_dict() for k, r in results.items()},
            agent_roster=[dict(name=a.name, role=a.role, goal=a.goal, ml=a.ml_capability) for a in PIPELINE_AGENTS],
            workflow=dict(layers=wf.layers if wf else [], edges=wf.edges() if wf else [],
                          tasks={tid: t.agent.name for tid, t in wf.tasks.items()} if wf else {}),
            qa=dict(score=qa.get("score"), passed=qa.get("passed"), revisions=qa.get("revision", 0),
                    history=self.blackboard.get("qa.history", [])),
            approvals=self.blackboard.get("approvals", []),
            adaptations=self.blackboard.get("director.adaptations", []),
            messages=[dict(sender=m.sender, recipient=m.recipient, content=m.content) for m in self.blackboard.messages()],
        )
        self.tracer.emit("System", "status", f"run {status} in {seconds}s", qa_score=qa.get("score"))
        save_run(self.run_dir, self.blackboard, self.tracer, meta)
        return RunResult(self.run_id, self.run_dir, status, seconds, qa, results)

    def _append_qa_certificate(self, qa: dict) -> None:
        if not self.blackboard.has("report.markdown"):
            return
        if not qa:  # the Critic did not finish: say so in the report rather than staying silent
            from .reporting.html_report import qa_not_verified_html
            note = ("\n\n## QA Certificate\n\nVerdict: **NOT VERIFIED** - the Critic agent did not complete, so the numbers, "
                    "citations and coverage of this report were not checked. The run trace records the error.")
            self.blackboard.put("report.markdown", self.blackboard.get("report.markdown") + note, "System", "Report + QA notice")
            html = self.blackboard.get("report.html")
            if html:
                html = html.replace("<!--QA-CERTIFICATE-->", qa_not_verified_html()).replace(
                    "<!--QA-BADGE-->", '<span class="badge fail">QA not run - unverified</span>')
                self.blackboard.put("report.html", html, "System")
            return
        checks = qa.get("checks", {})
        rows = "\n".join(f"| {k} | {v.get('score', 0) * 100:.0f}% |" for k, v in checks.items())
        open_issues = "\n".join(f"- [{i['severity']}] {i['message']}" for i in qa.get("issues", [])) or "- none"
        cert = (f"\n\n## QA Certificate\n\nVerdict: **{'PASSED' if qa.get('passed') else 'NOT PASSED'}** - score "
                f"{qa.get('score')}/100 after {qa.get('revision', 0)} revision(s); {qa.get('numbers_grounded')}/"
                f"{qa.get('numbers_checked')} numbers in the prose were traced to evidence.\n\n| Check | Score |\n| --- | --- |\n"
                f"{rows}\n\n**Open issues**\n\n{open_issues}")
        self.blackboard.put("report.markdown", self.blackboard.get("report.markdown") + cert, "System", "Report + QA certificate")
        html = self.blackboard.get("report.html")
        if html:
            from .reporting.html_report import qa_certificate_html
            badge = (f'<span class="badge {"pass" if qa.get("passed") else "fail"}">QA {"passed" if qa.get("passed") else "not passed"}'
                     f' - {qa.get("score")}/100</span>')
            html = html.replace("<!--QA-CERTIFICATE-->", qa_certificate_html(qa)).replace("<!--QA-BADGE-->", badge)
            self.blackboard.put("report.html", html, "System")
