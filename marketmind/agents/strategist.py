"""Strategy Agent: synthesises every finding into a SWOT, sized opportunities and a prioritised,
evidence-linked 12-month action plan.

Recommendations come from an explicit playbook of rules ("if the evidence shows X, recommend Y"),
each citing the findings that triggered it - so every action is traceable to data. The LLM, when
available, only polishes the narrative; the Critic later checks it did not invent numbers.
"""
from __future__ import annotations

import pandas as pd

from ..core.agent import BaseAgent
from ..core.approval import Decision, StudyRejected, request_approval
from ..core.findings import Finding
from .common import idr, pct

EFFORT = {"Low": 1.0, "Medium": 0.85, "High": 0.7}
CONVERSION = 0.05  # assumed trial conversion among top-2-box intenders in year 1 (stated in the report)


class StrategyAgent(BaseAgent):
    name = "Strategy Agent"
    role = "Strategy consultant. Synthesises findings from all analysts into a SWOT, sized opportunities and a prioritised plan."
    goal = "Turn evidence into a focused 12-month growth plan with owners, KPIs and expected impact."

    def register_tools(self):
        self.tool("rank_findings", self._rank, "prioritise findings by impact x confidence")
        self.tool("build_swot", self._swot, "map findings to strengths, weaknesses, opportunities and threats")
        self.tool("size_opportunities", self._size, "quantify the revenue at stake for each opportunity")
        self.tool("apply_strategy_playbook", self._playbook, "trigger evidence-based recommendations")
        self.tool("seek_client_approval", self._seek_approval, "put the recommendations to the human approval gate")
        self.tool("draft_executive_summary", self._exec_summary, "write the executive summary")

    def execute(self) -> str:
        self.plan = self.bb.require("plan")
        self.client = self.plan["client"]
        findings = self.use("rank_findings")
        self.F = {f.id: f for f in findings}
        self.t = {k.split(".")[0]: self.bb.get(k, {}) for k in
                  ("market.tables", "competition.tables", "consumer.tables", "segmentation.tables", "forecast.tables")}
        swot = self.use("build_swot", findings)
        opps = self.use("size_opportunities")
        recs = self.use("apply_strategy_playbook", opps)
        recs = self.use("seek_client_approval", recs)
        kpis = self._kpis()
        summary, summary_llm = self.use("draft_executive_summary", recs, kpis)
        self.put("strategy.swot", swot, "SWOT analysis")
        self.put("strategy.opportunities", opps, "Sized opportunities")
        self.put("strategy.recommendations", recs, "Prioritised recommendations")
        self.put("strategy.kpis", kpis, "Headline KPIs")
        self.put("strategy.exec_summary", summary, "Deterministic executive summary")
        if summary_llm:
            self.put("strategy.exec_summary_llm", summary_llm, "LLM-written executive summary (subject to QA)")
        return f"{len(recs)} recommendations; SWOT {sum(len(v) for v in swot.values())} items; {len(opps)} sized opportunities"

    # ------------------------------------------------------------------ tools
    def _seek_approval(self, recs: list[dict]) -> list[dict]:
        """Human approval gate: the reviewer approves the recommendations, drops some, or rejects the study.

        Runs before the executive summary is written, so a dropped recommendation cannot reach the report. When the
        Director has the strategy redone and the recommendations are unchanged, the earlier decision stands.
        """
        titles = [r["title"] for r in recs]
        last = self.bb.get("strategy.approved_proposal")
        if last and last["titles"] == titles:
            decision = Decision(**last["decision"])
            self.think("The recommendations are unchanged since the reviewer decided on them; that decision stands.")
        else:
            proposal = dict(recommendations=[dict(id=r["id"], title=r["title"], priority=r["priority"],
                                                  horizon=r["horizon"], evidence=r["evidence"]) for r in recs])
            decision = request_approval(self.ctx, "recommendations", proposal, self.name)
            self.put("strategy.approved_proposal", dict(titles=titles, decision=decision.to_dict()),
                     "Recommendations put to the reviewer and the decision taken")
        if not decision.approved:
            raise StudyRejected(f"the reviewer rejected the recommendations ({decision.comment or 'no reason given'})")
        dropped = [r for r in recs if r["id"] in decision.drop]
        if not dropped:
            return recs
        if len(dropped) == len(recs):  # nothing left to deliver: that is a rejection, whatever the form said
            raise StudyRejected("the reviewer removed every recommendation")
        kept = [r for r in recs if r["id"] not in decision.drop]
        self.put("strategy.rejected_recommendations",
                 [dict(id=r["id"], title=r["title"], reviewer=decision.reviewer, comment=decision.comment) for r in dropped],
                 "Recommendations the reviewer dropped")
        for i, r in enumerate(kept):
            r["id"] = f"R{i + 1}"
        self.think(f"The reviewer dropped {', '.join(r['id'] for r in dropped)}; {len(kept)} recommendations remain, "
                   f"renumbered R1-R{len(kept)}.")
        return kept

    def _rank(self) -> list[Finding]:
        fs = sorted(self.bb.findings(), key=lambda f: -f.priority)
        self.think(f"Synthesising {len(fs)} findings from {len({f.agent for f in fs})} agents.")
        return fs

    def _swot(self, findings: list[Finding]) -> dict:
        swot = {"S": [], "W": [], "O": [], "T": []}
        for f in findings:
            if f.swot in swot and len(swot[f.swot]) < 5:
                swot[f.swot].append(dict(id=f.id, title=f.title, statement=f.statement, priority=f.priority))
        return {"Strengths": swot["S"], "Weaknesses": swot["W"], "Opportunities": swot["O"], "Threats": swot["T"]}

    def _size(self) -> pd.DataFrame:
        comp, fc = self.t["competition"], self.t["forecast"]
        rows = []
        bs = comp.get("brand_share")
        rev = float(bs.set_index("brand").loc[self.client, "revenue_l12"]) if bs is not None else 0.0
        if "CMP-02" in self.F:
            m = self.F["CMP-02"].metrics
            target = m["client_mix"] + 0.5 * (m["market_mix"] - m["client_mix"])
            rows.append(dict(id="OPP-1", opportunity=f"Close half of the {m['channel']} gap",
                             value_idr=rev * (target - m["client_mix"]), basis=(
                                 f"lift {m['channel']} from {pct(m['client_mix'], sign=False)} to {pct(target, sign=False)} "
                                 f"of {self.client}'s {idr(rev)} revenue"), evidence="CMP-02"))
        if "SEG-02" in self.F and "SEG-04" in self.F:
            ms = self.bb.get("datasets", {}).get("market_size")
            moist = None
            if ms is not None:
                est = ms[(ms["category"] == "Moisturizer")].sort_values("year")
                moist = float(est.iloc[-1]["market_value_idr_bn"]) * 1e9
                moist_year = int(est.iloc[-1]["year"])
            p = self.F["SEG-02"].metrics
            if moist:
                val = moist * p["share"] * p["concept_t2b"] * CONVERSION
                rows.append(dict(id="OPP-2", opportunity="Fragrance-free barrier moisturizer launch (year 1)", value_idr=val,
                                 basis=(f"{idr(moist)} moisturizer market ({moist_year}) x {pct(p['share'], 0, sign=False)} target "
                                        f"segment x {pct(p['concept_t2b'], 0, sign=False)} intent x {pct(CONVERSION, 0, sign=False)} "
                                        f"assumed conversion"), evidence="SEG-02, SEG-04, CMP-08"))
        if "CMP-04" in self.F:
            ri = comp["region_index"].set_index("region")
            m = self.F["CMP-04"].metrics
            share = float(bs.set_index("brand").loc[self.client, "share_l12"])
            mk = comp["brand_share"]["revenue_l12"].sum()
            val = 0.0
            regions = [v for k, v in m.items() if k.startswith("region_") and not k.endswith(("_index", "_growth"))]
            for r in regions:
                val += mk * ri.loc[r, "market_mix"] * share * max(0.9 - ri.loc[r, "index"], 0)
            rows.append(dict(id="OPP-3", opportunity="Raise presence in fast-growing regions to 0.9x parity", value_idr=val,
                             basis=f"{', '.join(regions)}: lift {self.client}'s index to 0.9", evidence="CMP-04"))
        if "CMP-09" in self.F:
            m = self.F["CMP-09"].metrics
            rows.append(dict(id="OPP-4", opportunity="Eliminate stock-outs", value_idr=float(m["lost_revenue_idr"]),
                             basis="sales lost to stock-outs in the last 12 months", evidence="CMP-09"))
        if "FCT-04" in self.F and fc:
            ps = fc["price_scenarios"].set_index("price_change_pct")
            base = float(fc["forecast_summary_brand"].set_index("brand").loc[self.client, "revenue_next12"])
            el_txt = f"elasticity {self.F['FCT-04'].metrics['elasticity']:.2f}"
            basis = f"{el_txt} applied to the {idr(base)} baseline"
            h = int(self.plan.get("horizon_months", 12))
            if h != 12:  # the forecast covers h months, but opportunities are sized over 12
                base = base * 12 / h
                basis = f"{el_txt} applied to a {idr(base)} 12-month baseline (the {h}-month forecast scaled to a year)"
            rows.append(dict(id="OPP-5", opportunity="Avoid a further 5% list-price rise (revenue protected)",
                             value_idr=-base * ps.loc[5.0, "revenue_change_pct"] / 100, basis=basis, evidence="FCT-04"))
        opps = pd.DataFrame(rows)
        if len(opps):
            opps["value_idr"] = opps["value_idr"].round(-6)
            opps = opps.sort_values("value_idr", ascending=False).reset_index(drop=True)
        return opps

    def _playbook(self, opps: pd.DataFrame) -> list[dict]:
        F, c = self.F, self.client
        ov = opps.set_index("id")["value_idr"].to_dict() if len(opps) else {}
        recs = []

        def add(title, action, rationale, evidence, kpi, timeline, owner, effort, value=None):
            ev = [e for e in evidence if e in F]
            if not ev:
                return
            impact = max(F[e].impact for e in ev)
            conf = sum(F[e].confidence for e in ev) / len(ev)
            recs.append(dict(title=title, action=action, rationale=rationale, evidence=ev, kpi=kpi, timeline=timeline,
                             owner=owner, effort=effort, value_idr=value, impact=impact, confidence=round(conf, 2),
                             priority=round(impact * conf * EFFORT[effort], 2)))

        if "CMP-02" in F:
            m = F["CMP-02"].metrics
            add(f"Build an always-on {m['channel']} growth engine",
                f"Recruit nano/micro creators on affiliate commission, run weekly live-shopping and mega-sale campaigns, create "
                f"{m['channel']}-exclusive bundles and ring-fence stock for the channel.",
                f"{c} earns {pct(m['client_mix'], sign=False)} of sales on {m['channel']} versus {pct(m['market_mix'], sign=False)} "
                f"for the market, the fastest-growing channel ({pct(m['channel_growth'])}).",
                ["CMP-02", "MKT-03", "CMP-07"], f"{m['channel']} share of {c} sales from {pct(m['client_mix'], sign=False)} to "
                f"{pct(m['client_mix'] + 0.5 * (m['market_mix'] - m['client_mix']), sign=False)} in 12 months",
                "0-6 months", "E-commerce & Digital", "Medium", ov.get("OPP-1"))
        if "CON-03" in F:
            m = F["CON-03"].metrics
            add(f"Fix the {m['aspect'].lower()} issue and win back trust",
                "Run a root-cause review with the supplier, replace affected units proactively, flag the improved version on "
                "every listing and monitor complaint rates weekly with the sentiment model as an early-warning system.",
                f"{m['aspect']} complaints spiked to {m['peak_rate']:.1f} per 100 reviews ({m['start']} to {m['end']}) versus a "
                f"{m['baseline_rate']:.1f} baseline.",
                ["CON-03", "CON-09"], f"{m['aspect']} complaints back below {m['baseline_rate'] * 1.5:.1f} per 100 reviews within 3 months",
                "0-3 months", "Operations & Quality", "Low")
        if "SEG-02" in F and "SEG-04" in F:
            p, v = F["SEG-02"].metrics, F["SEG-04"].metrics
            close_call = not v.get("price_settled", True) and v.get("alternative_price")
            add(f"Launch the fragrance-free barrier-repair moisturizer at {idr(v['recommended_price'])}",
                f"Position it on ceramide + skin-barrier repair, fragrance-free and dermatologically tested; target "
                f"'{p['segment']}' first, seed through dermatologist and creator content, launch on Shopee and TikTok Shop "
                f"before Ramadan."
                + (f" The price research does not settle between {idr(v['recommended_price'])} and "
                   f"{idr(v['alternative_price'])}: test both in the first month before fixing the list price."
                   if close_call else ""),
                f"{pct(p['concept_t2b'], 0, sign=False)} top-2-box intent in the primary segment; acceptable price range "
                f"{idr(v['pmc'])}-{idr(v['pme'])}; the white space has little competing supply.",
                ["SEG-02", "SEG-04", "CMP-08", "CON-07", "MKT-06"], f"Year-1 revenue of {idr(ov.get('OPP-2', 0))} "
                f"and 4.7+ star rating", "3-9 months", "Brand & R&D", "High", ov.get("OPP-2"))
        if "FCT-04" in F:
            m = F["FCT-04"].metrics
            if m["elasticity"] < -1:
                add("Hold list prices; fund value with smarter promotions",
                    "Freeze list prices for 12 months, shift value to bundles, larger sizes and mega-sale vouchers, and test "
                    "price moves channel by channel before rolling out.",
                    f"Demand is price-elastic ({m['elasticity']:.2f}): a 5% rise would cut revenue {m['revenue_change_5pct']:+.1f}%.",
                    ["FCT-04", "CON-06"], "Price/value net sentiment back to its prior level; volume growth at or above market",
                    "0-12 months", "Revenue Management", "Low", ov.get("OPP-5"))
        if "CMP-04" in F:
            add("Expand distribution in outer-Java growth regions",
                "Add modern-trade doors and regional distributors, and geo-target social commerce campaigns in the "
                "under-indexed regions.",
                F["CMP-04"].statement, ["CMP-04", "MKT-04"], f"{c}'s index in target regions from below 0.9 to 0.9",
                "3-12 months", "Sales", "Medium", ov.get("OPP-3"))
        if "CMP-05" in F:
            th = F["CMP-05"].metrics["brand"]
            add(f"Defend against {th} in the overlapping categories",
                f"Benchmark {th}'s hero products, sharpen comparative claims where {c} wins on consumer sentiment, and "
                "protect key listings with bundles during its campaigns.",
                F["CMP-05"].statement, ["CMP-05", "SEG-05"], f"Hold or gain share versus {th} in overlapping categories",
                "0-6 months", "Marketing", "Medium")
        if "CON-05" in F:
            m = F["CON-05"].metrics
            add(f"Win over {m['brand']}'s customers during its {m['aspect'].lower()} crisis",
                "Promote authenticity guarantees (official stores, QR verification, BPOM number on pack) and target its "
                "lapsing buyers with trial sizes and comparison content.",
                F["CON-05"].statement, ["CON-05", "SEG-05"], f"Capture switchers from {m['brand']}: +0.5 pp share in 6 months",
                "0-3 months", "Marketing", "Low")
        if "MKT-05" in F or "CMP-09" in F:
            add("Plan stock and campaigns around Ramadan and the mega-sales",
                "Use the ML forecast in monthly S&OP, build safety stock six weeks before Ramadan and 11.11/12.12, and "
                "phase campaigns to the pre-Eid peak.",
                (F["MKT-05"].statement if "MKT-05" in F else "") + (" " + F["CMP-09"].statement if "CMP-09" in F else ""),
                ["MKT-05", "CMP-09", "FCT-01"], "Zero stock-out days in peak months", "0-3 months", "Supply Chain", "Low",
                ov.get("OPP-4"))
        recs.sort(key=lambda r: -r["priority"])
        for i, rec in enumerate(recs, 1):
            rec["id"] = f"R{i}"
            rec["horizon"] = "Quick win" if rec["timeline"].startswith("0-3") else (
                "Core move" if rec["timeline"].startswith("0-6") or rec["timeline"].startswith("0-12") else "Strategic bet")
        return recs

    def _kpis(self) -> dict:
        F = self.F

        def m(fid, key, default=None):
            return F[fid].metrics.get(key, default) if fid in F else default

        return dict(
            client=self.client, market_size_idr_bn=m("MKT-01", "market_size_idr_bn"), market_year=m("MKT-01", "year"),
            market_cagr=m("MKT-01", "cagr"), panel_growth=m("CMP-01", "panel_growth"), client_share=m("CMP-01", "share"),
            client_rank=m("CMP-01", "rank"), client_growth=m("CMP-01", "growth"), client_revenue_l12_idr=m("CMP-01", "revenue_l12_idr"),
            weakest_channel=m("CMP-02", "channel"), weakest_channel_index=m("CMP-02", "index"), top_threat=m("CMP-05", "brand"),
            sentiment_model_f1=m("CON-01", "macro_f1"), top_pain_point=m("CON-03", "aspect"), nps=m("CON-08", "nps"),
            target_segment=m("SEG-02", "segment"), concept_t2b=m("SEG-02", "concept_t2b"),
            recommended_price_idr=m("SEG-04", "recommended_price"), forecast_market_growth=m("FCT-01", "growth"),
            forecast_client_growth=m("FCT-02", "growth"), elasticity=m("FCT-04", "elasticity"),
            fastest_category=m("MKT-02", "top_category"), fastest_channel=m("MKT-03", "fastest_channel"),
            horizon_months=int(self.plan.get("horizon_months", 12)))

    def _exec_summary(self, recs: list[dict], kpis: dict) -> tuple[str, str | None]:
        F, c = self.F, self.client
        lines = []
        for fid in ("MKT-01", "FCT-01", "CMP-01", "CMP-02", "CON-03", "CMP-08", "SEG-02", "SEG-04", "FCT-04"):
            if fid in F:
                lines.append(f"- {F[fid].statement} [{fid}]")
        top = "; ".join(f"({r['id']}) {r['title']}" for r in recs[:4])
        lines.append(f"- Priority actions for {c}: {top}.")
        deterministic = "\n".join(lines)
        llm_text = None
        if self.llm.available and self.options.get("use_llm", True):
            facts = dict(client=c, findings=[F[k].to_dict() for k in F if F[k].area != "data"][:30],
                         recommendations=[{k: r[k] for k in ("id", "title", "rationale", "kpi", "value_idr")} for r in recs])
            llm_text = self.ask_llm(
                "Write the executive summary of the market research report as 5-7 bullet points (markdown '- '), "
                "120-220 words in total. Lead with the single most important insight, then market context, competitive "
                "position, consumer insight, the concept opportunity and the top actions. Cite finding IDs in brackets "
                "after each claim.", facts, max_tokens=900)
        return deterministic, llm_text
