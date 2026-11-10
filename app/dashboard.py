"""MarketMind dashboard - launch studies, watch the agents work live, and explore every result.

    streamlit run app/dashboard.py
"""
from __future__ import annotations

import html
import itertools
import json
import subprocess
from contextlib import contextmanager
import sys
import threading
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
warnings.filterwarnings("ignore")

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402
import streamlit.components.v1 as components  # noqa: E402

from marketmind.config import DATA_RAW, DATASETS, DEFAULT_BRIEF, DEFAULT_CLIENT, MODELS_DIR  # noqa: E402
from marketmind.core.llm import LLMClient  # noqa: E402
from marketmind.core.store import list_runs, load_run  # noqa: E402
from marketmind.reporting.charts import CHARTS, TableSource, tk  # noqa: E402

st.set_page_config(page_title="MarketMind - Agentic Market Research", page_icon="🧭", layout="wide")
st.markdown("""<style>
.block-container{padding-top:1.6rem;padding-bottom:3rem}
.mm-chip{display:inline-block;border:1px solid rgba(128,128,128,.35);border-radius:999px;padding:2px 10px;margin:0 6px 6px 0;font-size:.82rem;opacity:.9}
.mm-finding{border-left:3px solid #2a78d6;padding:4px 0 4px 12px;margin:6px 0}
.mm-finding small{opacity:.7}
.mm-token{border-radius:4px;padding:1px 3px;margin:1px;display:inline-block}
.mm-kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin:8px 0 18px}
.mm-kpi{border:1px solid rgba(128,128,128,.28);border-radius:10px;padding:10px 14px}
.mm-kpi .l{font-size:.8rem;opacity:.7}
.mm-kpi .v{font-size:1.35rem;font-weight:600;line-height:1.3;overflow-wrap:anywhere}
.mm-kpi .n{font-size:.8rem;opacity:.75}
</style>""", unsafe_allow_html=True)


# ============================================================================ helpers
def theme_mode() -> str:
    """Chart palette follows the app theme: the configured base theme wins, else the viewer's theme."""
    base = st.get_option("theme.base")
    if base in ("light", "dark"):
        return base
    try:
        return "dark" if st.context.theme.type == "dark" else "light"
    except Exception:
        return "light"


@st.cache_resource(show_spinner=False)
def get_llm() -> LLMClient:
    return LLMClient()


@st.cache_data(show_spinner=False)
def brands_in_data() -> list[str]:
    f = DATA_RAW / DATASETS["sales"]["file"]
    return sorted(pd.read_csv(f, usecols=["brand"])["brand"].unique()) if f.exists() else [DEFAULT_CLIENT]


@st.cache_resource(show_spinner=False)
def get_run(run_id: str):
    return load_run(run_id)


@st.cache_resource(show_spinner="Loading the sentiment model ...")
def get_suite(data_hash: str, model_dir: str = ""):
    from marketmind.ml.sentiment import SentimentSuite
    suite = SentimentSuite(ROOT / model_dir if model_dir else MODELS_DIR / "sentiment")
    return suite if suite.try_load(data_hash) else None


SENTIMENT_DATA = {"study": "The study's reviews (default)", "study+real": "The study's reviews + real reviews",
                  "real": "Real reviews only"}


def study_score(card: dict) -> tuple[dict, str]:
    """The sentiment score on the study's own reviews, whichever data the models were trained on (as in CON-01)."""
    sel, by_source = card["selected"], card.get("test_metrics_by_source") or {}
    if "study" in by_source:
        return by_source["study"][sel], "held-out study reviews"
    if card.get("study_reviews_check"):
        return card["study_reviews_check"], "all study reviews, unseen in training"
    return card["test_metrics"][sel], "held-out reviews"


_CHART_IDS = itertools.count()


def chart(src: TableSource, key: str, height: int | None = None) -> None:
    fn = CHARTS.get(key)
    fig = fn(src, theme_mode()) if fn else None
    if fig is None:
        st.caption(f"_{key.replace('_', ' ')}: no data in this run_")
        return
    if height:
        fig.update_layout(height=height)
    st.plotly_chart(fig, width="stretch", theme=None, config={"displaylogo": False}, key=f"chart-{key}-{next(_CHART_IDS)}")


