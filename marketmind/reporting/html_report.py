"""Render the report as a single self-contained HTML file (inline Plotly.js and typeface, works offline).

It follows the web app's design (frontend/src/styles/main.css): a mineral page with jade ink, one typeface (Archivo,
whose width axis sets the titles), the Critic agent's verdict as a seal, the headline figures as one ruled panel, and
evidence IDs as stamps. The text itself comes from the report's Markdown, which the Critic checks; this module only
presents it."""
from __future__ import annotations

import base64
import html as html_lib
import re
import time
from functools import lru_cache
from pathlib import Path

from jinja2 import Template
from markdown_it import MarkdownIt
from plotly.offline import get_plotlyjs

from .charts import CHARTS, TableSource

PLOTLY_CONFIG = {"displaylogo": False, "responsive": True,
                 "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines"]}

ASSETS = Path(__file__).with_name("assets")
FONT_STACK = "Archivo, system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif"
# the Latin subset, as @fontsource-variable/archivo ships it
LATIN_RANGE = ("U+0000-00FF,U+0131,U+0152-0153,U+02BB-02BC,U+02C6,U+02DA,U+02DC,U+0304,U+0308,U+0329,U+2000-206F,U+20AC,"
               "U+2122,U+2191,U+2193,U+2212,U+2215,U+FEFF,U+FFFD")
SWOT_KEYS = {"Strengths": "S", "Weaknesses": "W", "Opportunities": "O", "Threats": "T"}

EVIDENCE_ID = r"[A-Z]{2,4}-\d{1,3}"
CITED_IN_CODE = re.compile(rf"<code>\[({EVIDENCE_ID}(?:\s*[,;]\s*{EVIDENCE_ID})*)\]</code>")
CITED = re.compile(rf"\[({EVIDENCE_ID}(?:\s*[,;]\s*{EVIDENCE_ID})*)\]")
SECTION_NUMBER = re.compile(r"<h2>(\d+)\.\s+")
RECOMMENDATION_ID = re.compile(r"<h3>(R\d+)\.\s+")
APPENDIX_LETTER = re.compile(r"<h3>([A-Z])\.\s+")
# an amount stays on one line: never "Rp" at the end of one line and its figure on the next
RUPIAH = re.compile(r"\bRp (?=\d)")
MAGNITUDE = re.compile(r"(?<=\d) (?=(?:bn|tn|million|billion|trillion)\b)")

SEAL_SVG = ('<svg viewBox="0 0 100 100" aria-hidden="true"><circle class="face" cx="50" cy="50" r="41"/>'
            '<circle class="teeth" cx="50" cy="50" r="46.5" pathLength="360"/>'
            '<circle class="ring" cx="50" cy="50" r="40"/></svg>')

