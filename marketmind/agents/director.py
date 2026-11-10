"""Research Director: the orchestrating agent.

1. Plans: turns the free-text business brief into a structured research plan (client, scope,
   objectives, research questions, modules to run) - rule-based parsing, optionally refined by
   the LLM, always validated against the data actually available - and puts it to the human
   approval gate, applying the reviewer's edits.
2. Dispatches: builds the agent workflow (DAG) for the modules the plan needs, with retries and a
   time limit per agent.
3. Supervises: when the Critic finds a research question the report leaves open, it sends the
   responsible analysis agent back with that question (re-running it if it had failed) and has the
   strategy, report and QA redone; then it enforces the QA gate, sending a failing report back to
   the Report Writer for revision (bounded number of loops).
"""
from __future__ import annotations

import re
import time
import unicodedata

import pandas as pd

from .. import config
from ..config import DATASETS, DEFAULT_CLIENT
from ..core.agent import AgentResult, BaseAgent
from ..core.approval import Decision, request_approval
from ..core.orchestrator import Task, Workflow

AREAS = ["market", "competition", "consumer", "segmentation", "pricing", "forecast"]
AREA_KEYWORDS = {
    "market": ["market size", "market", "trend", "growth", "category", "categories", "channel", "region"],
    "competition": ["compet", "rival", "share", "position", "benchmark", "brand"],
    "consumer": ["consumer", "customer", "sentiment", "review", "pain point", "complaint", "perception", "social"],
    "segmentation": ["segment", "persona", "target", "audience", "concept"],
    "pricing": ["price", "pricing", "elastic", "willingness to pay"],
    "forecast": ["forecast", "demand", "outlook", "predict", "projection"],
}
QUESTION_TEMPLATES = {
    "market": "How large is the market, how fast is it growing, and which categories, channels and regions drive growth?",
    "competition": "How is {client} positioned versus competitors on share, momentum, price and channel presence, and who is the biggest threat?",
    "consumer": "What do consumers love and dislike about {client} and its competitors, and which pain points are emerging?",
    "segmentation": "Which consumer segments exist, and which should {client} target with the new concept?",
    "pricing": "How price-sensitive is demand, and at what price should the concept launch?",
    "forecast": "What is the 12-month demand outlook for the market and for {client}?",
    "strategy": "Where should {client} play and how can it win over the next 12 months?",
}
# which analysis task answers the questions of each area, and which task writes each report section
AREA_TASKS = {"market": ("market",), "competition": ("competition",), "consumer": ("consumer",),
              "segmentation": ("segmentation",), "pricing": ("segmentation", "forecast"), "forecast": ("forecast",)}
SECTION_TASKS = {"Market Overview": "market", "Competitive Landscape": "competition", "Consumer Insights": "consumer",
                 "Segments and Personas": "segmentation", "Demand Forecast": "forecast"}
DEFAULT_AGENT_TIMEOUT = 900.0   # seconds per agent; a first run trains the deep-learning model in about 2 minutes
DATASET_NAMES = {"sales": "the sales panel", "market_size": "the market-size table", "reviews": "product reviews",
                 "survey": "the consumer survey", "social": "social posts", "catalog": "the product catalogue"}


def module_requirements() -> dict[str, tuple[str, ...]]:
    """Datasets each analysis module needs, read from its agent's `requires` (pricing needs one of two agents)."""
    from . import (CompetitiveIntelligenceAgent, ConsumerInsightAgent, DemandForecastingAgent, MarketTrendAnalystAgent,
                   SegmentationAgent)
    return {"market": MarketTrendAnalystAgent.requires, "competition": CompetitiveIntelligenceAgent.requires,
            "consumer": ConsumerInsightAgent.requires, "segmentation": SegmentationAgent.requires,
            "forecast": DemandForecastingAgent.requires}