def table(df: pd.DataFrame | None, label: str = "Table view", expanded: bool = False) -> None:
    if df is None or df.empty:
        return
    with st.expander(label, expanded=expanded):
        st.dataframe(df, width="stretch", hide_index=True)


def findings(run, area: str | list[str], limit: int | None = None) -> None:
    areas = [area] if isinstance(area, str) else area
    fs = sorted([f for f in run.findings if f.area in areas], key=lambda f: f.id)[:limit]
    for f in fs:
        st.markdown(f'<div class="mm-finding"><b>{html.escape(f.title)}</b> <small>[{f.id} · {html.escape(f.agent)} · '
                    f'impact {f.impact}/5 · confidence {f.confidence:.0%}]</small><br>{html.escape(f.statement)}</div>',
                    unsafe_allow_html=True)


@contextmanager
def guard(section: str):
    """Keep one failing section from blanking the rest of the dashboard."""
    try:
        yield
    except Exception as exc:
        st.error(f"{section} could not be rendered: {type(exc).__name__}: {exc}")


def kpi_tiles(items: list[tuple[str, str, str]]) -> None:
    tiles = "".join(f'<div class="mm-kpi"><div class="l">{html.escape(l)}</div><div class="v">{html.escape(v)}</div>'
                    f'<div class="n">{html.escape(n)}</div></div>' for l, v, n in items)
    st.markdown(f'<div class="mm-kpis">{tiles}</div>', unsafe_allow_html=True)


def fmt_idr(x) -> str:
    if x is None or pd.isna(x):
        return "n/a"
    x = float(x)
    return f"Rp {x / 1e12:,.2f} tn" if abs(x) >= 1e12 else f"Rp {x / 1e9:,.1f} bn" if abs(x) >= 1e9 else f"Rp {x:,.0f}"


def pct(x, sign=True) -> str:
    return "n/a" if x is None or pd.isna(x) else (f"{x * 100:+.1f}%" if sign else f"{x * 100:.1f}%")


# ============================================================================ live run
STATUS_ICON = {"started": "⏳ running", "completed": "✅ done", "failed": "❌ failed", "skipped": "⏭️ skipped"}


def render_progress(events, grid, feed) -> None:
    status, seconds = {}, {}
    for ev in events:
        if ev.kind == "status" and ev.agent != "System":
            status[ev.agent] = ev.message
            if "seconds" in ev.data:
                seconds[ev.agent] = ev.data["seconds"]
    rows = [dict(Agent=a, Status=STATUS_ICON.get(s, s), Seconds=seconds.get(a, "")) for a, s in status.items()]
    if rows:
        grid.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    recent = [e for e in events if e.kind in ("thought", "action", "finding", "message", "warning", "error", "llm")][-12:]
    lines = [f"`{time.strftime('%H:%M:%S', time.localtime(e.ts))}` **{e.agent}** · _{e.kind}_ · {e.message[:220]}" for e in recent]
    feed.markdown("\n\n".join(lines) if lines else "_starting ..._")


def launch(brief: str, client: str, use_llm: bool, retrain: bool, parallel: bool, sentiment_data: str = "study") -> str | None:
    from marketmind.system import MarketResearchSystem
    system = MarketResearchSystem(brief=brief, client=client, use_llm=use_llm, force_retrain=retrain, parallel=parallel,
                                  llm=get_llm(), sentiment_data=sentiment_data)
    holder: dict = {}

    def target():
        try:
            holder["result"] = system.run()
        except Exception as exc:  # surfaced in the UI below
            holder["error"] = f"{type(exc).__name__}: {exc}"

    th = threading.Thread(target=target, daemon=True)
    th.start()
    with st.status(f"Run {system.run_id}: the agent team is working ...", expanded=True) as box:
        c1, c2 = st.columns([1, 1.4])
        with c1:
            st.caption("Agent status")
            grid = st.empty()
        with c2:
            st.caption("Live trace (thoughts, tool calls, findings)")
            feed = st.empty()
        while th.is_alive():
            render_progress(system.tracer.snapshot(), grid, feed)
            time.sleep(0.6)
        th.join()
        render_progress(system.tracer.snapshot(), grid, feed)
        if "error" in holder:
            box.update(label=f"Run failed: {holder['error']}", state="error")
            return None
        res = holder["result"]
        box.update(label=f"Run {res.run_id} {res.status} in {res.seconds}s - QA {res.qa.get('score')}/100",
                   state="complete" if res.status == "completed" else "error", expanded=False)
    return system.run_id