TEMPLATE = Template("""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ title|e }}</title>
<style>
{{ font_face }}
:root{color-scheme:light;--bg:#f2f4f3;--panel:#fff;--panel-2:#f6f8f7;--border:#d6dedb;--border-strong:#b4c1bc;
--text:#102320;--text-2:#3c504b;--muted:#5e716c;--accent:#0b6e5f;--accent-soft:rgba(11,110,95,.09);
--good:#1f7a3a;--good-soft:rgba(31,122,58,.11);--bad:#b42335;--bad-soft:rgba(180,35,53,.1);--warn:#8a5a00;
--warn-soft:rgba(214,150,20,.16);--idle-soft:rgba(94,113,108,.14);--radius:10px;--radius-sm:6px;
--font:{{ font_stack }}}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.6 var(--font);-webkit-font-smoothing:antialiased}
.wrap{max-width:1120px;margin:0 auto;padding:0 32px}
a{color:var(--accent)}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
h1,h2,h3,h4{color:var(--text);line-height:1.2;font-weight:650;font-stretch:108%;letter-spacing:-.01em}
strong,b{font-weight:640}

/* the cover: the client, what the study is, the Critic agent's seal, the run's facts, the headline figures */
.cover{padding:36px 0 26px}
.cover-grid{display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-areas:"title seal" "lede seal" "facts facts";
column-gap:32px;align-items:start}
.cover h1{grid-area:title;margin:0;font-size:clamp(30px,4.2vw,44px);font-weight:740;font-stretch:122%;letter-spacing:-.024em;
line-height:1.06;overflow-wrap:anywhere}
.lede{grid-area:lede;margin:10px 0 0;max-width:62ch;color:var(--text-2);font-size:16px;line-height:1.5}
.cover .seal{grid-area:seal;align-self:center}
.facts{grid-area:facts;display:flex;flex-wrap:wrap;gap:10px 36px;margin:22px 0 0;padding:13px 0 0;border-top:1px solid var(--border)}
.facts div{min-width:0}
.facts dt{font-size:12px;color:var(--muted)}
.facts dd{margin:1px 0 0;font-size:13.5px;font-weight:560;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}

/* the headline figures: one panel ruled into cells, in rows of even length */
.kpis{--cols:3;display:grid;grid-template-columns:repeat(var(--cols),minmax(0,1fr));margin-top:22px;background:var(--panel);
border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
.kpis[data-cols="1"]{--cols:1}.kpis[data-cols="2"]{--cols:2}.kpis[data-cols="4"]{--cols:4}.kpis[data-cols="5"]{--cols:5}
.kpi{min-width:0;padding:14px 18px 15px;box-shadow:-1px 0 0 var(--border),0 -1px 0 var(--border)}
.kpi .label{font-size:12px;color:var(--muted)}
.kpi .value{margin:4px 0 2px;font-size:21px;font-weight:680;font-stretch:104%;letter-spacing:-.01em;line-height:1.25;
font-variant-numeric:tabular-nums lining-nums;overflow-wrap:anywhere}
.kpi .note{font-size:12px;color:var(--text-2)}

/* the contents: one row that scrolls sideways, the section in view marked */
nav.toc{position:sticky;top:0;z-index:5;background:var(--bg);background:color-mix(in srgb,var(--bg) 94%,transparent);
backdrop-filter:blur(8px);border-top:1px solid var(--border);border-bottom:1px solid var(--border)}
nav.toc .wrap{display:flex;overflow-x:auto;scrollbar-width:none;padding:0 22px;
-webkit-mask-image:linear-gradient(to right,transparent 0,#000 16px,#000 calc(100% - 28px),transparent 100%);
mask-image:linear-gradient(to right,transparent 0,#000 16px,#000 calc(100% - 28px),transparent 100%)}
nav.toc .wrap::-webkit-scrollbar{display:none}
nav.toc a{flex:none;display:inline-flex;align-items:center;min-height:44px;padding:0 10px;margin-bottom:-1px;color:var(--text-2);
text-decoration:none;white-space:nowrap;font-size:13.5px;font-weight:560;font-stretch:97%;border-bottom:2px solid transparent}
nav.toc a:hover{color:var(--text)}
nav.toc a[aria-current]{color:var(--accent);border-bottom-color:var(--accent);font-weight:650}

/* the sections: sheets of paper with a rule, each numbered in jade */
main{padding:22px 0 40px}
section{margin:0 0 20px;padding:10px 36px 26px;background:var(--panel);border:1px solid var(--border);border-radius:var(--radius);
scroll-margin-top:60px}
section h2{display:flex;align-items:baseline;gap:12px;margin:22px 0 12px;font-size:23px;font-weight:700;font-stretch:112%;
letter-spacing:-.016em}
.sec-num{color:var(--accent);font-stretch:100%;font-variant-numeric:tabular-nums}
section h3{display:flex;align-items:baseline;gap:9px;margin:26px 0 8px;font-size:17px}
section h4{margin:16px 0 6px;font-size:15px}
p,li{max-width:78ch}
ul,ol{padding-left:20px}
li{margin:4px 0}
code{padding:0 4px;font:12.5px/1.4 ui-monospace,"Cascadia Mono",Consolas,monospace;background:var(--panel-2);
border:1px solid var(--border);border-radius:5px}
blockquote{max-width:82ch;margin:14px 0;padding:10px 16px;color:var(--text-2);background:var(--panel-2);
border-left:3px solid var(--accent);border-radius:0 var(--radius-sm) var(--radius-sm) 0}
blockquote p{margin:4px 0}
/* an evidence ID, the same stamp as in the web app */
.stamp{display:inline-flex;align-items:center;padding:0 6px;font-size:11.5px;font-weight:650;font-stretch:92%;letter-spacing:.02em;
line-height:1.6;font-variant-numeric:tabular-nums;white-space:nowrap;text-indent:0;vertical-align:1px;color:var(--accent);
background:var(--accent-soft);border-radius:var(--radius-sm)}
.stamp.swot-S{color:var(--good);background:var(--good-soft)}
.stamp.swot-W{color:var(--bad);background:var(--bad-soft)}
.stamp.swot-T{color:var(--warn);background:var(--warn-soft)}
/* a wide table scrolls inside its sheet instead of widening the page */
table{display:block;overflow-x:auto;width:100%;margin:14px 0;border-collapse:collapse;font-size:13.5px}
th,td{padding:7px 12px;text-align:left;vertical-align:top;border-bottom:1px solid var(--border)}
th{color:var(--text-2);font-weight:600;font-stretch:96%;white-space:nowrap;background:var(--panel-2)}
td{font-variant-numeric:tabular-nums}
/* a recommendation's details: each label in a column of its own, the text hanging beside it */
#recommendations h3+ul{list-style:none;padding:0}
#recommendations h3+ul li{max-width:none;padding-left:10.5rem;text-indent:-10.5rem}
#recommendations h3+ul li>strong:first-child{display:inline-block;width:10.5rem;text-indent:0;color:var(--text-2);font-weight:600}
.charts{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,460px),1fr));gap:16px;margin-top:16px}
.chart{min-width:0;padding:8px;border:1px solid var(--border);border-radius:var(--radius)}
/* SWOT: four ledgers, each keyed by the colour its stamps carry */
.swot{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,420px),1fr));gap:16px}
.quad{padding:14px 18px 8px;border:1px solid var(--border);border-radius:var(--radius)}
.quad h4{display:flex;align-items:center;gap:9px;margin:0 0 6px;font-size:15.5px}
.quad h4 i{width:10px;height:10px;border-radius:3px;background:var(--border-strong)}
.q-S h4 i{background:var(--good)}.q-W h4 i{background:var(--bad)}.q-O h4 i{background:var(--accent)}.q-T h4 i{background:var(--warn)}
.entry{display:grid;grid-template-columns:3.9rem minmax(0,1fr);align-content:start;column-gap:12px;padding:10px 0;
border-top:1px solid var(--border)}
.quad h4+.entry{padding-top:4px;border-top:0}
.entry .stamp{grid-row:1/span 2;align-self:start;justify-content:center;margin-top:3px}
.entry b{font-stretch:104%}
.entry p{margin:2px 0 0;color:var(--text-2);font-size:14px}
/* the QA certificate */
.qa-head{display:flex;align-items:center;gap:22px;margin:8px 0 6px}
.qa-head p{margin:0}
.checks td:last-child{white-space:nowrap}
.meter{display:inline-block;width:96px;height:6px;margin-right:10px;overflow:hidden;vertical-align:middle;border-radius:3px;
background:var(--panel-2);box-shadow:inset 0 0 0 1px var(--border)}
.meter i{display:block;height:100%;background:var(--accent)}
.sev{margin-right:8px;padding:0 6px;font-size:11.5px;font-weight:650;border-radius:var(--radius-sm)}
.sev.critical{color:var(--bad);background:var(--bad-soft)}.sev.major{color:var(--warn);background:var(--warn-soft)}
/* the seal: the Critic agent's verdict (the web app's QaSeal) */
.seal{--seal:var(--accent);--seal-soft:var(--accent-soft);position:relative;flex:none;width:112px;height:112px;color:var(--seal)}
.seal.warn{--seal:var(--warn);--seal-soft:var(--warn-soft)}
.seal.idle{--seal:var(--muted);--seal-soft:var(--idle-soft)}
.seal svg{position:absolute;inset:0;width:100%;height:100%}
.seal .face{fill:var(--seal-soft)}
.seal .teeth{fill:none;stroke:currentColor;stroke-width:4.5;stroke-dasharray:2.1 2.4}
.seal.idle .teeth{stroke-dasharray:1 3.5}
.seal .ring{fill:none;stroke:currentColor;stroke-width:.9;opacity:.55}
.seal-body{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;
text-align:center;line-height:1.05}
.seal-body small{font-size:12px;font-weight:600;color:var(--text-2)}
.seal-body strong{margin:1px 0 2px;font-size:33px;font-weight:760;font-stretch:86%;letter-spacing:-.02em;line-height:1;
font-variant-numeric:tabular-nums lining-nums}
.seal-body strong.word{margin:3px 0 4px;font-size:16px;font-stretch:100%;letter-spacing:0}
footer{padding:4px 16px 32px;color:var(--muted);font-size:13px;text-align:center}
@media (max-width:1000px){.kpis[data-cols="5"]{--cols:3}.kpis[data-cols="4"]{--cols:2}}
@media (max-width:720px){
body{font-size:14.5px}
.wrap{padding:0 16px}
.cover{padding:22px 0 18px}
.cover-grid{grid-template-areas:"title seal" "lede lede" "facts facts";column-gap:16px}
.cover h1{align-self:center}
.lede{margin-top:12px;font-size:14.5px}
.facts{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px 16px}
.kpis:not([data-cols="1"]){--cols:2}
.kpis:not([data-cols="1"]) .kpi:last-child:nth-child(odd){grid-column:1/-1}
.kpi{padding:11px 13px}
.kpi .value{font-size:17px}
nav.toc .wrap{padding:0 8px}
section{padding:4px 16px 18px}
section h2{font-size:19px}
.seal{width:88px;height:88px}
.seal-body small{font-size:10.5px}
.seal-body strong{font-size:26px}
.seal-body strong.word{font-size:13px}
#recommendations h3+ul li{padding-left:0;text-indent:0}
#recommendations h3+ul li>strong:first-child{display:block;width:auto}
.entry{grid-template-columns:auto minmax(0,1fr)}
.entry .stamp{grid-row:auto}
.entry p{grid-column:1/-1}
th,td{min-width:8.5rem}
th:first-child,td:first-child{min-width:3.5rem}
.qa-head{flex-direction:column;align-items:flex-start;gap:12px}
}
@media print{
body{background:#fff;font-size:12.5px}
nav.toc{display:none}
section{margin:0 0 18px;padding:0;border:0}
.chart,table,.quad,blockquote,.kpis{break-inside:avoid}
.seal,.stamp,.kpis,.meter,.sev{-webkit-print-color-adjust:exact;print-color-adjust:exact}
}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
</style>
<script>{{ plotlyjs }}</script>
</head>
<body>
<header class="cover"><div class="wrap">
<div class="cover-grid">
<h1>{{ client|e }}</h1>
<p class="lede">A market research report on Indonesia's local facial-skincare market, prepared by the MarketMind agent team on {{ date }}.</p>
<!--QA-SEAL-->
<dl class="facts">
<div><dt>Run</dt><dd>{{ run_id|e }}</dd></div>
<div><dt>Language model</dt><dd>{{ llm|e }}</dd></div>
<div><dt>Output</dt><dd>{{ n_findings }} finding{{ '' if n_findings == 1 else 's' }}, {{ n_recs }} recommendation{{ '' if n_recs == 1 else 's' }}</dd></div>
<div><dt>Data</dt><dd>{{ data_kind|e }}</dd></div>
</dl>
</div>
{% if kpis %}<div class="kpis" data-cols="{{ cols }}">{% for k in kpis %}<div class="kpi"><div class="label">{{ k.label|e }}</div><div class="value">{{ k.value|e }}</div>{% if k.note %}<div class="note">{{ k.note|e }}</div>{% endif %}</div>{% endfor %}</div>{% endif %}
</div></header>
<nav class="toc" aria-label="Contents"><div class="wrap">{% for s in toc %}<a href="#{{ s.key }}">{{ s.title|e }}</a>{% endfor %}<a href="#qa">QA certificate</a></div></nav>
<main class="wrap">
{{ body }}
<section id="qa"><h2>QA Certificate</h2><!--QA-CERTIFICATE--></section>
</main>
<footer>{{ data_note|e }} Generated {{ date }}.</footer>
<script>
(() => {
  // mark the section in view in the contents, and keep its link in sight where the row scrolls
  const row = document.querySelector('nav.toc .wrap');
  const links = new Map([...row.querySelectorAll('a')].map((a) => [a.hash.slice(1), a]));
  if ('IntersectionObserver' in window) {
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) {
        const a = links.get(e.target.id);
        if (!e.isIntersecting || !a) continue;
        links.forEach((l) => l.removeAttribute('aria-current'));
        a.setAttribute('aria-current', 'location');
        row.scrollLeft = a.offsetLeft - (row.clientWidth - a.offsetWidth) / 2;
      }
    }, { rootMargin: '-40% 0px -55% 0px' });
    document.querySelectorAll('main section[id]').forEach((s) => io.observe(s));
  }
  // the charts measured their labels before the typeface was ready: draw them again in it
  if (document.fonts && window.Plotly) {
    document.fonts.ready.then(() => {
      document.querySelectorAll('.js-plotly-plot').forEach((el) => Plotly.newPlot(el, el.data, el.layout, el._context));
    });
  }
})();
</script>
</body>
</html>""")


