"""Report Writer Agent: turns the team's findings, tables and recommendations into a structured client
report (Markdown + self-contained interactive HTML).

Deterministic text is assembled straight from findings, so it is grounded by construction. When an LLM
is configured it adds an executive summary and short "so what" commentary per section; those blocks are
marked so the Critic can verify them, and on a revision request any block the Critic rejects is replaced
by its deterministic version.
"""
from __future__ import annotations

import re
import time

import pandas as pd

from ..core.agent import BaseAgent
from ..reporting.html_report import render_html
from .common import idr, pct

AREA_SECTIONS = [
    ("market", "Market Overview", ["market"]),
    ("competition", "Competitive Landscape", ["competition"]),
    ("consumer", "Consumer Insights", ["consumer"]),
    ("segmentation", "Segments and Personas", ["segmentation"]),
    ("pricing", "Pricing", ["pricing"]),
    ("forecast", "Demand Forecast", ["forecast"]),
]
LLM_OPEN = "<!-- llm:{key} -->"
LLM_CLOSE = "<!-- /llm -->"


def md_table(df: pd.DataFrame, formats: dict | None = None, max_rows: int = 30) -> str:
    if df is None or df.empty:
        return "_No data._"
    formats = formats or {}
    d = df.head(max_rows)
    head = "| " + " | ".join(str(c) for c in d.columns) + " |"
    sep = "| " + " | ".join("---" for _ in d.columns) + " |"
    rows = []
    for _, r in d.iterrows():
        cells = []
        for col in d.columns:
            v = r[col]
            f = formats.get(col)
            cells.append(f(v) if f and pd.notna(v) else ("" if pd.isna(v) else str(v)))
        rows.append("| " + " | ".join(c.replace("|", "/") for c in cells) + " |")
    return "\n".join([head, sep] + rows)


def fx(x):
    return f"{x:.2f}x"


def p1(x):
    return pct(x, 1, sign=False)


def g1(x):
    return pct(x, 1)