# ============================================================================ sidebar
llm = get_llm()
with st.sidebar:
    st.title("🧭 MarketMind")
    st.caption("Multi-agent market research system · Indonesian local skincare")
    data_ok = all((DATA_RAW / v["file"]).exists() for k, v in DATASETS.items() if k != "social_labels")
    if not data_ok:
        st.warning("Datasets not found.")
        if st.button("Generate datasets", type="primary", width="stretch"):
            with st.spinner("Generating realistic synthetic datasets ..."):
                subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_data.py")], check=True)
            st.cache_data.clear()
            st.rerun()
    runs = list_runs()
    with st.expander("▶️  New research run", expanded=not runs):
        brief = st.text_area("Research brief", DEFAULT_BRIEF, height=190)
        brands = brands_in_data()
        client = st.selectbox("Client brand", brands, index=brands.index(DEFAULT_CLIENT) if DEFAULT_CLIENT in brands else 0)
        use_llm = st.toggle("Use LLM reasoning", value=llm.available, disabled=not llm.available,
                            help="Add a free API key to .env (see README) to enable LLM planning and narrative.")
        from marketmind.ml import real_reviews
        real_ok = real_reviews.available()
        sentiment_data = st.selectbox(
            "Sentiment training data", list(SENTIMENT_DATA) if real_ok else ["study"], format_func=SENTIMENT_DATA.get,
            help="Which reviews the deep-learning sentiment models learn from. The real Shopee/Tokopedia beauty reviews "
                 "must be downloaded first (docs/DATA_SOURCES.md); a new mix trains once, for a few minutes.")
        retrain = st.toggle("Retrain deep-learning model", value=False)
        parallel = st.toggle("Run analysis agents in parallel", value=True)
        start = st.button("Run study", type="primary", width="stretch", disabled=not data_ok)
    st.divider()
    st.caption(f"**LLM:** {llm.describe()}")
    if llm.available and st.button("Test LLM connection", width="stretch"):
        ok, msg = llm.ping()
        (st.success if ok else st.error)(f"{'Connected' if ok else 'Failed'}: {msg[:200]}")
    if runs:
        labels = {r["run_id"]: f"{r['run_id']} · QA {r['qa_score'] if r['qa_score'] is not None else '-'} · {r['client']}" for r in runs}
        ids = list(labels)
        default = st.session_state.get("run_id", ids[0])
        run_id = st.selectbox("Saved runs", ids, index=ids.index(default) if default in ids else 0, format_func=labels.get)
        st.session_state["run_id"] = run_id

if start:
    new_id = launch(brief, client, use_llm, retrain, parallel, sentiment_data)
    if new_id:
        st.session_state["run_id"] = new_id
        st.session_state.pop(f"chat-{new_id}", None)
        st.rerun()

if not runs:
    st.header("Welcome to MarketMind")
    st.write("Eleven AI agents plan, collect, clean, analyse and report a complete market research study. "
             "Open **New research run** in the sidebar and press **Run study** to start the first one.")
    st.stop()

run = get_run(st.session_state["run_id"])
src = TableSource.from_run(run)
meta = run.meta
kpis = run.json("strategy.kpis", {}) or {}
client = meta.get("client", "")
qa = meta.get("qa", {})

