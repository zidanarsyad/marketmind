"""Workflow engine: executes agents as a dependency graph (DAG).

Tasks whose dependencies are satisfied run concurrently on a thread pool, so the five analysis
agents work in parallel once the data is clean. A task that fails is retried (once by default),
unless it ran out of time or a reviewer rejected the study. If a critical task still fails,
everything that depends on it is skipped (and reported) instead of crashing the run.
"""
from __future__ import annotations

import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass

from .agent import AgentResult, BaseAgent, RunContext
from .approval import NON_RETRYABLE


@dataclass
class Task:
    id: str
    agent: type[BaseAgent]
    depends_on: tuple[str, ...] = ()
    critical: bool = True
    retries: int = 1                 # extra attempts after a failure (never after a timeout or a rejection)
    timeout: float | None = None     # seconds; the agent stops at its next tool or LLM call once it is over


class Workflow:
    def __init__(self, tasks: list[Task]):
        self.tasks = {t.id: t for t in tasks}
        self.layers = self._toposort()

    def _toposort(self) -> list[list[str]]:
        for t in self.tasks.values():
            missing = [d for d in t.depends_on if d not in self.tasks]
            if missing:
                raise ValueError(f"Task '{t.id}' depends on unknown task(s) {missing}")
        indeg = {tid: len(t.depends_on) for tid, t in self.tasks.items()}
        layers, done = [], set()
        while len(done) < len(self.tasks):
            layer = sorted(tid for tid, d in indeg.items() if tid not in done and d == 0)
            if not layer:
                raise ValueError("Workflow has a dependency cycle")
            layers.append(layer)
            done.update(layer)
            for tid, t in self.tasks.items():
                if tid not in done:
                    indeg[tid] = sum(1 for d in t.depends_on if d not in done)
        return layers

    def edges(self) -> list[tuple[str, str]]:
        return [(d, t.id) for t in self.tasks.values() for d in t.depends_on]

    def run(self, ctx: RunContext, parallel: bool = True, max_workers: int = 3) -> dict[str, AgentResult]:
        results: dict[str, AgentResult] = {}
        pending = set(self.tasks)
        running = {}
        attempts: dict[str, int] = {}

        def submit(tid: str) -> None:
            task = self.tasks[tid]
            agent = task.agent(ctx)
            agent.time_limit = task.timeout
            attempts[tid] = attempts.get(tid, 0) + 1
            running[pool.submit(agent.run)] = tid

        with ThreadPoolExecutor(max_workers=max_workers if parallel else 1) as pool:
            while pending or running:
                for tid in sorted(pending):
                    task = self.tasks[tid]
                    if not all(d in results for d in task.depends_on):
                        continue
                    blocked = [d for d in task.depends_on
                               if results[d].status != "completed" and self.tasks[d].critical]
                    if blocked:
                        results[tid] = AgentResult(task.agent.name, "skipped", error=f"upstream failed: {blocked}")
                        ctx.tracer.emit(task.agent.name, "status", "skipped", reason=f"upstream failed: {blocked}")
                        pending.discard(tid)
                        continue
                    if parallel or not running:
                        submit(tid)
                        pending.discard(tid)
                if not running:
                    if pending:  # nothing runnable: unresolved dependencies
                        for tid in pending:
                            results[tid] = AgentResult(self.tasks[tid].agent.name, "skipped", error="unresolved dependencies")
                        pending.clear()
                    break
                finished, _ = wait(list(running), return_when=FIRST_COMPLETED)
                for fut in finished:
                    tid = running.pop(fut)
                    task = self.tasks[tid]
                    try:
                        result = fut.result()
                    except Exception as exc:  # BaseAgent.run already catches; this is a last resort
                        result = AgentResult(task.agent.name, "failed", error=str(exc))
                    error = result.error or ""
                    if (result.status == "failed" and attempts[tid] <= task.retries
                            and not error.startswith(NON_RETRYABLE)):
                        ctx.tracer.emit(task.agent.name, "warning", f"failed ({error[:160]}); retrying, attempt "
                                        f"{attempts[tid] + 1} of {task.retries + 1}", attempt=attempts[tid] + 1)
                        time.sleep(0.5)
                        submit(tid)
                        continue
                    result.attempts = attempts[tid]
                    results[tid] = result
        return results