def _fold(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


class ResearchDirectorAgent(BaseAgent):
    name = "Research Director"
    role = "Orchestrator and planner. Turns a business brief into a research plan, dispatches specialist agents and enforces quality gates."
    goal = "Deliver a decision-ready, evidence-backed market research report that answers the client's questions."

    def register_tools(self):
        self.tool("scan_data_catalog", self._scan_catalog, "inspect available datasets, brands, categories and coverage")
        self.tool("parse_brief", self._rule_plan, "extract client, scope, horizon and questions from the brief (rule-based)")
        self.tool("refine_plan_with_llm", self._llm_refine, "let the LLM sharpen objectives and questions")
        self.tool("seek_plan_approval", self._seek_plan_approval, "put the research plan to the human approval gate")

    # ------------------------------------------------------------------ planning
    def execute(self) -> str:
        brief = self.options.get("brief", "")
        self.think("Reading the research brief and checking what data the team can use.")
        catalog = self.use("scan_data_catalog")
        plan = self.use("parse_brief", brief, catalog)
        if self.llm.available and self.options.get("use_llm", True):
            plan = self.use("refine_plan_with_llm", brief, catalog, plan)
        active = [a for a in AREAS if plan["modules"][a]]
        self.think(f"Plan ready for client '{plan['client']}': {len(plan['questions'])} research questions, "
                   f"modules = {', '.join(active)}; horizon {plan['horizon_months']} months.")
        self.put("plan", plan, "Structured research plan derived from the brief")
        return f"Planned {len(plan['questions'])} questions across {len(active)} analysis modules for {plan['client']}"

    def _scan_catalog(self) -> dict:
        """Brands, categories, channels and the period, from the sales panel or, without one, the reviews or catalogue."""
        raw = config.DATA_RAW
        available = {k: (raw / v["file"]).exists() for k, v in DATASETS.items()}
        source = next((k for k in ("sales", "reviews", "catalog") if available.get(k)), None)
        if source is None:
            raise ValueError(f"No sales panel, reviews or product catalogue in {raw}: there is nothing to study. "
                             "Run scripts/generate_data.py, or import real data (docs/DATA_SOURCES.md).")
        date_col = {"sales": "month", "reviews": "review_date", "catalog": None}[source]
        cols = [c for c in (date_col, "brand", "category", "channel") if c]
        df = pd.read_csv(raw / DATASETS[source]["file"], usecols=lambda c: c in cols)
        dates = pd.to_datetime(df[date_col]).dt.to_period("M").dt.to_timestamp() if date_col else None
        return dict(brands=sorted(df["brand"].dropna().unique()), categories=sorted(df["category"].dropna().unique()),
                    channels=sorted(df["channel"].astype(str).str.strip().unique()) if "channel" in df else [],
                    first_month=dates.min().date().isoformat() if dates is not None else None,
                    last_month=dates.max().date().isoformat() if dates is not None else None,
                    datasets=available, source=source, brand_counts=df["brand"].value_counts().to_dict(),
                    data=config.data_manifest(raw))

    def _rule_plan(self, brief: str, catalog: dict) -> dict:
        text = _fold(brief)
        brands = catalog["brands"]
        mentioned = [b for b in brands if _fold(b) in text or _fold(b.split()[0]) in text]
        requested = (self.options.get("client") or "").strip()
        if requested:  # case, accents and stray spaces are ignored ("lumiere lab" -> "Lumière Lab")
            matches = [b for b in brands if _fold(b) == _fold(requested)]
            if not matches:
                raise ValueError(f"Unknown client {requested!r}; the data covers: {', '.join(brands)}")
            client = matches[0]
        elif mentioned:
            client = mentioned[0]
        elif DEFAULT_CLIENT in brands:
            client = DEFAULT_CLIENT
        else:  # real data without a named client: the brand with the most evidence
            counts = catalog.get("brand_counts") or {}
            client = max(brands, key=lambda b: counts.get(b, 0))
            self.think(f"No client named; choosing {client}, the brand with the most records in the data.")
        m = re.search(r"(\d+)\s*(?:-\s*)?(?:month|bulan)", text)
        horizon = int(m.group(1)) if m else 12
        horizon = min(max(horizon, 3), 12)
        hits = {a: any(k in text for k in kws) for a, kws in AREA_KEYWORDS.items()}
        modules = {a: hits[a] for a in AREAS} if any(hits.values()) else {a: True for a in AREAS}
        if modules["segmentation"] or modules["pricing"]:
            modules["segmentation"] = True  # pricing research (Van Westendorp) lives in the survey agent
        if modules["competition"] or modules["consumer"]:
            modules["market"] = True        # competitive and consumer findings need market context
        # availability unknown (a hand-made catalogue) means available
        unavailable = self._drop_unavailable(modules, catalog.get("datasets") or {k: True for k in DATASETS})
        data = catalog.get("data") or config.SIMULATED
        concept = None
        if "concept" in text or "launch" in text or "new product" in text:
            m2 = re.search(r"\b(?:a|an|the)\s+([a-z\- ]{3,60}?)\s+concept", text)
            concept = (m2.group(1).strip().title() if m2 else "New product concept")
        questions = [dict(id=f"Q{i + 1}", area=a, question=QUESTION_TEMPLATES[a].format(client=client))
                     for i, a in enumerate([a for a in AREAS if modules[a]] + ["strategy"])]
        return dict(
            brief=brief, client=client, competitors=[b for b in brands if b != client],
            categories=catalog["categories"], channels=catalog["channels"], horizon_months=horizon,
            data_window=[catalog["first_month"], catalog["last_month"]], modules=modules, concept=concept,
            objectives=[o for o, on in [
                ("Size the market and identify where growth is coming from", modules["market"]),
                (f"Benchmark {client} against {len(brands) - 1} local competitors", modules["competition"]),
                ("Surface consumer pain points and unmet needs", modules["consumer"]),
                ("Define target segments, price and demand outlook",
                 modules["segmentation"] or modules["pricing"] or modules["forecast"]),
                (f"Recommend a prioritised 12-month growth plan for {client}", True)] if on],
            questions=questions, planner="rule-based", created=time.strftime("%Y-%m-%d %H:%M:%S"),
            unavailable=unavailable, data=dict(kind=data["kind"], source=data["source"]),
        )

    def _drop_unavailable(self, modules: dict, datasets: dict) -> dict:
        """Switch off the modules whose data is missing, and say why: a partial study instead of failing agents."""
        reasons, requirements = {}, module_requirements()
        for area, needs in requirements.items():
            missing = [d for d in needs if not datasets.get(d)]
            if modules.get(area) and missing:
                modules[area] = False
                reasons[area] = "needs " + " and ".join(DATASET_NAMES.get(d, d) for d in missing)
        if modules.get("pricing") and not (modules["segmentation"] or modules["forecast"]):
            modules["pricing"] = False
            reasons["pricing"] = "needs the consumer survey or the sales panel"
        if not any(modules.values()):   # nothing asked for can run: study what the data does support
            supported = [a for a, needs in requirements.items() if all(datasets.get(d) for d in needs)]
            if not supported:
                raise ValueError("No analysis can run on the data available: "
                                 + "; ".join(f"{a} {r}" for a, r in reasons.items()))
            for area in supported:
                modules[area] = True
            self.think(f"None of the analyses the brief asks for can run on this data; studying what it supports "
                       f"instead: {', '.join(supported)}.")
        for area, why in reasons.items():
            self.think(f"Leaving out the {area} module: it {why}, which this data folder does not have.")
        return reasons

    def _llm_refine(self, brief: str, catalog: dict, plan: dict) -> dict:
        task = ("Refine this market research plan. Return JSON with keys: objectives (list of 4-6 short strings), "
                "questions (list of objects with 'area' and 'question'; areas must be from "
                f"{AREAS + ['strategy']}), concept (short name or null). Keep the client as given.")
        facts = dict(brief=brief, client=plan["client"], brands=catalog["brands"], categories=catalog["categories"],
                     modules=plan["modules"], draft_questions=plan["questions"], draft_objectives=plan["objectives"])
        out = self.ask_llm(task, facts, max_tokens=900, as_json=True)
        if not isinstance(out, dict):
            self.think("The LLM's plan refinement was not usable JSON; keeping the rule-based plan.")
            return plan
        refined = dict(plan)
        objectives = [str(o) for o in out.get("objectives", []) if isinstance(o, str)]
        if 3 <= len(objectives) <= 8:
            refined["objectives"] = objectives
        qs = [q for q in out.get("questions", []) if isinstance(q, dict) and q.get("area") in AREAS + ["strategy"]
              and isinstance(q.get("question"), str)]
        covered = {q["area"] for q in qs}
        needed = {q["area"] for q in plan["questions"]}
        if qs and needed <= covered:
            refined["questions"] = [dict(id=f"Q{i + 1}", area=q["area"], question=q["question"].strip())
                                    for i, q in enumerate(qs) if plan["modules"].get(q["area"], True)]
        else:
            self.think(f"The LLM's questions leave out {', '.join(sorted(needed - covered)) or 'every area'}; "
                       f"keeping the rule-based questions.")
        if isinstance(out.get("concept"), str) and out["concept"].strip():
            refined["concept"] = out["concept"].strip()
        refined["planner"] = "rule-based + LLM refinement"
        return refined

    # ------------------------------------------------------------------ human approval of the plan
    def review_plan(self) -> Decision:
        """Put the plan to the approval gate and apply the reviewer's edits (modules left out)."""
        return self.use("seek_plan_approval")

    def _seek_plan_approval(self) -> Decision:
        plan = self.bb.require("plan")
        proposal = dict(client=plan["client"], modules=[a for a in AREAS if plan["modules"][a]],
                        questions=plan["questions"], objectives=plan["objectives"],
                        horizon_months=plan["horizon_months"], concept=plan.get("concept"))
        decision = request_approval(self.ctx, "plan", proposal, self.name)
        if not decision.approved:
            self.think(f"The reviewer rejected the plan ({decision.comment or 'no reason given'}); stopping the study.")
            return decision
        drop = [m for m in decision.drop if m in AREAS and plan["modules"].get(m)]
        if "segmentation" in drop and plan["modules"].get("pricing") and "pricing" not in drop:
            drop.append("pricing")  # the concept price research runs inside the segmentation agent
        if drop:
            for m in drop:
                plan["modules"][m] = False
            kept = [q for q in plan["questions"] if q["area"] not in drop]
            plan["questions"] = [dict(q, id=f"Q{i + 1}") for i, q in enumerate(kept)]
            active = [a for a in AREAS if plan["modules"][a]]
            if not active:
                self.think("The reviewer left out every analysis module, so there is nothing to study; stopping.")
                return Decision(False, decision.reviewer, "every analysis module was left out")
            self.put("plan", plan, "Research plan after the reviewer's edits")
            self.think(f"The reviewer left out {', '.join(drop)}; the plan now covers {', '.join(active)} "
                       f"with {len(plan['questions'])} questions.")
        return decision

    # ------------------------------------------------------------------ dispatching
    def build_workflow(self) -> Workflow:
        from . import (CompetitiveIntelligenceAgent, ConsumerInsightAgent, DataCollectionAgent, DataQualityAgent,
                       DemandForecastingAgent, MarketTrendAnalystAgent, QualityAssuranceAgent, ReportWriterAgent,
                       SegmentationAgent, StrategyAgent)
        modules = self.bb.require("plan")["modules"]
        limits = dict(retries=int(self.options.get("retries", 1)),
                      timeout=float(self.options.get("agent_timeout") or DEFAULT_AGENT_TIMEOUT))
        tasks = [Task("collect", DataCollectionAgent, **limits), Task("quality", DataQualityAgent, ("collect",), **limits)]
        analysis = []
        for key, agent, flag in [("market", MarketTrendAnalystAgent, modules["market"]),
                                 ("competition", CompetitiveIntelligenceAgent, modules["competition"]),
                                 ("consumer", ConsumerInsightAgent, modules["consumer"]),
                                 ("segmentation", SegmentationAgent, modules["segmentation"]),
                                 ("forecast", DemandForecastingAgent, modules["forecast"] or modules["pricing"])]:
            if flag:
                tasks.append(Task(key, agent, ("quality",), critical=False, **limits))
                analysis.append(key)
        tasks += [Task("strategy", StrategyAgent, tuple(analysis) or ("quality",), **limits),
                  Task("report", ReportWriterAgent, ("strategy",), **limits),
                  Task("qa", QualityAssuranceAgent, ("report",), **limits)]
        wf = Workflow(tasks)
        self.emit("thought", f"Dispatching {len(tasks)} agents in {len(wf.layers)} stages; "
                             f"{len(analysis)} analysis agents will run in parallel.",
                  layers=wf.layers)
        return wf

    # ------------------------------------------------------------------ supervision: adaptive re-dispatch
    def follow_up_plan(self, qa: dict, results: dict[str, AgentResult], tasks: set[str]) -> dict[str, dict]:
        """Which analysis agents to send back, and why: {task id: {questions, sections, failed}}.

        Reads the Critic's verdict: research questions no finding answers, and analysis sections missing from
        the report. Each is traced to the task that should have answered it.
        """
        plan = self.bb.require("plan")
        questions = {q["id"]: q for q in plan["questions"]}
        checks = qa.get("checks", {})
        todo: dict[str, dict] = {}
        for qid in checks.get("coverage", {}).get("unanswered", []):
            q = questions.get(qid)
            for tid in AREA_TASKS.get(q["area"] if q else "", ()):
                if tid in tasks:
                    todo.setdefault(tid, dict(questions=[], sections=[]))["questions"].append(q)
        for section in checks.get("structure", {}).get("missing", []):
            tid = SECTION_TASKS.get(section)
            if tid in tasks:
                todo.setdefault(tid, dict(questions=[], sections=[]))["sections"].append(section)
        for tid, item in todo.items():
            item["failed"] = tid not in results or results[tid].status != "completed"
        return todo

    def supervise(self, results: dict[str, AgentResult], workflow: Workflow) -> dict[str, AgentResult]:
        """Send analysis agents back for the research questions the report leaves open (once per agent per run).

        An agent that failed is re-dispatched in full; one that completed but did not answer a question gets a
        targeted request and answers it from its findings, or reports the question as open. If anything changed,
        the Strategy agent, the Report Writer and the Critic are run again on the new evidence.
        """
        qa = self.bb.get("qa.result") or {}
        done = set(self.bb.get("director.followed_up", []))
        todo = {tid: v for tid, v in self.follow_up_plan(qa, results, set(workflow.tasks)).items() if tid not in done}
        if not todo:
            return results
        adaptations = list(self.bb.get("director.adaptations", []))
        changed = False
        for tid, item in todo.items():
            task = workflow.tasks[tid]
            qids = [q["id"] for q in item["questions"]]
            gaps = qids + [f"the {s} section" for s in item["sections"]]
            reason = "it failed" if item["failed"] else f"no finding answers {', '.join(qids)}"
            self.think(f"The report leaves {', '.join(gaps)} open ({reason}); sending the {task.agent.name} back.")
            for q in item["questions"]:
                self.tell(task.agent.name, f"Answer {q['id']}: {q['question']}", question=q)
            if not item["questions"]:
                self.tell(task.agent.name, f"Re-run your analysis: the report has no {', '.join(item['sections'])} section")
            agent = task.agent(self.ctx)
            agent.time_limit = task.timeout
            result = agent.run() if item["failed"] else agent.run_follow_up()
            results[f"{tid}_followup"] = result
            adaptations.append(dict(task=tid, agent=task.agent.name, reason=reason, questions=qids,
                                    sections=item["sections"], action="re-dispatched" if item["failed"] else "targeted request",
                                    status=result.status, outcome=result.summary if result.status == "completed"
                                    else f"failed again: {result.error}"))
            changed |= result.status == "completed"
        self.put("director.followed_up", sorted(done | set(todo)), "Analysis tasks already sent back once")
        self.put("director.adaptations", adaptations, "Follow-up requests the Director sent and their outcomes")
        if changed:
            self.think("Redoing the strategy, the report and the QA check with the new evidence.")
            for tid in ("strategy", "report", "qa"):
                if tid in workflow.tasks:
                    agent = workflow.tasks[tid].agent(self.ctx)
                    agent.time_limit = workflow.tasks[tid].timeout
                    results[f"{tid}_followup"] = agent.run()
                    if results[f"{tid}_followup"].status != "completed":
                        break
        else:
            self.warn("Follow-up requests did not close the gaps; they are disclosed in the report.")
        return results

    # ------------------------------------------------------------------ supervision: QA gate
    def quality_loop(self, results: dict[str, AgentResult], max_revisions: int = 2) -> dict[str, AgentResult]:
        from . import QualityAssuranceAgent, ReportWriterAgent
        for attempt in range(1, max_revisions + 1):
            qa = self.bb.get("qa.result") or {}
            if not qa or qa.get("passed"):
                if qa:
                    self.think(f"QA gate passed with score {qa.get('score')}/100 - report approved for release.")
                return results
            issues = qa.get("issues", [])
            self.think(f"QA gate failed (score {qa.get('score')}/100, {len(issues)} issues). "
                       f"Requesting revision {attempt}/{max_revisions} from the Report Writer.")
            self.tell(ReportWriterAgent.name, "Revise the report to resolve the QA issues", issues=issues[:20])
            self.ctx.options["revision"] = attempt
            results[f"report_rev{attempt}"] = ReportWriterAgent(self.ctx).run()
            results[f"qa_rev{attempt}"] = QualityAssuranceAgent(self.ctx).run()
        qa = self.bb.get("qa.result") or {}
        if not qa.get("passed"):
            self.warn(f"Report released with QA score {qa.get('score')}/100 after {max_revisions} revisions; "
                      "open issues are listed in the QA appendix.")
        return results