# ============================================================================ header
st.title(f"{client} · Market Research")
chips = [f"Run {run.run_id}", f"{meta.get('seconds')}s", meta.get("llm", {}).get("description", ""),
         f"QA {qa.get('score')}/100 {'passed' if qa.get('passed') else 'not passed'}",
         f"{len(run.findings)} findings", f"{len(run.json('strategy.recommendations', []) or [])} recommendations"]
st.markdown("".join(f'<span class="mm-chip">{html.escape(str(c))}</span>' for c in chips if c), unsafe_allow_html=True)

tabs = st.tabs(["Overview", "Agents", "Market", "Competition", "Consumers (DL)", "Segments", "Forecast & pricing",
                "Strategy", "Report", "Ask the analyst", "Evaluation", "Data"])

# ---------------------------------------------------------------------------- overview
with tabs[0], guard("Overview"):
    with st.expander("Research brief", expanded=False):
        st.write(meta.get("brief", ""))
    el_txt = f"elasticity {kpis['elasticity']:.2f}" if kpis.get("elasticity") is not None else ""
    kpi_tiles([
        (f"Market size {kpis.get('market_year', '')}", fmt_idr((kpis.get("market_size_idr_bn") or 0) * 1e9),
         f"CAGR {pct(kpis.get('market_cagr'), False)} since 2019"),
        (f"{client} panel share", f"{pct(kpis.get('client_share'), False)} (#{kpis.get('client_rank', '-')})",
         f"growth {pct(kpis.get('client_growth'))} vs panel {pct(kpis.get('panel_growth'))}"),
        ("Forecast growth, next 12 months", pct(kpis.get("forecast_client_growth")),
         f"market {pct(kpis.get('forecast_market_growth'))}"),
        ("Top competitive threat", kpis.get("top_threat") or "n/a", f"weakest channel: {kpis.get('weakest_channel') or 'n/a'}"),
        ("Concept target segment", kpis.get("target_segment") or "n/a", f"purchase intent {pct(kpis.get('concept_t2b'), False)}"),
        ("Recommended launch price", fmt_idr(kpis.get("recommended_price_idr")), el_txt),
    ])
    left, right = st.columns([1.15, 1])
    with left:
        st.subheader("Key findings")
        top = sorted([f for f in run.findings if "methodology" not in f.tags], key=lambda f: -f.priority)[:7]
        for f in top:
            st.markdown(f'<div class="mm-finding"><b>{html.escape(f.title)}</b> <small>[{f.id} · priority {f.priority:.2f}]</small>'
                        f'<br>{html.escape(f.statement)}</div>', unsafe_allow_html=True)
    with right:
        st.subheader("Priority actions")
        for r in (run.json("strategy.recommendations", []) or [])[:5]:
            with st.container(border=True):
                st.markdown(f"**{r['id']}. {r['title']}**  \n{r['horizon']} · {r['timeline']} · {r['owner']}"
                            + (f" · value {fmt_idr(r['value_idr'])}" if r.get("value_idr") else ""))
                st.caption(f"KPI: {r['kpi']}")
    c1, c2 = st.columns(2)
    with c1:
        chart(src, "brand_share")
    with c2:
        chart(src, "client_forecast")