@lru_cache(maxsize=1)
def _font_face() -> str:
    """Archivo, a variable font (weight 100-900, width 62-125%) under the SIL Open Font License (assets/OFL-Archivo.txt),
    inlined so the report keeps its typeface offline. Without the file, the report falls back to the system font."""
    font = ASSETS / "archivo-latin-wdth-normal.woff2"
    if not font.is_file():
        return ""
    data = base64.b64encode(font.read_bytes()).decode("ascii")
    return ("@font-face{font-family:Archivo;font-style:normal;font-display:swap;font-weight:100 900;font-stretch:62% 125%;"
            f"src:url(data:font/woff2;base64,{data}) format('woff2');unicode-range:{LATIN_RANGE}}}")


def _e(text) -> str:
    return html_lib.escape(str(text))


def _idr(x) -> str:
    """Rupiah, as the web app writes it: "Rp 38.30 tn", "Rp 74.5 bn", smaller amounts in full."""
    if x is None:
        return "n/a"
    if abs(x) >= 1e12:
        return f"Rp {x / 1e12:,.2f} tn"
    return f"Rp {x / 1e9:,.1f} bn" if abs(x) >= 1e9 else f"Rp {x:,.0f}"


def _pct(x, sign: bool = True) -> str:
    if x is None:
        return "n/a"
    return f"{x * 100:+.1f}%" if sign else f"{x * 100:.1f}%"


