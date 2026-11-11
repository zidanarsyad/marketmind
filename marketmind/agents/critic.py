"""Critic Agent (QA): fact-checks the report before release.

Checks: required structure, coverage of every research question, numeric grounding (every number in the
prose must match a number produced by the analysis tools, within the precision it is written at),
validity of finding citations, evidence behind every recommendation, and mandatory disclosures.
A failing report goes back to the Report Writer with block-level issues (reflection loop).
"""
from __future__ import annotations

import re

from ..core.agent import OPEN_QUESTION, BaseAgent
from ..core.grounding import NUM  # noqa: F401  (kept importable from here)
from ..core.grounding import evidence_numbers, grounded
from ..core.grounding import expand as _expand  # noqa: F401  (kept importable from here)
from ..core.grounding import numbers_in as _numbers

CITE = re.compile(r"\[([A-Z]{2,4}-\d{2})\]")
CODE_SPAN = re.compile(r"`[^`\n]*`")   # identifiers (model names, IDs, files), not claims: not checked
LLM_BLOCK = re.compile(r"<!-- llm:(?P<key>[\w-]+) -->(?P<body>.*?)<!-- /llm -->", re.S)
REQUIRED = ["Executive Summary", "Research Objectives", "Methodology", "SWOT", "Recommendations", "Risks and Limitations"]
WEIGHTS = dict(structure=15, coverage=20, grounding=35, citations=10, recommendations=15, disclosure=5)