# ---------------------------------------------------------------------------- agents
with tabs[1], guard("Agents"):
    st.subheader("How the agent team worked")
    wf = meta.get("workflow", {})
    agents = meta.get("agents", {})
    if wf.get("tasks"):
        fill = {"completed": "#d9f2d9", "failed": "#f8d7d7", "skipped": "#eeeeee"}
        lines = ['digraph G { rankdir=LR; bgcolor="transparent"; node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11];',
                 f'director [label="Research Director\\n(plan + supervise)", fillcolor="#dbe8fb"];']
        for tid, name in wf["tasks"].items():
            res = agents.get(tid, {})
            label = name.replace(" Agent", "\\nAgent").replace("(QA)", "\\n(QA)")
            lines.append(f'{tid} [label="{label}\\n{res.get("seconds", "")}s", fillcolor="{fill.get(res.get("status"), "#ffffff")}"];')
        lines.append("director -> collect;")
        lines += [f"{a} -> {b};" for a, b in wf.get("edges", [])]
        lines.append('qa -> director [style=dashed, label="QA verdict / revision loop", fontsize=9];')
        lines.append("}")
        st.graphviz_chart("\n".join(lines), width="stretch")
    roster = pd.DataFrame(meta.get("agent_roster", []))
    if not roster.empty:
        res = pd.DataFrame([dict(name=v["agent"], status=v["status"], seconds=v["seconds"], tool_calls=v["tool_calls"],
                                 findings=v["findings"], llm_calls=v["llm_calls"], summary=v["summary"] or v.get("error"))
                            for v in agents.values()]).drop_duplicates("name", keep="last")
        st.dataframe(roster.merge(res, on="name", how="left")[["name", "role", "ml", "status", "seconds", "tool_calls",
                                                                "findings", "llm_calls", "summary"]],
                     width="stretch", hide_index=True,
                     column_config={"ml": st.column_config.TextColumn("ML / DL capability", width="medium"),
                                    "role": st.column_config.TextColumn(width="large")})
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("**Agent-to-agent messages**")
        msgs = meta.get("messages", [])
        st.dataframe(pd.DataFrame(msgs) if msgs else pd.DataFrame([{"info": "No messages (QA passed first time)."}]),
                     width="stretch", hide_index=True)
        st.markdown("**QA history**")
        st.dataframe(pd.DataFrame(qa.get("history", [])), width="stretch", hide_index=True)
    with c2:
        st.markdown("**LLM usage**")
        st.json(meta.get("llm", {}), expanded=False)
    st.markdown("**Trace explorer**")
    trace = pd.DataFrame(run.trace)
    if not trace.empty:
        f1, f2 = st.columns(2)
        who = f1.multiselect("Agents", sorted(trace["agent"].unique()))
        kind_opts = sorted(trace["kind"].unique())
        kinds = f2.multiselect("Event kinds", kind_opts,
                               default=[k for k in ("thought", "finding", "action", "warning", "message") if k in kind_opts])
        view = trace[(trace["agent"].isin(who) if who else True) & (trace["kind"].isin(kinds) if kinds else True)]
        st.dataframe(view[["time", "agent", "kind", "message"]], width="stretch", hide_index=True, height=360)

# ---------------------------------------------------------------------------- market
with tabs[2], guard("Market"):
    findings(run, "market")
    c1, c2 = st.columns(2)
    with c1:
        chart(src, "market_size")
        chart(src, "channel_mix")
        chart(src, "seasonality")
    with c2:
        chart(src, "category_growth")
        chart(src, "region_growth")
        chart(src, "monthly_market")
    chart(src, "topic_trends")
    table(src.t("market", "topic_trends"), "Topic trend table")
    table(run.table("external.macro"), "World Bank indicators (live API)")

# ---------------------------------------------------------------------------- competition
with tabs[3], guard("Competition"):
    findings(run, "competition")
    c1, c2 = st.columns(2)
    with c1:
        chart(src, "brand_share")
        chart(src, "channel_index")
        chart(src, "threats")
    with c2:
        chart(src, "share_trend")
        chart(src, "region_index")
        chart(src, "white_space")
    chart(src, "positioning")
    table(src.t("competition", "brand_share"), "Brand share table")
    table(src.t("competition", "threats"), "Threat scoring components")
    table(src.t("competition", "white_space"), "White-space scan")