def _kpi_tiles(k: dict, horizon: int) -> list[dict]:
    """The headline figures the study produced, the same tiles as the web app's Overview (a skipped module leaves none)."""
    tiles = []
    if k.get("market_size_idr_bn"):
        tiles.append(dict(label=f"Market size {k.get('market_year') or ''}".strip(), value=_idr(k["market_size_idr_bn"] * 1e9),
                          note=f"CAGR {_pct(k['market_cagr'], False)}" if k.get("market_cagr") is not None else ""))
    if k.get("client_share") is not None:
        rank = f" (#{k['client_rank']})" if k.get("client_rank") else ""
        note = f"growth {_pct(k.get('client_growth'))}" if k.get("client_growth") is not None else ""
        if note and k.get("panel_growth") is not None:
            note += f" vs panel {_pct(k['panel_growth'])}"
        tiles.append(dict(label=f"{k.get('client') or 'Client'} panel share", value=_pct(k["client_share"], False) + rank, note=note))
    if k.get("forecast_client_growth") is not None:
        tiles.append(dict(label=f"Forecast growth, next {horizon} months", value=_pct(k["forecast_client_growth"]),
                          note=f"market {_pct(k['forecast_market_growth'])}" if k.get("forecast_market_growth") is not None else ""))
    if k.get("top_threat"):
        tiles.append(dict(label="Top competitive threat", value=k["top_threat"],
                          note=f"weakest channel: {k['weakest_channel']}" if k.get("weakest_channel") else ""))
    if k.get("target_segment"):
        tiles.append(dict(label="Concept target segment", value=k["target_segment"],
                          note=f"purchase intent {_pct(k['concept_t2b'], False)}" if k.get("concept_t2b") is not None else ""))
    if k.get("recommended_price_idr"):
        tiles.append(dict(label="Recommended launch price", value=_idr(k["recommended_price_idr"]),
                          note=f"elasticity {k['elasticity']:.2f}" if k.get("elasticity") is not None else ""))
    elif k.get("elasticity") is not None:
        tiles.append(dict(label="Price elasticity", value=f"{k['elasticity']:.2f}", note="elastic" if k["elasticity"] < -1 else "inelastic"))
    return tiles