class QualityAssuranceAgent(BaseAgent):
    name = "Critic Agent (QA)"
    role = "Reviewer. Fact-checks the report against the evidence and enforces quality standards before release."
    goal = "Block any report with unsupported numbers, unanswered questions, invalid citations or unevidenced recommendations."

    def register_tools(self):
        self.tool("collect_evidence_numbers", self._allowed_numbers, "gather every number produced by the analysis tools")
        self.tool("check_numeric_grounding", self._grounding, "verify each number in the prose against the evidence")
        self.tool("check_structure_and_coverage", self._structure, "required sections and research-question coverage")
        self.tool("check_citations_and_evidence", self._citations, "validate finding citations and recommendation evidence")

    def execute(self) -> str:
        md = self.bb.require("report.markdown")
        allowed = self.use("collect_evidence_numbers")
        grounding = self.use("check_numeric_grounding", md, allowed)
        structure, coverage, disclosure = self.use("check_structure_and_coverage", md)
        citations, recs = self.use("check_citations_and_evidence", md)
        checks = dict(structure=structure, coverage=coverage, grounding=grounding, citations=citations,
                      recommendations=recs, disclosure=disclosure)
        score = round(sum(WEIGHTS[k] * checks[k]["score"] for k in WEIGHTS), 1)
        issues = [i for c in checks.values() for i in c.get("issues", [])]
        critical = [i for i in issues if i["severity"] == "critical"]
        passed = score >= 85 and not critical
        result = dict(score=score, passed=passed, revision=int(self.options.get("revision", 0)),
                      checks={k: {kk: vv for kk, vv in v.items() if kk != "issues"} for k, v in checks.items()},
                      issues=issues, numbers_checked=grounding["checked"], numbers_grounded=grounding["grounded"])
        self.put("qa.result", result, "Critic verdict")
        history = list(self.bb.get("qa.history", []))
        history.append(dict(revision=result["revision"], score=score, passed=passed, issues=len(issues)))
        self.put("qa.history", history, "QA verdicts across revisions")
        verdict = "PASS" if passed else "FAIL"
        self.think(f"QA {verdict}: score {score}/100, {grounding['grounded']}/{grounding['checked']} numbers grounded, "
                   f"{len(issues)} issue(s) ({len(critical)} critical).")
        if not passed:
            self.tell("Report Writer Agent", f"QA failed with score {score}; {len(issues)} issues to fix", issues=issues)
        return f"QA {verdict} - score {score}/100"

    # ------------------------------------------------------------------ evidence
    def _allowed_numbers(self) -> list[float]:
        evidence = []
        for f in self.bb.findings():
            evidence += [f.statement, f.metrics]
        for key in ("strategy.recommendations", "strategy.kpis", "strategy.exec_summary", "plan", "strategy.swot",
                    "consumer.model_card", "segmentation.model_card", "forecast.model_card"):
            evidence.append(self.bb.get(key))
        opps = self.bb.get("strategy.opportunities")
        if opps is not None and len(opps):
            evidence.append(opps.to_dict(orient="records"))
        return evidence_numbers(*evidence)   # core/grounding.py, shared with the on-demand agents

    def _grounding(self, md: str, allowed: list[float]) -> dict:
        issues, checked, ok = [], 0, 0
        llm_spans = [(m.start(), m.end(), m.group("key"), m.group("body")) for m in LLM_BLOCK.finditer(md)]
        blocks = [(key, body) for _, _, key, body in llm_spans]
        stripped = LLM_BLOCK.sub("", md)
        prose = "\n".join(line for line in stripped.splitlines()
                          if line.strip() and not line.lstrip().startswith(("|", "#", ">", "*Prepared")))
        blocks.append(("deterministic_text", prose))
        per_block = {}
        for key, text in blocks:
            text = CODE_SPAN.sub(" ", CITE.sub("", text)).replace(self.ctx.run_id, "")
            bad = []
            for x, dec, raw in _numbers(text):
                checked += 1
                if grounded(x, dec, allowed):
                    ok += 1
                else:
                    pos = text.find(raw)
                    bad.append(dict(value=raw, context=text[max(0, pos - 60):pos + 40].replace("\n", " ")))
            per_block[key] = dict(ungrounded=len(bad))
            if bad:
                llm = key != "deterministic_text"
                issues.append(dict(check="grounding", severity="critical" if llm else "major", block=key if llm else None,
                                   message=f"{len(bad)} number(s) in '{key}' not found in the evidence: "
                                           + "; ".join(f"{b['value']} ('...{b['context']}...')" for b in bad[:4])))
        rate = ok / checked if checked else 1.0
        return dict(score=min(1.0, rate / 0.98), rate=round(rate, 4), checked=checked, grounded=ok,
                    blocks=per_block, issues=issues)

    def _structure(self, md: str) -> tuple[dict, dict, dict]:
        heads = [h.lower() for h in re.findall(r"^## (.+)$", md, re.M)]
        missing = [r for r in REQUIRED if not any(r.lower() in h for h in heads)]
        plan = self.bb.require("plan")
        for area, title in (("market", "Market Overview"), ("competition", "Competitive Landscape"),
                            ("consumer", "Consumer Insights"), ("segmentation", "Segments and Personas"),
                            ("forecast", "Demand Forecast")):
            if plan["modules"].get(area) and not any(title.lower() in h for h in heads):
                missing.append(title)
        structure = dict(score=1 - len(missing) / (len(REQUIRED) + 5), missing=missing,
                         issues=[dict(check="structure", severity="critical" if m in ("Executive Summary", "Recommendations") else "major",
                                      block=None, message=f"Missing section: {m}") for m in missing])
        found = [f for f in self.bb.findings() if "methodology" not in f.tags]
        areas = {f.area for f in found if OPEN_QUESTION not in f.tags}
        open_areas = {f.area for f in found if OPEN_QUESTION in f.tags}
        recs = self.bb.get("strategy.recommendations", [])

        def covered(q: dict, pool: set) -> bool:
            return (q["area"] in pool or (q["area"] == "segmentation" and "pricing" in pool)
                    or (q["area"] == "strategy" and bool(recs)))

        answered = [q for q in plan["questions"] if covered(q, areas)]
        still_open = [q for q in plan["questions"] if q not in answered and covered(q, open_areas)]
        unanswered = [q for q in plan["questions"] if q not in answered and q not in still_open]
        n_questions = max(len(plan["questions"]), 1)
        # a question an agent looked into and reported as open is addressed, not answered: half credit, no issue
        coverage = dict(score=(len(answered) + 0.5 * len(still_open)) / n_questions, questions=len(plan["questions"]),
                        unanswered=[q["id"] for q in unanswered], open=[q["id"] for q in still_open],
                        issues=[dict(check="coverage", severity="major", block=None,
                                     message=f"{q['id']} not answered by any finding: {q['question']}") for q in unanswered])
        low = md.lower()
        disclosed = ("simulated" in low or "real marketplace data" in low) and ("limitations" in low)
        disclosure = dict(score=1.0 if disclosed else 0.0, issues=[] if disclosed else [
            dict(check="disclosure", severity="major", block=None, message="Data provenance / limitations disclosure missing")])
        return structure, coverage, disclosure

    def _citations(self, md: str) -> tuple[dict, dict]:
        known = {f.id for f in self.bb.findings()}
        issues = []
        cited = CITE.findall(md)
        bad = sorted(set(c for c in cited if c not in known))
        for m in LLM_BLOCK.finditer(md):
            inv = sorted(set(c for c in CITE.findall(m.group("body")) if c not in known))
            if inv:
                issues.append(dict(check="citations", severity="critical", block=m.group("key"),
                                   message=f"Invented citation(s) {inv} in '{m.group('key')}'"))
        if bad and not issues:
            issues.append(dict(check="citations", severity="major", block=None, message=f"Unknown citations: {bad}"))
        valid = 1 - len([c for c in cited if c not in known]) / max(len(cited), 1)
        citations = dict(score=valid, cited=len(cited), distinct=len(set(cited)), unknown=bad, issues=issues)
        recs = self.bb.get("strategy.recommendations", [])
        unevidenced = [r["id"] for r in recs if not [e for e in r["evidence"] if e in known]]
        rec_issues = [dict(check="recommendations", severity="major", block=None,
                           message=f"Recommendation {r} has no valid evidence") for r in unevidenced]
        # recommendations a human reviewer dropped count as proposed: the agents did their part. A study that the
        # data limits to one or two analysis modules needs at least one recommendation, a fuller study three
        proposed = len(recs) + len(self.bb.get("strategy.rejected_recommendations", []))
        modules = (self.bb.get("plan") or {}).get("modules", {})
        active = sum(bool(modules.get(a)) for a in ("market", "competition", "consumer", "segmentation", "forecast"))
        minimum = 1 if 0 < active < 3 else 3
        if proposed < minimum:
            rec_issues.append(dict(check="recommendations", severity="critical", block=None,
                                   message=f"Only {len(recs)} recommendations (minimum {minimum})"))
        rec_score = (1 - len(unevidenced) / max(len(recs), 1)) * (1.0 if proposed >= minimum else 0.5)
        return citations, dict(score=rec_score, count=len(recs), unevidenced=unevidenced, issues=rec_issues)