# ---------------------------------------------------------------------------- consumers
with tabs[4], guard("Consumers"):
    card = run.json("consumer.model_card", {}) or {}
    if card:
        sel = card["selected"]
        tr = card.get("transfer_metrics", {}).get(card.get("transfer_model", ""), {})
        head, basis = study_score(card)
        kpi_tiles([
            ("Selected model (validation)", {"bigru": "BiGRU + attention", "linear": "TF-IDF + LogReg",
                                             "ensemble": "BiGRU + TF-IDF ensemble"}[sel], f"vocabulary {card.get('vocab_size', 0):,} tokens"),
            ("Test macro-F1", f"{head['macro_f1']:.3f}", f"accuracy {head['accuracy']:.3f} · {basis}"),
            ("Training data", f"{card['n_train']:,} reviews",
             f"{SENTIMENT_DATA.get((card.get('training_data') or {}).get('mode', 'study'), '').replace(' (default)', '')} · "
             f"test set {card['n_test']:,}"),
            ("Social transfer macro-F1", f"{tr.get('macro_f1', 0):.3f}" if tr else "n/a",
             f"{card.get('transfer_model', '')} on {card.get('transfer_n', 0)} hand-labelled posts" if tr else ""),
        ])
    findings(run, "consumer")
    c1, c2, c3 = st.columns(3)
    with c1:
        chart(src, "model_quality", 330)
    with c2:
        chart(src, "confusion", 330)
    with c3:
        chart(src, "training_curve", 330)
    c1, c2 = st.columns(2)
    with c1:
        chart(src, "sentiment_by_brand")
        chart(src, "social_sentiment")
    with c2:
        chart(src, "aspect_heatmap")
        chart(src, "client_aspect_trend")
    table(src.t("consumer", "anomalies"), "Detected complaint spikes (Poisson-tested)", expanded=True)
    ex = src.t("consumer", "example_reviews")
    if ex is not None and len(ex):
        with st.expander("Voice of the customer"):
            for r in ex.itertuples():
                st.markdown(f"> {r.text}  \n> — *{r.brand} · {r.aspect} · {r.type}*")

    st.subheader("Try the deep-learning model")
    suite = get_suite(card.get("data_hash", ""), (card.get("training_data") or {}).get("model_dir", "")) if card else None
    if suite is None:
        st.info("The trained model is not on disk for this run (retrain by starting a new run).")
    else:
        from marketmind.ml.text import ASPECT_LABELS, detect_aspects, split_clauses
        text = st.text_input("Type a review or post (Indonesian slang and English both work)",
                             "Teksturnya ringan dan cepat meresap, tapi pump-nya rusak baru seminggu dipake 😭")
        if text.strip():
            p = suite.predict_proba([text])[0]
            label = ["negative", "neutral", "positive"][int(p.argmax())]
            m = st.columns(4)
            m[0].metric("Prediction", label)
            m[1].metric("P(negative)", f"{p[0]:.2f}")
            m[2].metric("P(neutral)", f"{p[1]:.2f}")
            m[3].metric("P(positive)", f"{p[2]:.2f}")
            att = suite.neural.explain(text)
            if att:
                mx = max(w for _, w in att) or 1
                rgb = "57,135,229" if theme_mode() == "dark" else "42,120,214"
                spans = "".join(f'<span class="mm-token" style="background:rgba({rgb},{0.08 + 0.75 * w / mx:.2f})">{html.escape(t)}</span>'
                                for t, w in att)
                st.markdown("**Where the BiGRU looked (attention weights):**", unsafe_allow_html=True)
                st.markdown(spans, unsafe_allow_html=True)
            rows = []
            for clause in split_clauses(text):
                for a in detect_aspects(clause):
                    s = float(suite.score_clauses([clause])[0])
                    rows.append(dict(clause=clause, aspect=ASPECT_LABELS[a], score=round(s, 3),
                                     polarity="positive" if s > 0.2 else "negative" if s < -0.2 else "neutral"))
            if rows:
                st.markdown("**Aspect-based sentiment:**")
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