def _columns(n: int) -> int:
    # rows of even length: six tiles sit three by two, never five and a stray
    return n if n <= 5 else 3 if n in (6, 9) else 4


def _swot_html(swot: dict) -> str:
    cells = []
    for quadrant, items in swot.items():
        q = SWOT_KEYS.get(quadrant, "x")
        entries = "".join(f'<div class="entry"><span class="stamp swot-{q}">{_e(i["id"])}</span><b>{_e(i["title"])}</b>'
                          f'<p>{_e(i["statement"])}</p></div>' for i in items) or "<p>None identified.</p>"
        cells.append(f'<div class="quad q-{q}"><h4><i aria-hidden="true"></i>{_e(quadrant)}</h4>{entries}</div>')
    return f'<div class="swot">{"".join(cells)}</div>'


def _stamps(ids: str) -> str:
    return " ".join(f'<span class="stamp">{i}</span>' for i in re.split(r"\s*[,;]\s*", ids))


def _present(html: str) -> str:
    """Typeset the rendered Markdown: section numbers in jade, recommendation IDs and cited evidence IDs as stamps,
    amounts kept on one line. The words do not change."""
    html = CITED_IN_CODE.sub(lambda m: _stamps(m.group(1)), html)
    html = CITED.sub(lambda m: _stamps(m.group(1)), html)
    html = MAGNITUDE.sub("&nbsp;", RUPIAH.sub("Rp&nbsp;", html))
    html = SECTION_NUMBER.sub(r'<h2><span class="sec-num">\1</span>', html)
    html = RECOMMENDATION_ID.sub(r'<h3><span class="stamp">\1</span>', html)
    return APPENDIX_LETTER.sub(r'<h3><span class="sec-num">\1</span>', html)