class ReportWriterAgent(BaseAgent):
    name = "Report Writer Agent"
    role = "Research writer. Turns the team's findings into a clear, structured, decision-ready client report."
    goal = "Deliver a report in which every claim is traceable to evidence, in Markdown and interactive HTML."

    def register_tools(self):
        self.tool("compose_report", self._compose, "assemble the report sections from findings, tables and recommendations")
        self.tool("write_section_commentary", self._commentary, "LLM 'so what' commentary per section (optional)")
        self.tool("render_html_report", self._render, "render the interactive HTML report with embedded charts")

    def execute(self) -> str:
        self.plan = self.bb.require("plan")
        self.client = self.plan["client"]
        revision = int(self.options.get("revision", 0))
        rejected = set()
        if revision:
            for msg in self.bb.inbox(self.name):
                for issue in msg.data.get("issues", []):
                    if issue.get("block"):
                        rejected.add(issue["block"])
            self.think(f"Revision {revision}: replacing {len(rejected)} rejected block(s) with grounded text: {sorted(rejected)}")
            self.ctx.options["rejected_blocks"] = sorted(set(self.options.get("rejected_blocks", [])) | rejected)
        commentary = self.bb.get("report.commentary")
        if commentary is None:
            commentary = self.use("write_section_commentary")
            self.put("report.commentary", commentary, "LLM section commentary (may be empty)")
        sections = self.use("compose_report", commentary, set(self.options.get("rejected_blocks", [])))
        md = "\n\n".join(s["markdown"] for s in sections)
        self.put("report.sections", [{k: v for k, v in s.items() if k != "markdown"} for s in sections], "Report structure")
        self.put("report.markdown", md, "Final report (Markdown)")
        html = self.use("render_html_report", sections)
        self.put("report.html", html, "Final report (interactive HTML)")
        words = len(re.findall(r"\w+", md))
        return f"Report with {len(sections)} sections, ~{words:,} words (revision {revision})"

    # ------------------------------------------------------------------ LLM commentary
    def _commentary(self) -> dict:
        out = {}
        if not (self.llm.available and self.options.get("use_llm", True)):
            return out
        for key, title, areas in AREA_SECTIONS:
            fs = [f.to_dict() for f in self.bb.findings() if f.area in areas]
            if not fs:
                continue
            text = self.ask_llm(
                f"Write 2-3 sentences of 'so what' commentary for the '{title}' section of {self.client}'s report: what these "
                f"findings mean for {self.client} and what it should do. Plain prose, no bullet points, no headings, cite "
                f"finding IDs in brackets.", fs, max_tokens=400)
            if text:
                out[key] = text.strip()
        return out

    # ------------------------------------------------------------------ composition
    @staticmethod
    def _training_mix(td: dict) -> str:
        if td.get("mode") == "study+real":
            return (f" Training data: {td['study_reviews']:,} of this study's reviews plus {td['real_reviews']:,} real "
                    f"Shopee/Tokopedia beauty reviews ({td['real_source']}).")
        if td.get("mode") == "real":
            return (f" Training data: {td['real_reviews']:,} real Shopee/Tokopedia beauty reviews only "
                    f"({td['real_source']}); the study's reviews were used for testing only.")
        return ""

    def _compose(self, commentary: dict, rejected: set) -> list[dict]:
        bb, c = self.bb, self.client
        F = {f.id: f for f in bb.findings()}
        kpis = bb.get("strategy.kpis", {})
        recs = bb.get("strategy.recommendations", [])
        swot = bb.get("strategy.swot", {})
        opps = bb.get("strategy.opportunities")
        mt, ct = bb.get("market.tables", {}), bb.get("competition.tables", {})
        cs, sg, fc = bb.get("consumer.tables", {}), bb.get("segmentation.tables", {}), bb.get("forecast.tables", {})
        sections = []

        def bullets(area):
            return "\n".join(f"- **{f.title}.** {f.statement} `[{f.id}]`"
                             for f in sorted(bb.findings(area=area), key=lambda f: f.id))

        def llm_block(key):
            text = commentary.get(key)
            if not text or key in rejected:
                return ""
            return f"\n\n{LLM_OPEN.format(key=key)}\n> **Analyst commentary.** {text}\n{LLM_CLOSE}"

        def add(key, title, body, charts=()):
            sections.append(dict(key=key, title=title, charts=list(charts), markdown=f"## {title}\n\n{body}".rstrip()))

        # -- title + executive summary
        date = time.strftime("%d %B %Y")
        title = (f"# {c} - Market Research Report\n### Indonesian local facial-skincare market\n\n"
                 f"*Prepared by the MarketMind multi-agent system on {date} - run `{self.ctx.run_id}`*\n\n"
                 "> **Note:** all data in this report is simulated for demonstration; brands and products are fictional.")
        sections.append(dict(key="title", title="Title", charts=[], markdown=title))
        llm_sum = bb.get("strategy.exec_summary_llm")
        summary = (f"{LLM_OPEN.format(key='exec_summary')}\n{llm_sum}\n{LLM_CLOSE}"
                   if llm_sum and "exec_summary" not in rejected else bb.get("strategy.exec_summary", ""))
        kpi_rows = [("Market size", f"{idr((kpis.get('market_size_idr_bn') or 0) * 1e9)} ({kpis.get('market_year')})"),
                    ("Market CAGR", p1(kpis["market_cagr"]) if kpis.get("market_cagr") is not None else "n/a"),
                    (f"{c} panel share", f"{p1(kpis['client_share'])} (#{kpis.get('client_rank')})" if kpis.get("client_share") else "n/a"),
                    (f"{c} growth (last 12m)", g1(kpis["client_growth"]) if kpis.get("client_growth") is not None else "n/a"),
                    ("Top competitive threat", kpis.get("top_threat") or "n/a"),
                    ("Top consumer pain point", kpis.get("top_pain_point") or "n/a"),
                    ("Concept target segment", kpis.get("target_segment") or "n/a"),
                    ("Recommended concept price", idr(kpis["recommended_price_idr"]) if kpis.get("recommended_price_idr") else "n/a"),
                    ("Forecast market growth (next 12m)", g1(kpis["forecast_market_growth"]) if kpis.get("forecast_market_growth") is not None else "n/a"),
                    (f"{c} price elasticity", f"{kpis['elasticity']:.2f}" if kpis.get("elasticity") is not None else "n/a")]
        kpi_md = md_table(pd.DataFrame(kpi_rows, columns=["Headline KPI", "Value"]))
        add("executive_summary", "1. Executive Summary", f"{summary}\n\n{kpi_md}", ["kpi_strip"])

        # -- objectives and questions
        area_ids = {}
        for f in bb.findings():
            area_ids.setdefault(f.area, []).append(f)
        qrows = []
        for q in self.plan["questions"]:
            if q["area"] == "strategy":
                ans = "; ".join(r["title"] for r in recs[:3]) or "See recommendations."
                ev = ", ".join(sorted({e for r in recs[:3] for e in r["evidence"]}))
            else:
                areas = [q["area"]] + (["pricing"] if q["area"] == "segmentation" else [])
                fs = sorted([f for a in areas for f in area_ids.get(a, []) if "methodology" not in f.tags],
                            key=lambda f: -f.priority)[:2]
                ans = " ".join(f.statement for f in fs) or "Not covered in this run."
                ev = ", ".join(f.id for f in fs)
            qrows.append(dict(**{"#": q["id"], "Research question": q["question"], "Answer": ans, "Evidence": ev}))
        obj = "\n".join(f"- {o}" for o in self.plan["objectives"])
        add("objectives", "2. Research Objectives and Answers",
            f"**Brief.** {self.plan['brief']}\n\n**Objectives**\n\n{obj}\n\n{md_table(pd.DataFrame(qrows))}")

        # -- methodology
        cat = bb.get("data.catalog")
        dq = bb.get("dq.scorecard")
        cards = []
        mc = bb.get("consumer.model_card")
        if mc:
            cards.append(f"- **Consumer Insight Agent (deep learning):** PyTorch BiGRU with attention trained on "
                         f"{mc['n_train']:,} reviews, compared with TF-IDF + logistic regression and a soft-vote ensemble; "
                         f"selected: `{mc['selected']}` (test macro-F1 {mc['test_metrics'][mc['selected']]['macro_f1']:.3f}). "
                         f"Applied to review clauses (aspect-based sentiment) and to unlabeled social posts."
                         + self._training_mix(mc.get("training_data") or {})
                         + (f" {mc['real_text_note']}" if mc.get("real_text_note") else ""))
        smc = bb.get("segmentation.model_card")
        if smc:
            cards.append(f"- **Consumer Segmentation Agent (machine learning):** {smc['algorithm']}; k={smc['k']} chosen by "
                         f"silhouette ({smc['silhouette']:.3f}); Van Westendorp price sensitivity meter.")
        fmc = bb.get("forecast.model_card")
        if fmc:
            cards.append(f"- **Demand Forecasting Agent (machine learning):** candidates {', '.join(fmc['candidates'])}; "
                         f"winner `{fmc['model']}` by 3-fold rolling-origin backtest; fixed-effects log-log price elasticities.")
        llm_note = (f"LLM support: `{self.llm.describe()}` - used for planning and narrative only; every number comes "
                    f"from deterministic tools and is verified by the Critic.") if self.llm.available else \
                   "LLM support: none (offline mode) - all reasoning and narrative are deterministic."
        meth = (self._team_sentence() + "\n\n"
                + (md_table(cat[["dataset", "rows", "coverage", "source"]]) if cat is not None else "") + "\n\n"
                + (f"**Data quality.** {F['DAT-02'].statement} `[DAT-02]`\n\n" if "DAT-02" in F else "")
                + (md_table(dq[["dataset", "rows_in", "rows_out", "quality_score", "actions"]]) if dq is not None else "")
                + "\n\n**Models**\n\n" + "\n".join(cards) + f"\n\n{llm_note}" + self._oversight())
        add("methodology", "3. Methodology and Data", meth)

        # -- analysis sections
        n = 4
        if mt:
            body = bullets("market") + llm_block("market")
            if "category_growth" in mt:
                body += "\n\n" + md_table(mt["category_growth"][["category", "revenue_l12", "growth", "share_l12"]],
                                          dict(revenue_l12=idr, growth=g1, share_l12=p1))
            add("market", f"{n}. Market Overview", body,
                ["market_size", "category_growth", "channel_mix", "region_growth", "topic_trends", "seasonality"])
            n += 1
        if ct:
            body = bullets("competition") + llm_block("competition")
            body += "\n\n" + md_table(ct["brand_share"][["brand", "revenue_l12", "share_l12", "share_change_pp", "growth"]],
                                      dict(revenue_l12=idr, share_l12=p1, share_change_pp=lambda x: f"{x * 100:+.1f} pp", growth=g1))
            if "threats" in ct:
                body += "\n\n**Threat index**\n\n" + md_table(ct["threats"][["rank", "brand", "threat_index", "growth", "share_l12", "category_overlap"]],
                                                            dict(threat_index=lambda x: f"{x:.2f}", growth=g1, share_l12=p1, category_overlap=lambda x: f"{x:.2f}"))
            if "white_space" in ct:
                body += "\n\n**White-space scan**\n\n" + md_table(ct["white_space"][["space", "supply_skus", "consumer_need_share", "trend_momentum", "opportunity_score"]],
                                                                 dict(consumer_need_share=p1, trend_momentum=g1))
            add("competition", f"{n}. Competitive Landscape", body,
                ["brand_share", "share_trend", "channel_index", "positioning", "threats"])
            n += 1
        if cs:
            body = bullets("consumer") + llm_block("consumer")
            if "aspect_summary" in cs:
                a = cs["aspect_summary"]
                a = a[a["brand"] == c].sort_values("net_sentiment")[["aspect_label", "mentions", "net_sentiment", "negative_per_100_reviews"]]
                body += f"\n\n**{c} aspect sentiment (last 12 months)**\n\n" + md_table(a, dict(net_sentiment=lambda x: f"{x:+.2f}", negative_per_100_reviews=lambda x: f"{x:.1f}"))
            if "anomalies" in cs and len(cs["anomalies"]):
                an = cs["anomalies"].head(6).copy()
                an["period"] = an["start"].astype(str).str[:7] + " to " + an["end"].astype(str).str[:7]
                body += "\n\n**Detected complaint spikes**\n\n" + md_table(an[["brand", "aspect_label", "period", "peak_rate", "baseline_rate", "complaints"]])
            if "example_reviews" in cs and len(cs["example_reviews"]):
                ex = cs["example_reviews"]
                quotes = "\n".join(f"> \"{t}\" - *{b}, {a}*" for t, b, a in zip(ex["text"].head(6), ex["brand"], ex["aspect"], strict=False))
                body += f"\n\n**Voice of the customer**\n\n{quotes}"
            add("consumer", f"{n}. Consumer Insights", body,
                ["sentiment_by_brand", "aspect_heatmap", "client_aspect_trend", "social_sentiment", "model_quality"])
            n += 1
        if sg:
            body = bullets("segmentation") + llm_block("segmentation")
            prof = sg["profiles"][["name", "share", "description", "drivers", "concept_t2b"]]
            body += "\n\n" + md_table(prof, dict(share=p1, concept_t2b=p1))
            add("segmentation", f"{n}. Segments and Personas", body, ["segment_map", "segment_importance", "concept"])
            n += 1
        if sg or fc:
            body = bullets("pricing") + llm_block("pricing")
            if sg and "vw_points" in sg:
                body += "\n\n**Van Westendorp price points**\n\n" + md_table(sg["vw_points"], dict(pmc=idr, opp=idr, ipp=idr, pme=idr))
            if fc and "price_scenarios" in fc:
                body += f"\n\n**{c} price scenarios (next 12 months, elasticity-based)**\n\n" + md_table(fc["price_scenarios"])
            add("pricing", f"{n}. Pricing", body, ["van_westendorp", "elasticities", "price_scenarios"])
            n += 1
        if fc:
            body = bullets("forecast") + llm_block("forecast")
            body += "\n\n" + md_table(fc["forecast_summary_brand"][["brand", "revenue_last12", "revenue_next12", "revenue_growth"]],
                                      dict(revenue_last12=idr, revenue_next12=idr, revenue_growth=g1))
            body += "\n\n" + md_table(fc["forecast_summary_category"][["category", "revenue_last12", "revenue_next12", "revenue_growth"]],
                                      dict(revenue_last12=idr, revenue_next12=idr, revenue_growth=g1))
            add("forecast", f"{n}. Demand Forecast", body, ["market_forecast", "client_forecast", "backtest", "feature_importance"])
            n += 1

        # -- SWOT, recommendations, opportunities
        sw = []
        for k in ("Strengths", "Weaknesses", "Opportunities", "Threats"):
            items = swot.get(k, [])
            sw.append(f"**{k}**\n\n" + ("\n".join(f"- {i['title']}: {i['statement']} `[{i['id']}]`" for i in items) or "- (none identified)"))
        add("swot", f"{n}. SWOT Analysis", "\n\n".join(sw), ["swot"])
        n += 1
        if recs:
            tbl = pd.DataFrame([dict(ID=r["id"], Recommendation=r["title"], Horizon=r["horizon"], Timeline=r["timeline"],
                                     Owner=r["owner"], KPI=r["kpi"], Value=idr(r["value_idr"]) if r.get("value_idr") else "-",
                                     Priority=f"{r['priority']:.2f}") for r in recs])
            details = "\n\n".join(
                f"### {r['id']}. {r['title']}\n\n- **Action:** {r['action']}\n- **Why:** {r['rationale']}\n"
                f"- **KPI:** {r['kpi']}\n- **Owner / timeline:** {r['owner']}, {r['timeline']} ({r['effort']} effort)\n"
                f"- **Evidence:** {', '.join(f'`[{e}]`' for e in r['evidence'])}" for r in recs)
            add("recommendations", f"{n}. Recommendations", md_table(tbl) + "\n\n" + details, ["recommendations"])
            n += 1
        if opps is not None and len(opps):
            add("opportunities", f"{n}. Sized Opportunities",
                "Indicative 12-month value at stake (assumptions shown in the basis column).\n\n"
                + md_table(opps[["id", "opportunity", "value_idr", "basis", "evidence"]], dict(value_idr=idr)), ["opportunities"])
            n += 1
        caveats = bb.get("dq.caveats", [])
        mods = self.plan["modules"]
        studied = [
            ("Forecasts assume list prices stay at current levels and promotions repeat last year's calendar; shocks like "
             "the counterfeit crisis seen in the data are not predictable.", mods.get("forecast") or mods.get("pricing")),
            ("The concept revenue estimate uses an assumed 5% year-1 conversion of top-2-box intenders; validate with a "
             "pilot launch.", mods.get("segmentation")),
            ("Aspect detection is lexicon-based; aspect polarity comes from the sentiment model and inherits its error rate.",
             mods.get("consumer")),
        ]
        lim = "\n".join(f"- {x}" for x in caveats + [s for s, on in studied if on] + self._open_items())
        add("limitations", f"{n}. Risks and Limitations", lim)

        # -- appendix
        reg = pd.DataFrame([dict(ID=f.id, Agent=f.agent, Area=f.area, Finding=f.statement, Impact=f.impact,
                                 Confidence=f"{f.confidence:.2f}") for f in sorted(bb.findings(), key=lambda f: f.id)])
        app = "### A. Findings register\n\n" + md_table(reg, max_rows=200)
        if mc:
            tm = pd.DataFrame([dict(model=k, accuracy=v["accuracy"], macro_f1=v["macro_f1"],
                                    f1_negative=v["per_class"]["negative"]["f1-score"],
                                    f1_neutral=v["per_class"]["neutral"]["f1-score"],
                                    f1_positive=v["per_class"]["positive"]["f1-score"]) for k, v in mc["test_metrics"].items()])
            app += "\n\n### B. Sentiment model card (held-out test set)\n\n" + md_table(tm)
        if fc and "backtest_metrics" in fc:
            app += "\n\n### C. Forecast backtest (mean of 3 rolling folds)\n\n" + md_table(fc["backtest_metrics"])
        log = self._coordination_log()
        if log:
            app += "\n\n### D. Human review and agent coordination\n\n" + log
        add("appendix", "Appendix", app)
        return sections

    def _team_sentence(self) -> str:
        """Who did the work in this run, the modules left out for lack of data, and what the data is."""
        mods = self.plan["modules"]
        ran = [a for a in ("market", "competition", "consumer", "segmentation") if mods.get(a)]
        ran += ["forecast"] if (mods.get("forecast") or mods.get("pricing")) else []
        words = {1: "one analysis agent did the analysis", 2: "two analysis agents worked in parallel",
                 3: "three analysis agents worked in parallel", 4: "four analysis agents worked in parallel",
                 5: "five analysis agents worked in parallel"}
        text = (f"{len(ran) + 6} cooperating agents shared a blackboard: a Research Director planned the study from the brief, "
                "a Data Collection Agent loaded the data and live World Bank indicators, a Data Quality Agent cleaned it, "
                f"{words.get(len(ran), 'the analysis agents')}, and a Strategy Agent, Report Writer and Critic turned the "
                "evidence into this report.")
        gaps = self.plan.get("unavailable") or {}
        if gaps:
            text += (" **Not studied for lack of data:** " + "; ".join(f"{area} ({why})" for area, why in gaps.items())
                     + ". The research questions of those areas were left out of the plan.")
        data = self.plan.get("data") or {}
        if data.get("kind") == "real":
            text += f" **Data:** real marketplace data from {data['source']}."
        return text

    # -- oversight: approval gates, follow-up requests, open questions
    def _oversight(self) -> str:
        """One paragraph on who approved the plan and the recommendations, and what the Director sent back."""
        bb, parts = self.bb, []
        approvals = bb.get("approvals", [])
        if approvals and all(a["reviewer"].startswith("auto") and a["approved"] and not a["drop"] for a in approvals):
            parts_text = ("\n\n**Human review.** No reviewer was asked in this run: the plan and recommendation gates "
                          "approved automatically. Run with `--approve`, or tick the review option in the dashboard, to "
                          "review them.")
            approvals = []
        else:
            parts_text = ""
        for a in approvals:
            what = "research plan" if a["gate"] == "plan" else "recommendations"
            who = f"`{a['reviewer']}`"
            if a["drop"]:
                kind = "module(s)" if a["gate"] == "plan" else "recommendation(s)"
                parts.append(f"the {what} {'was' if a['gate'] == 'plan' else 'were'} approved by {who}, who removed "
                             f"{len(a['drop'])} {kind}")
            else:
                parts.append(f"the {what} {'was' if a['gate'] == 'plan' else 'were'} approved by {who}")
        text = parts_text
        if parts:
            text += "\n\n**Human review.** " + "; ".join(parts)[0].upper() + "; ".join(parts)[1:] + " (details in Appendix D)."
        ad = bb.get("director.adaptations", [])
        if ad:
            sent = ", ".join(f"the {a['agent']} ({a['action']}: {a['reason']})" for a in ad)
            text += (f"\n\n**Adaptive coordination.** After the first quality check the Research Director sent back {sent}, "
                     "then had the strategy, this report and the quality check redone.")
        return text

    def _open_items(self) -> list[str]:
        """Limitations from the run itself: questions left open, and recommendations the reviewer removed."""
        items = []
        open_qs = [f for f in self.bb.findings() if "open question" in f.tags]
        if open_qs:
            items.append("Research questions left open: " + "; ".join(
                f"{f.metrics.get('question', f.id)} `[{f.id}]`" for f in open_qs)
                + ". The responsible agents were asked again and found no evidence strong enough to answer them.")
        for r in self.bb.get("strategy.rejected_recommendations", []):
            items.append(f"The reviewer `{r['reviewer']}` removed the recommendation \"{r['title']}\"; it is not part of "
                         "this plan.")
        return items

    def _coordination_log(self) -> str:
        rows = [dict(Step=f"Approval: {a['gate']}", Decision="approved" if a["approved"] else "rejected",
                     By=a["reviewer"], Detail="; ".join(x for x in (", ".join(a["drop"]) and f"removed {', '.join(a['drop'])}",
                                                                     a["comment"]) if x) or "-")
                for a in self.bb.get("approvals", [])]
        rows += [dict(Step=f"Follow-up: {a['agent']}", Decision=a["action"], By="Research Director",
                      Detail=f"{a['reason']} -> {a['outcome']}") for a in self.bb.get("director.adaptations", [])]
        return md_table(pd.DataFrame(rows)) if rows else ""

    def _render(self, sections: list[dict]) -> str:
        return render_html(sections, self.bb, title=f"{self.client} - Market Research Report", run_id=self.ctx.run_id)