# ---------------------------------------------------------------------------- segments
with tabs[5], guard("Segments"):
    findings(run, ["segmentation"])
    chart(src, "segment_map", 340)
    c1, c2 = st.columns([1.3, 1])
    with c1:
        chart(src, "segment_importance")
    with c2:
        chart(src, "concept")
    prof = src.t("segmentation", "profiles")
    concept_df = src.t("segmentation", "concept")
    if prof is not None:
        roles = concept_df.set_index("segment")["role"].to_dict() if concept_df is not None and "role" in concept_df else {}
        cols = st.columns(len(prof))
        for col, p in zip(cols, prof.itertuples()):
            with col.container(border=True):
                tag = {"primary": "🎯 primary target", "secondary": "secondary target"}.get(roles.get(p.segment), "")
                st.markdown(f"**{p.name}**  \n{p.share:.0%} of consumers {('· ' + tag) if tag else ''}")
                st.caption(p.description)
                st.markdown(f"Drivers: _{p.drivers}_  \nConcept intent: **{p.concept_t2b:.0%}** · NPS {p.nps_main_brand:+.0f}")
    findings(run, "pricing")
    chart(src, "van_westendorp")
    table(src.t("segmentation", "vw_points"), "Van Westendorp price points", expanded=True)
    table(src.t("segmentation", "k_selection"), "Choosing k (silhouette, Calinski-Harabasz, Davies-Bouldin)")

# ---------------------------------------------------------------------------- forecast & pricing
with tabs[6], guard("Forecast & pricing"):
    findings(run, "forecast")
    c1, c2 = st.columns(2)
    with c1:
        chart(src, "market_forecast")
        chart(src, "backtest")
    with c2:
        chart(src, "client_forecast")
        chart(src, "feature_importance")
    table(src.t("forecast", "backtest_metrics"), "Backtest metrics (mean of 3 rolling folds)", expanded=True)
    table(src.t("forecast", "forecast_summary_brand"), "Forecast by brand")
    table(src.t("forecast", "forecast_summary_category"), "Forecast by category")
    st.subheader("Pricing")
    c1, c2 = st.columns(2)
    with c1:
        chart(src, "elasticities")
    with c2:
        chart(src, "price_scenarios")
    el = src.t("forecast", "elasticities")
    fsb = src.t("forecast", "forecast_summary_brand")
    if el is not None and fsb is not None and client in set(el["brand"]):
        st.markdown(f"**Price simulator for {client}** (constant-elasticity demand on the 12-month forecast baseline)")
        e = float(el.set_index("brand").loc[client, "elasticity"])
        base = float(fsb.set_index("brand").loc[client, "revenue_next12"])
        s1, s2 = st.columns(2)
        dp = s1.slider("List-price change (%)", -20, 20, 0, 1)
        margin = s2.slider("Gross margin at current price (%)", 30, 85, 60, 1) / 100
        m = 1 + dp / 100
        vol = m ** e
        m_cols = st.columns(4)
        m_cols[0].metric("Elasticity", f"{e:.2f}")
        m_cols[1].metric("Volume change", f"{(vol - 1) * 100:+.1f}%")
        m_cols[2].metric("Revenue (12m)", fmt_idr(base * m * vol), f"{(m * vol - 1) * 100:+.1f}%")
        m_cols[3].metric("Gross profit change", f"{(((m - (1 - margin)) / margin) * vol - 1) * 100:+.1f}%")

# ---------------------------------------------------------------------------- strategy
with tabs[7], guard("Strategy"):
    swot = run.json("strategy.swot", {}) or {}
    if swot:
        q = st.columns(2)
        for i, (name, items) in enumerate(swot.items()):
            with q[i % 2].container(border=True):
                st.markdown(f"**{name}**")
                for it in items:
                    st.markdown(f"- **{it['title']}** — {it['statement']} `[{it['id']}]`")
    st.subheader("Recommendations")
    for r in run.json("strategy.recommendations", []) or []:
        with st.expander(f"{r['id']}. {r['title']}  ·  {r['horizon']}  ·  priority {r['priority']:.2f}", expanded=r["id"] == "R1"):
            st.markdown(f"**Action.** {r['action']}\n\n**Why.** {r['rationale']}\n\n**KPI.** {r['kpi']}\n\n"
                        f"**Owner / timeline.** {r['owner']} · {r['timeline']} · {r['effort']} effort"
                        + (f"\n\n**Indicative value.** {fmt_idr(r['value_idr'])}" if r.get("value_idr") else "")
                        + f"\n\n**Evidence.** {', '.join(r['evidence'])}")
    chart(src, "opportunities")
    table(run.table("strategy.opportunities"), "Sized opportunities and assumptions")

