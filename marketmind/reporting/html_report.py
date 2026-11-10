"""Render the report as a single self-contained HTML file (inline Plotly.js, works offline)."""
from __future__ import annotations

import html as html_lib
import time

from jinja2 import Template
from markdown_it import MarkdownIt
from plotly.offline import get_plotlyjs

from .charts import CHARTS, TableSource

PLOTLY_CONFIG = {"displaylogo": False, "responsive": True,
                 "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines"]}

TEMPLATE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title }}</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--line:#e1e0d9;
--axis:#c3c2b7;--accent:#2a78d6;--good:#0ca30c;--good-text:#006300;--critical:#d03b3b;--ring:rgba(11,11,11,.10)}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
header{background:var(--surface);border-bottom:1px solid var(--line);padding:28px 16px 22px}
.wrap{max-width:1120px;margin:0 auto;padding:0 16px}
header h1{margin:0 0 4px;font-size:28px;line-height:1.2}
header .sub{color:var(--ink2)}
.badges{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.badge{border:1px solid var(--line);border-radius:999px;padding:3px 12px;font-size:13px;color:var(--ink2);background:var(--page)}
.badge.pass{color:var(--good-text);border-color:var(--good)}
.badge.fail{color:var(--critical);border-color:var(--critical)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:22px 0 4px}
.kpi{background:var(--surface);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
.kpi .label{font-size:12.5px;color:var(--muted)}
.kpi .value{font-size:22px;font-weight:600;line-height:1.3}
.kpi .note{font-size:12.5px;color:var(--ink2)}
nav.toc{position:sticky;top:0;z-index:5;background:var(--surface);border-bottom:1px solid var(--line);overflow-x:auto;white-space:nowrap}
nav.toc a{display:inline-block;padding:10px 12px;color:var(--ink2);text-decoration:none;font-size:13.5px}
nav.toc a:hover{color:var(--accent)}
main{padding:12px 0 48px}
section{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:8px 22px 18px;margin:18px 0}
h2{font-size:21px;margin:18px 0 10px}
h3{font-size:17px;margin:20px 0 6px}
p,li{color:var(--ink)}
code{font-size:12px;color:var(--ink2);background:var(--page);border:1px solid var(--line);border-radius:4px;padding:0 4px}
blockquote{margin:12px 0;padding:8px 14px;border-left:3px solid var(--accent);background:var(--page);color:var(--ink2)}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:13.5px;display:block;overflow-x:auto}
th,td{border-bottom:1px solid var(--line);padding:6px 10px;text-align:left;vertical-align:top}
th{color:var(--ink2);font-weight:600;background:var(--page)}
td{font-variant-numeric:tabular-nums}
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,480px),1fr));gap:14px;margin-top:10px}
.chart{border:1px solid var(--line);border-radius:10px;padding:6px;background:var(--surface);min-width:0}
.swot{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:12px}
.swot div{border:1px solid var(--line);border-radius:10px;padding:10px 14px}
.swot h4{margin:2px 0 6px}
.swot ul{margin:0;padding-left:18px}
.qa{border:1px solid var(--line);border-radius:10px;padding:10px 16px}
footer{color:var(--muted);font-size:13px;text-align:center;padding:24px 16px}
@media print{nav.toc{display:none}section{break-inside:avoid;border:none}body{background:#fff}}
</style>
<script>{{ plotlyjs }}</script>
</head>
<body>
<header><div class="wrap">
<h1>{{ title }}</h1>
<div class="sub">Indonesian local facial-skincare market &middot; prepared by the MarketMind multi-agent system &middot; {{ date }}</div>
<div class="badges"><span class="badge">Run {{ run_id }}</span><span class="badge">{{ llm }}</span>
<span class="badge">{{ n_findings }} findings &middot; {{ n_recs }} recommendations</span><!--QA-BADGE--></div>
<div class="kpis">{% for k in kpis %}<div class="kpi"><div class="label">{{ k.label }}</div><div class="value">{{ k.value }}</div>{% if k.note %}<div class="note">{{ k.note }}</div>{% endif %}</div>{% endfor %}</div>
</div></header>
<nav class="toc"><div class="wrap">{% for s in toc %}<a href="#{{ s.key }}">{{ s.title }}</a>{% endfor %}<a href="#qa">QA</a></div></nav>
<main class="wrap">
{{ body }}
<section id="qa"><h2>QA Certificate</h2><!--QA-CERTIFICATE--></section>
</main>
<footer>All data is simulated for demonstration; brands and products are fictional. Generated {{ date }}.</footer>
</body>
</html>""")


def _kpi_tiles(k: dict) -> list[dict]:
    def idr(x):
        if x is None:
            return "n/a"
        return f"Rp {x / 1e12:,.2f} tn" if x >= 1e12 else (f"Rp {x / 1e9:,.0f} bn" if x >= 1e9 else f"Rp {x:,.0f}")

    tiles = []
    if k.get("market_size_idr_bn"):
        tiles.append(dict(label=f"Market size {k.get('market_year')}", value=idr(k["market_size_idr_bn"] * 1e9),
                          note=f"CAGR {k['market_cagr'] * 100:.1f}%" if k.get("market_cagr") else ""))
    if k.get("client_share") is not None:
        tiles.append(dict(label=f"{k['client']} panel share", value=f"{k['client_share'] * 100:.1f}%",
                          note=f"#{k.get('client_rank')} | growth {k['client_growth'] * 100:+.1f}%"))
    if k.get("forecast_client_growth") is not None:
        tiles.append(dict(label="Forecast growth, next 12m", value=f"{k['forecast_client_growth'] * 100:+.1f}%",
                          note=f"market {k['forecast_market_growth'] * 100:+.1f}%"))
    if k.get("top_threat"):
        tiles.append(dict(label="Top threat", value=k["top_threat"], note=""))
    if k.get("target_segment"):
        tiles.append(dict(label="Concept target", value=k["target_segment"],
                          note=f"intent {k['concept_t2b'] * 100:.0f}% | price {idr(k.get('recommended_price_idr'))}"))
    if k.get("elasticity") is not None:
        tiles.append(dict(label="Price elasticity", value=f"{k['elasticity']:.2f}", note="elastic" if k["elasticity"] < -1 else "inelastic"))
    return tiles


def _swot_html(swot: dict) -> str:
    cells = []
    for quadrant, items in swot.items():
        lis = "".join(f"<li><b>{html_lib.escape(i['title'])}.</b> {html_lib.escape(i['statement'])} <code>[{i['id']}]</code></li>"
                      for i in items) or "<li>None identified</li>"
        cells.append(f"<div><h4>{quadrant}</h4><ul>{lis}</ul></div>")
    return f'<div class="swot">{"".join(cells)}</div>'


def render_html(sections: list[dict], bb, title: str, run_id: str) -> str:
    src = TableSource.from_blackboard(bb)
    md = MarkdownIt("commonmark", {"html": True}).enable("table")
    body, toc = [], []
    for s in sections:
        if s["key"] == "title":
            continue
        if s["key"] == "swot" and bb.get("strategy.swot"):
            inner = f"<h2>{html_lib.escape(s['title'])}</h2>" + _swot_html(bb.get("strategy.swot"))
        else:
            inner = md.render(s["markdown"])
        charts = []
        for key in s.get("charts", []):
            fn = CHARTS.get(key)
            fig = fn(src, "light") if fn else None
            if fig is not None:
                charts.append(f'<div class="chart">{fig.to_html(full_html=False, include_plotlyjs=False, config=PLOTLY_CONFIG)}</div>')
        if s["key"] == "opportunities":
            fig = CHARTS["opportunities"](src, "light")
            if fig is not None and not charts:
                charts.append(f'<div class="chart">{fig.to_html(full_html=False, include_plotlyjs=False, config=PLOTLY_CONFIG)}</div>')
        body.append(f'<section id="{s["key"]}">{inner}' + (f'<div class="charts">{"".join(charts)}</div>' if charts else "") + "</section>")
        toc.append(dict(key=s["key"], title=s["title"].split(". ", 1)[-1]))
    llm = bb.get("plan", {}).get("planner", "")
    return TEMPLATE.render(title=title, date=time.strftime("%d %B %Y"), run_id=run_id, plotlyjs=get_plotlyjs(),
                           kpis=_kpi_tiles(bb.get("strategy.kpis") or {}), toc=toc, body="\n".join(body),
                           llm=("LLM-assisted" if "LLM" in llm else "Offline deterministic mode"),
                           n_findings=len(bb.findings()), n_recs=len(bb.get("strategy.recommendations") or []))


def qa_certificate_html(qa: dict) -> str:
    checks = qa.get("checks", {})
    rows = "".join(f"<tr><td>{html_lib.escape(k)}</td><td>{v.get('score', 0) * 100:.0f}%</td></tr>" for k, v in checks.items())
    issues = "".join(f"<li>[{html_lib.escape(i['severity'])}] {html_lib.escape(i['message'])}</li>" for i in qa.get("issues", [])) or "<li>None</li>"
    verdict = "PASSED" if qa.get("passed") else "NOT PASSED"
    return (f'<div class="qa"><p><b>Verdict: {verdict}</b> - score {qa.get("score")}/100 after {qa.get("revision", 0)} '
            f'revision(s); {qa.get("numbers_grounded")}/{qa.get("numbers_checked")} numbers in the prose were traced to '
            f'evidence produced by the analysis agents.</p><table><tr><th>Check</th><th>Score</th></tr>{rows}</table>'
            f'<p><b>Open issues</b></p><ul>{issues}</ul></div>')
