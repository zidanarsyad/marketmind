#!/usr/bin/env python
"""Collect every Mermaid diagram in the documentation into one browsable page with SVG/PNG export.

    python scripts/build_diagram_gallery.py          # writes docs/diagrams/gallery.html

The page renders the diagrams in the browser with mermaid.js (pinned version, loaded from a CDN), so it
needs an internet connection the first time it is opened. Re-run this script after editing a diagram.
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]
OUT = ROOT / "docs" / "diagrams" / "gallery.html"
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "diagram"


def extract(path: Path) -> list[dict]:
    """Mermaid blocks of one Markdown file, titled by the nearest heading and the bold lead-in above them."""
    out, heading, lead, block, start, in_code = [], path.stem, "", None, 0, False
    for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if block is not None:
            if stripped == "```":
                out.append(dict(heading=heading, lead=lead, line=start, code="\n".join(block)))
                block, lead = None, ""
            else:
                block.append(line)
            continue
        if stripped.startswith("```"):
            if stripped == "```mermaid" and not in_code:
                block, start = [], no
            else:
                in_code = not in_code
            continue
        if in_code:
            continue
        if stripped.startswith("#"):
            heading, lead = stripped.lstrip("#").strip(), ""
        elif stripped:
            m = re.match(r"\*\*(.+?)\*\*", stripped)
            lead = m.group(1).rstrip(".:") if m else ""
    return out


def collect() -> list[dict]:
    diagrams = []
    for path in SOURCES:
        seen: dict[str, int] = {}
        for d in extract(path):
            title = d["lead"] or re.sub(r"^\d+(\.\d+)*\.?\s*", "", d["heading"])
            seen[title] = seen.get(title, 0) + 1
            if seen[title] > 1:
                title = f"{title} ({seen[title]})"
            kind = d["code"].split(None, 1)[0] if d["code"].strip() else "diagram"
            diagrams.append(dict(id=len(diagrams) + 1, doc=path.relative_to(ROOT).as_posix(), line=d["line"],
                                 title=title, section=d["heading"], kind=kind, code=d["code"],
                                 slug=f"{len(diagrams) + 1:02d}-{slugify(title)}"))
    return diagrams


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MarketMind Diagrams</title>
<style>
:root{--bg:#fcfcfb;--surface:#ffffff;--text:#0b0b0b;--text2:#52514e;--muted:#7a7974;--border:#e4e3dd;
--accent:#2a78d6;--accent-soft:#e8f1fc;--error:#c43131;--error-soft:#fbeaea;--code:#f3f2ee}
@media (prefers-color-scheme:dark){:root{--bg:#121211;--surface:#1b1b1a;--text:#f2f2ef;--text2:#c3c2b7;
--muted:#9a998f;--border:#2f2f2c;--accent:#6aa9f4;--accent-soft:#1c2a3b;--error:#ff7b7b;--error-soft:#3a1f1f;--code:#232321}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:32px 16px 64px}
h1{font-size:26px;margin:0 0 4px;letter-spacing:-.01em}
.sub{color:var(--text2);margin:0 0 20px}
.status{display:inline-block;padding:4px 10px;border:1px solid var(--border);border-radius:999px;font-size:13px;color:var(--text2);background:var(--surface)}
.status.bad{color:var(--error);border-color:var(--error);background:var(--error-soft)}
nav{margin:24px 0 8px;display:grid;gap:14px}
nav h2{font-size:13px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:0 0 6px}
nav ul{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:6px}
nav a{display:block;padding:4px 10px;border:1px solid var(--border);border-radius:999px;color:var(--text);text-decoration:none;font-size:13px;background:var(--surface)}
nav a:hover{border-color:var(--accent);color:var(--accent)}
section.card{background:var(--surface);border:1px solid var(--border);border-radius:12px;margin:22px 0;overflow:hidden}
section.card.error{border-color:var(--error)}
.head{display:flex;flex-wrap:wrap;align-items:center;gap:8px 16px;padding:14px 18px;border-bottom:1px solid var(--border)}
.head h3{margin:0;font-size:17px;flex:1 1 260px}
.meta{color:var(--muted);font-size:12.5px;width:100%;order:3}
.meta code{background:var(--code);padding:1px 5px;border-radius:4px}
.actions{display:flex;gap:6px}
button{font:inherit;font-size:13px;padding:5px 11px;border-radius:7px;border:1px solid var(--border);background:var(--surface);color:var(--text);cursor:pointer}
button:hover{border-color:var(--accent);color:var(--accent)}
button:disabled{opacity:.45;cursor:default}
.canvas{padding:18px;overflow-x:auto;text-align:center;min-height:80px}
.canvas svg{max-width:100%;height:auto}
.canvas.wide svg{max-width:none}
.err{color:var(--error);background:var(--error-soft);text-align:left;padding:12px 14px;border-radius:8px;white-space:pre-wrap;font:12.5px/1.5 ui-monospace,Consolas,monospace}
details{border-top:1px solid var(--border)}
summary{cursor:pointer;padding:10px 18px;color:var(--text2);font-size:13px}
pre{margin:0;padding:12px 18px 18px;overflow-x:auto;background:var(--code);font:12.5px/1.5 ui-monospace,Consolas,monospace;color:var(--text)}
footer{color:var(--muted);font-size:12.5px;margin-top:32px}
</style>
</head>
<body>
<div class="wrap">
  <h1>MarketMind diagrams</h1>
  <p class="sub">Every Mermaid diagram in the MarketMind documentation, rendered in one place. Use <b>SVG</b> or <b>PNG</b> to export a diagram for slides or reports, and <b>Wide</b> to see a large diagram at full size.</p>
  <span class="status" id="status">Rendering __COUNT__ diagrams ...</span>
  <nav id="toc"></nav>
  <main id="gallery"></main>
  <footer>Generated __GENERATED__ by <code>scripts/build_diagram_gallery.py</code> from the Markdown sources. Rendered with mermaid __MERMAID_VERSION__.</footer>
</div>
<script id="diagram-data" type="application/json">__DATA__</script>
<script type="module">
import mermaid from "__MERMAID__";

const diagrams = JSON.parse(document.getElementById("diagram-data").textContent);
const gallery = document.getElementById("gallery");
const toc = document.getElementById("toc");
const status = document.getElementById("status");
const dark = window.matchMedia("(prefers-color-scheme: dark)");

function el(tag, attrs = {}, text) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  if (text !== undefined) node.textContent = text;
  return node;
}

// table of contents, grouped by source document
const byDoc = new Map();
for (const d of diagrams) (byDoc.get(d.doc) || byDoc.set(d.doc, []).get(d.doc)).push(d);
for (const [doc, items] of byDoc) {
  const group = el("div");
  group.append(el("h2", {}, doc));
  const ul = el("ul");
  for (const d of items) {
    const li = el("li");
    li.append(el("a", { href: "#" + d.slug }, d.title));
    ul.append(li);
  }
  group.append(ul);
  toc.append(group);
}

// one card per diagram
for (const d of diagrams) {
  const card = el("section", { class: "card", id: d.slug });
  const head = el("div", { class: "head" });
  head.append(el("h3", {}, d.id + ". " + d.title));
  const actions = el("div", { class: "actions" });
  for (const [label, fn] of [["SVG", downloadSvg], ["PNG", downloadPng], ["Wide", toggleWide], ["Copy source", copySource]]) {
    const b = el("button", { type: "button" }, label);
    b.addEventListener("click", () => fn(d, card, b));
    actions.append(b);
  }
  head.append(actions);
  const meta = el("div", { class: "meta" });
  meta.append(document.createTextNode(d.kind + " · from "));
  meta.append(el("code", {}, d.doc + ":" + d.line));
  meta.append(document.createTextNode(" · section " + d.section));
  head.append(meta);
  card.append(head, el("div", { class: "canvas" }));
  const details = el("details");
  details.append(el("summary", {}, "Mermaid source"), el("pre", {}, d.code));
  card.append(details);
  gallery.append(card);
}

async function renderAll() {
  mermaid.initialize({
    startOnLoad: false, securityLevel: "strict", theme: dark.matches ? "dark" : "default",
    fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif', htmlLabels: false,
    flowchart: { htmlLabels: false, useMaxWidth: false, curve: "basis" },
    sequence: { useMaxWidth: false }, class: { useMaxWidth: false }, state: { useMaxWidth: false },
    er: { useMaxWidth: false },
  });
  let failed = 0;
  for (const d of diagrams) {
    const card = document.getElementById(d.slug);
    const canvas = card.querySelector(".canvas");
    card.classList.remove("error");
    try {
      const { svg } = await mermaid.render("mmd-" + d.id + "-" + Date.now(), d.code);
      canvas.innerHTML = svg;
      cleanLabels(canvas.querySelector("svg"));
    } catch (err) {
      failed += 1;
      card.classList.add("error");
      canvas.replaceChildren(el("div", { class: "err" }, "Could not render this diagram:\\n" + (err && err.message ? err.message : err)));
    }
    for (const b of card.querySelectorAll(".actions button")) if (b.textContent !== "Copy source") b.disabled = !canvas.querySelector("svg");
  }
  status.textContent = failed ? `${diagrams.length - failed} of ${diagrams.length} diagrams rendered; ${failed} failed` : `${diagrams.length} diagrams rendered`;
  status.classList.toggle("bad", failed > 0);
  document.body.dataset.rendered = String(diagrams.length - failed);
  document.body.dataset.failed = String(failed);
}

// Plain SVG text labels keep exports portable (PowerPoint ignores HTML labels), but mermaid then prints
// "&" as "&amp;" and leaves inline tags such as <b> as literal text; tidy those text nodes.
function cleanLabels(svg) {
  const entities = { "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'" };
  const walker = document.createTreeWalker(svg, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    if (node.parentNode && node.parentNode.closest("style")) continue;
    node.nodeValue = node.nodeValue.replace(/&(amp|lt|gt|quot|#39);/g, m => entities[m])
      .replace(/<\\/?(b|i|strong|em|u|small)>/g, "").replace(/\\s{2,}/g, " ");
  }
}

function svgText(card) {
  const svg = card.querySelector(".canvas svg").cloneNode(true);
  svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  const box = card.querySelector(".canvas svg").viewBox.baseVal;
  if (box && box.width) { svg.setAttribute("width", box.width); svg.setAttribute("height", box.height); }
  svg.style.backgroundColor = getComputedStyle(document.body).getPropertyValue("--surface").trim();
  return { text: new XMLSerializer().serializeToString(svg), width: box.width, height: box.height };
}

function save(blob, name) {
  const a = el("a", { href: URL.createObjectURL(blob), download: name });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

function downloadSvg(d, card) {
  save(new Blob([svgText(card).text], { type: "image/svg+xml" }), d.slug + ".svg");
}

function downloadPng(d, card, button) {
  const { text, width, height } = svgText(card);
  const scale = 2, img = new Image();
  img.onload = () => {
    const c = el("canvas"); c.width = Math.ceil(width * scale); c.height = Math.ceil(height * scale);
    const ctx = c.getContext("2d");
    ctx.fillStyle = getComputedStyle(document.body).getPropertyValue("--surface").trim() || "#ffffff";
    ctx.fillRect(0, 0, c.width, c.height);
    ctx.drawImage(img, 0, 0, c.width, c.height);
    try { c.toBlob(b => b ? save(b, d.slug + ".png") : alert("PNG export failed; use SVG instead."), "image/png"); }
    catch (e) { alert("This browser blocked PNG export (" + e.name + "); use SVG instead."); }
  };
  img.onerror = () => alert("PNG export failed; use SVG instead.");
  img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(text);
}

function toggleWide(d, card, button) {
  const wide = card.querySelector(".canvas").classList.toggle("wide");
  button.textContent = wide ? "Fit" : "Wide";
}

async function copySource(d, card, button) {
  try { await navigator.clipboard.writeText(d.code); button.textContent = "Copied"; }
  catch { button.textContent = "Select the source below"; card.querySelector("details").open = true; }
  setTimeout(() => (button.textContent = "Copy source"), 1600);
}

renderAll();
dark.addEventListener("change", renderAll);
</script>
</body>
</html>
"""


def main() -> int:
    diagrams = collect()
    if not diagrams:
        print("No Mermaid diagrams found.")
        return 1
    data = json.dumps(diagrams, ensure_ascii=False).replace("</", "<\\/")
    page = (PAGE.replace("__DATA__", data).replace("__COUNT__", str(len(diagrams)))
            .replace("__MERMAID__", MERMAID).replace("__MERMAID_VERSION__", MERMAID.split("@")[1].split("/")[0])
            .replace("__GENERATED__", html.escape(time.strftime("%Y-%m-%d %H:%M"))))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    for d in diagrams:
        print(f"  {d['id']:>2}. {d['title']:<52} {d['kind']:<16} {d['doc']}:{d['line']}")
    print(f"\n{len(diagrams)} diagrams -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