# ---------------------------------------------------------------------------- report
with tabs[8], guard("Report"):
    html_report = run.text("report.html")
    md_report = run.text("report.md")
    d1, d2, _ = st.columns([1, 1, 3])
    d1.download_button("Download HTML report", html_report, file_name=f"marketmind_{run.run_id}.html", mime="text/html",
                       disabled=not html_report)
    d2.download_button("Download Markdown", md_report, file_name=f"marketmind_{run.run_id}.md", mime="text/markdown",
                       disabled=not md_report)
    if html_report:
        components.html(html_report, height=1150, scrolling=True)
    else:
        st.info("No report in this run.")

# ---------------------------------------------------------------------------- chat
with tabs[9], guard("Ask the analyst"):
    from marketmind.agents.analyst_chat import AnalystChatAgent
    st.caption(f"Answers come only from this run's findings, recommendations and SWOT - via {llm.describe()}.")
    key = f"chat-{run.run_id}"
    history = st.session_state.setdefault(key, [])
    suggestions = ["What is our biggest problem right now?", "Why should we launch the new moisturizer?",
                   "Who is our biggest competitor?", "How price-sensitive are our customers?"]
    picked = st.pills("Try asking", suggestions, selection_mode="single", key=f"pills-{run.run_id}")
    for msg in history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
    question = st.chat_input("Ask the analyst about this study") or (picked if picked and (not history or history[-1].get("q") != picked) else None)
    if question:
        history.append(dict(role="user", content=question, q=question))
        with st.chat_message("user"):
            st.markdown(question)
        agent = AnalystChatAgent(run, llm)
        out = agent.answer(question, history[:-1])
        with st.chat_message("assistant"):
            st.markdown(out["answer"])
            if out["sources"]:
                st.caption("Sources: " + ", ".join(f"{s['id']} ({s['kind']})" for s in out["sources"]) + f" · {out['mode']}")
        history.append(dict(role="assistant", content=out["answer"]))

# ---------------------------------------------------------------------------- evaluation
with tabs[10], guard("Evaluation"):
    st.caption("The data is simulated, so the true market facts are known. This checks how many of them the agents recovered.")
    ev_path = run.path / "evaluation.json"
    if st.button("Evaluate this run against the ground truth", type="primary") or ev_path.exists():
        if not ev_path.exists():
            from marketmind.evaluation import evaluate
            ev_path.write_text(json.dumps(evaluate(run), indent=2, ensure_ascii=False), encoding="utf-8")
        ev = json.loads(ev_path.read_text(encoding="utf-8"))
        c = st.columns(3)
        c[0].metric("Ground-truth checks passed", f"{ev['passed']}/{ev['total']}", border=True)
        c[1].metric("Insight recall", f"{ev['score']:.0%}", border=True)
        c[2].metric("QA score", f"{qa.get('score')}/100", border=True)
        df = pd.DataFrame(ev["checks"])
        df.insert(0, "result", df.pop("passed").map({True: "✅ pass", False: "❌ fail"}))
        st.dataframe(df, width="stretch", hide_index=True, height=min(900, 38 * len(df) + 40))

# ---------------------------------------------------------------------------- data
with tabs[11], guard("Data"):
    st.dataframe(run.table("data.catalog"), width="stretch", hide_index=True)
    st.markdown("**Data quality scorecard**")
    st.dataframe(run.table("dq.scorecard"), width="stretch", hide_index=True)
    name = st.selectbox("Preview a dataset", [k for k in DATASETS])
    f = DATA_RAW / DATASETS[name]["file"]
    if f.exists():
        df = pd.read_csv(f, nrows=2000)
        st.caption(f"{DATASETS[name]['description']} · source: {DATASETS[name]['source']} · showing first {len(df):,} rows")
        st.dataframe(df, width="stretch", hide_index=True, height=360)
    news = run.table("external.news")
    if news is not None and len(news):
        st.markdown("**Latest news headlines (live API)**")
        st.dataframe(news, width="stretch", hide_index=True)