def _chart(fig) -> str:
    fig.update_layout(font_family=FONT_STACK, hoverlabel_font_family=FONT_STACK)
    return f'<div class="chart">{fig.to_html(full_html=False, include_plotlyjs=False, config=PLOTLY_CONFIG)}</div>'


def render_html(sections: list[dict], bb, title: str, run_id: str, llm: str | None = None) -> str:
    """`llm` names the language model the run used ("groq / model"), an empty string when it used none, or None to
    infer it from the plan."""
    src = TableSource.from_blackboard(bb)
    md = MarkdownIt("commonmark", {"html": True}).enable("table")
    body, toc = [], []
    for s in sections:
        if s["key"] == "title":
            continue
        if s["key"] == "swot" and bb.get("strategy.swot"):
            inner = f"<h2>{_e(s['title'])}</h2>" + _swot_html(bb.get("strategy.swot"))
        else:
            inner = md.render(s["markdown"])
        charts = []
        for key in s.get("charts", []):
            fn = CHARTS.get(key)
            fig = fn(src, "light") if fn else None
            if fig is not None:
                charts.append(_chart(fig))
        if s["key"] == "opportunities":
            fig = CHARTS["opportunities"](src, "light")
            if fig is not None and not charts:
                charts.append(_chart(fig))
        body.append(f'<section id="{s["key"]}">{_present(inner)}' + (f'<div class="charts">{"".join(charts)}</div>' if charts else "")
                    + "</section>")
        toc.append(dict(key=s["key"], title=s["title"].split(". ", 1)[-1]))
    plan = bb.get("plan", {}) or {}
    data = plan.get("data") or {}
    real = data.get("kind") == "real"
    data_note = (f"Data: real marketplace data from {data.get('source', 'a third-party source')}; see Methodology and "
                 "Limitations for its caveats." if real else
                 "All data is simulated for demonstration; brands and products are fictional.")
    kpis = bb.get("strategy.kpis") or {}
    tiles = _kpi_tiles(kpis, int(kpis.get("horizon_months") or plan.get("horizon_months") or 12))
    client = plan.get("client") or kpis.get("client") or title.split(" - ")[0]
    return TEMPLATE.render(title=title, client=client, date=time.strftime("%d %B %Y").lstrip("0"), run_id=run_id,
                           plotlyjs=get_plotlyjs(), font_face=_font_face(), font_stack=FONT_STACK, data_note=data_note,
                           data_kind=(f"Real, from {data.get('source', 'a third-party source')}" if real
                                      else "Simulated; brands and products are fictional"),
                           kpis=tiles, cols=_columns(len(tiles)), toc=toc, body="\n".join(body),
                           llm=llm or ("Off, a deterministic run" if llm == "" or "LLM" not in plan.get("planner", "")
                                       else "Used for the plan and the writing"),
                           n_findings=len(bb.findings()), n_recs=len(bb.get("strategy.recommendations") or []))


