"""Research Director: the orchestrating agent.

1. Plans: turns the free-text business brief into a structured research plan (client, scope,
   objectives, research questions, modules to run) - rule-based parsing, optionally refined by
   the LLM, always validated against the data actually available.
2. Dispatches: builds the agent workflow (DAG) for the modules the plan needs.
3. Supervises: enforces the QA gate - if the Critic rejects the report, it sends the report back
   to the Report Writer for revision (bounded number of loops).
"""
from __future__ import annotations

import re
import time
import unicodedata

import pandas as pd

from ..config import DATA_RAW, DATASETS, DEFAULT_CLIENT
from ..core.agent import AgentResult, BaseAgent
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
        sales = pd.read_csv(DATA_RAW / DATASETS["sales"]["file"], usecols=["month", "brand", "category", "channel"])
        available = {k: (DATA_RAW / v["file"]).exists() for k, v in DATASETS.items()}
        return dict(brands=sorted(sales["brand"].unique()), categories=sorted(sales["category"].unique()),
                    channels=sorted(sales["channel"].str.strip().unique()), first_month=sales["month"].min(),
                    last_month=sales["month"].max(), datasets=available)

    def _rule_plan(self, brief: str, catalog: dict) -> dict:
        text = _fold(brief)
        brands = catalog["brands"]
        mentioned = [b for b in brands if _fold(b) in text or _fold(b.split()[0]) in text]
        requested = (self.options.get("client") or "").strip()
        if requested:  # case, accents and stray spaces are ignored ("lumiere lab" -> "Lumière Lab")
            matches = [b for b in brands if _fold(b) == _fold(requested)]
            if not matches:
                raise ValueError(f"Unknown client {requested!r}; the sales data covers: {', '.join(brands)}")
            client = matches[0]
        else:
            client = mentioned[0] if mentioned else (DEFAULT_CLIENT if DEFAULT_CLIENT in brands else brands[0])
        m = re.search(r"(\d+)\s*(?:-\s*)?(?:month|bulan)", text)
        horizon = int(m.group(1)) if m else 12
        horizon = min(max(horizon, 3), 12)
        hits = {a: any(k in text for k in kws) for a, kws in AREA_KEYWORDS.items()}
        modules = {a: hits[a] for a in AREAS} if any(hits.values()) else {a: True for a in AREAS}
        if modules["segmentation"] or modules["pricing"]:
            modules["segmentation"] = True  # pricing research (Van Westendorp) lives in the survey agent
        if modules["competition"] or modules["consumer"]:
            modules["market"] = True        # competitive and consumer findings need market context
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
            objectives=["Size the market and identify where growth is coming from",
                        f"Benchmark {client} against {len(brands) - 1} local competitors",
                        "Surface consumer pain points and unmet needs",
                        "Define target segments, price and demand outlook",
                        f"Recommend a prioritised 12-month growth plan for {client}"],
            questions=questions, planner="rule-based", created=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

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

    # ------------------------------------------------------------------ dispatching
    def build_workflow(self) -> Workflow:
        from . import (CompetitiveIntelligenceAgent, ConsumerInsightAgent, DataCollectionAgent, DataQualityAgent,
                       DemandForecastingAgent, MarketTrendAnalystAgent, QualityAssuranceAgent, ReportWriterAgent,
                       SegmentationAgent, StrategyAgent)
        modules = self.bb.require("plan")["modules"]
        tasks = [Task("collect", DataCollectionAgent), Task("quality", DataQualityAgent, ("collect",))]
        analysis = []
        for key, agent, flag in [("market", MarketTrendAnalystAgent, modules["market"]),
                                 ("competition", CompetitiveIntelligenceAgent, modules["competition"]),
                                 ("consumer", ConsumerInsightAgent, modules["consumer"]),
                                 ("segmentation", SegmentationAgent, modules["segmentation"]),
                                 ("forecast", DemandForecastingAgent, modules["forecast"] or modules["pricing"])]:
            if flag:
                tasks.append(Task(key, agent, ("quality",), critical=False))
                analysis.append(key)
        tasks += [Task("strategy", StrategyAgent, tuple(analysis) or ("quality",)),
                  Task("report", ReportWriterAgent, ("strategy",)),
                  Task("qa", QualityAssuranceAgent, ("report",))]
        wf = Workflow(tasks)
        self.emit("thought", f"Dispatching {len(tasks)} agents in {len(wf.layers)} stages; "
                             f"{len(analysis)} analysis agents will run in parallel.",
                  layers=wf.layers)
        return wf

    # ------------------------------------------------------------------ supervision
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