def qa_seal_html(qa: dict | None) -> str:
    """The Critic agent's verdict as a seal for the cover and the certificate: its score when it checked the report,
    else that QA did not run. Words sit inside the seal, so its colour is never the only signal."""
    if not qa:
        cls, top, big, bottom, word = "idle", "QA", "Not run", "unverified", True
        label = "QA not run: the Critic agent did not complete, so this report is unverified."
    else:
        passed = bool(qa.get("passed"))
        score = qa.get("score")
        big = f"{float(score):.0f}" if isinstance(score, (int, float)) else "?"
        cls, top, bottom, word = ("good" if passed else "warn"), "QA", ("passed" if passed else "not passed"), False
        label = f"QA {'passed' if passed else 'not passed'}: the Critic agent scored this report {big} out of 100."
    strong = '<strong class="word">' if word else "<strong>"
    return (f'<div class="seal {cls}" role="img" aria-label="{_e(label)}" title="{_e(label)}">{SEAL_SVG}'
            f'<span class="seal-body" aria-hidden="true"><small>{top}</small>{strong}{big}</strong><small>{bottom}</small></span></div>')


def qa_not_verified_html() -> str:
    return (f'<div class="qa"><div class="qa-head">{qa_seal_html(None)}<p><strong>Not verified.</strong> The Critic agent did '
            'not complete, so the numbers, citations and coverage of this report were not checked. The run trace records the '
            'error.</p></div></div>')


def qa_certificate_html(qa: dict) -> str:
    rows = []
    for name, check in qa.get("checks", {}).items():
        pct = max(0.0, min(100.0, float(check.get("score", 0) or 0) * 100))
        rows.append(f'<tr><td>{_e(name.capitalize())}</td><td><span class="meter" aria-hidden="true"><i style="width:{pct:.0f}%">'
                    f'</i></span>{pct:.0f}%</td></tr>')
    issues = "".join(f'<li><span class="sev {_e(i["severity"])}">{_e(i["severity"])}</span>{_e(i["message"])}</li>'
                     for i in qa.get("issues", [])) or "<li>None.</li>"
    passed = bool(qa.get("passed"))
    score = qa.get("score")
    scored = f"{float(score):.0f}" if isinstance(score, (int, float)) else "?"
    revision = int(qa.get("revision", 0) or 0)
    when = "on its first draft" if revision == 0 else f"after {revision} revision{'' if revision == 1 else 's'}"
    traced = ""
    if qa.get("numbers_checked") is not None:
        traced = (f" {qa.get('numbers_grounded')} of {qa.get('numbers_checked')} numbers in the prose were traced to evidence "
                  "produced by the analysis agents.")
    return (f'<div class="qa"><div class="qa-head">{qa_seal_html(qa)}<p><strong>{"Passed" if passed else "Not passed"}.</strong> '
            f'The Critic agent scored this report {scored} out of 100 {when}.{traced}</p></div>'
            f'<table class="checks"><tr><th>Check</th><th>Score</th></tr>{"".join(rows)}</table>'
            f'<h4>Open issues</h4><ul class="issues">{issues}</ul></div>')
