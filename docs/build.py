#!/usr/bin/env python3
"""
Generate docs/index.html — a unified HTML documentation portal for the
Digital Employee Platform.

Usage:
    python3 docs/build.py

Output:
    docs/index.html  (self-contained, no external file dependencies at runtime;
                      uses highlight.js and fonts from CDN)
"""

from __future__ import annotations
import os
import re
import json
import markdown
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).parent.parent  # repo root

# Each entry: (doc_id, en_file, cn_file, category_en, category_cn, emoji[, nav_en, nav_cn])
# Optional nav_en / nav_cn override the sidebar label without changing the doc H1.
DOCS = [
    ("overview",    "00-digital-employee-overview.md",    "00-digital-employee-overview_cn.md",    "Design Docs",    "设计文档",     "🎨"),
    ("design",      "01-digital-employee-design.md",      "01-digital-employee-design_cn.md",      "Design Docs",    "设计文档",     "🎨"),
    ("qa-persp",    "02-digital-employee-qa-perspective.md", "02-digital-employee-qa-perspective_cn.md", "Design Docs", "设计文档", "🎨"),
    ("readme",      "README.md",                          "README_cn.md",                          "Overview",       "项目概览",     "🏠"),
    ("roadmap",     "ROADMAP.md",                         "ROADMAP_cn.md",                         "Overview",       "项目概览",     "🗺️",  "Roadmap", "路线图"),
    ("llm-guide",   "LLM_Application_Development.md",    "LLM_Application_Development_cn.md",    "LLM Dev & Agentic Evaluation", "LLM应用开发与Agentic评测", "📚", "Technical Details", "技术考虑与细节"),
    ("test",        "TEST.md",                            "TEST_cn.md",                            "LLM Dev & Agentic Evaluation", "LLM应用开发与Agentic评测", "🧪", "Digital Employee Evaluation", "数字员工评测"),
]

MD_EXTENSIONS = [
    "tables",
    "fenced_code",
    "codehilite",
    "toc",
    "attr_list",
    "def_list",
    "footnotes",
    "md_in_html",
    "pymdownx.tasklist",
]
MD_EXT_CONFIGS = {
    "codehilite": {"css_class": "highlight", "guess_lang": False},
    "toc":        {"permalink": True, "toc_depth": 3},
    "pymdownx.tasklist": {"custom_checkbox": True},
}

# ── Helpers ───────────────────────────────────────────────────────────────────

# Map every known .md filename (basename, with or without _cn suffix) → doc_id
_MD_TO_DOC: dict[str, str] = {}
for _doc_id, _en_file, _cn_file, *_ in DOCS:
    _MD_TO_DOC[Path(_en_file).name] = _doc_id
    _MD_TO_DOC[Path(_cn_file).name] = _doc_id


def _inline_images(html: str) -> str:
    """Replace <img src="assets/foo.svg"> with inline <svg> content so the
    single-file portal is fully self-contained regardless of server path."""
    def replace(m: re.Match) -> str:
        src = m.group(1)
        alt = m.group(2)
        # Only handle local assets/ SVGs
        if not src.startswith("assets/") or not src.endswith(".svg"):
            return m.group(0)
        svg_path = ROOT / src
        if not svg_path.exists():
            return m.group(0)
        svg = svg_path.read_text(encoding="utf-8")
        # Add a title for accessibility and constrain width
        svg = re.sub(r"<svg\b", f'<svg role="img" aria-label="{alt}" style="max-width:100%;height:auto"', svg, count=1)
        return svg
    # Match both orderings: alt-before-src and src-before-alt
    def _replace_any(m: re.Match) -> str:
        attrs = m.group(0)
        src_m = re.search(r'src="([^"]+)"', attrs)
        alt_m = re.search(r'alt="([^"]*)"', attrs)
        if not src_m:
            return attrs
        return replace(type('M', (), {'group': lambda self, i: (src_m.group(1) if i == 1 else (alt_m.group(1) if alt_m else ''))})())
    return re.sub(r'<img\b[^>]*/>', _replace_any, html)


def _rewrite_md_links(html: str) -> str:
    """Replace href="*.md" links with in-portal navigate() calls, or remove them."""
    def replace(m: re.Match) -> str:
        href = m.group(1)
        # Strip leading path components, keep just the filename
        fname = Path(href.split("#")[0]).name
        anchor = ("#" + href.split("#")[1]) if "#" in href else ""
        doc_id = _MD_TO_DOC.get(fname)
        if doc_id:
            return f'href="#" onclick="navigate(\'{doc_id}\');return false;"'
        # Unknown .md file — remove the href so it's not a broken link
        return 'href="#" onclick="return false;"'
    return re.sub(r'href="([^"]*\.md[^"]*)"', replace, html)


def _ensure_list_blank_lines(text: str) -> str:
    """Insert a blank line before list items that immediately follow non-blank,
    non-list lines. Python-markdown requires this; CommonMark does not."""
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines):
        if i > 0 and re.match(r"^(\s*[-*+]|\s*\d+\.)\s", line):
            prev = lines[i - 1]
            if prev.strip() and not re.match(r"^(\s*[-*+]|\s*\d+\.)\s", prev):
                out.append("")
        out.append(line)
    return "\n".join(out)


def md_to_html(text: str) -> tuple[str, list[dict]]:
    """Convert markdown text to HTML; also extract headings for nav."""
    text = _ensure_list_blank_lines(text)
    md = markdown.Markdown(extensions=MD_EXTENSIONS, extension_configs=MD_EXT_CONFIGS)
    html = md.convert(text)
    html = _rewrite_md_links(html)
    html = _inline_images(html)
    # Extract headings from toc data
    toc_items = []
    toc_raw = getattr(md, "toc_tokens", [])
    for item in _flatten_toc(toc_raw, depth=0):
        toc_items.append(item)
    return html, toc_items


def _flatten_toc(tokens: list, depth: int) -> list[dict]:
    result = []
    for tok in tokens:
        result.append({"id": tok["id"], "name": tok["name"], "depth": depth})
        if tok.get("children"):
            result.extend(_flatten_toc(tok["children"], depth + 1))
    return result


def read_md(path: Path) -> str:
    if not path.exists():
        return f"# File not found\n\n`{path}` does not exist in this repository."
    return path.read_text(encoding="utf-8")


def js_str(s: str) -> str:
    """Escape a string for embedding in a JS template literal."""
    return s.replace("\\", "\\\\").replace("`", "\\`").replace("${", "\\${")


# ── Build ─────────────────────────────────────────────────────────────────────

def build():
    # Convert all docs
    doc_data = []
    for entry in DOCS:
        doc_id, en_file, cn_file, cat_en, cat_cn, emoji = entry[:6]
        nav_en_override = entry[6] if len(entry) > 6 else None
        nav_cn_override = entry[7] if len(entry) > 7 else None

        en_md  = read_md(ROOT / en_file)
        cn_md  = read_md(ROOT / cn_file)
        en_html, en_toc = md_to_html(en_md)
        cn_html, cn_toc = md_to_html(cn_md)

        # Derive short title from first H1
        m = re.search(r"^#\s+(.+)$", en_md, re.MULTILINE)
        en_title = nav_en_override or (m.group(1).strip() if m else en_file)
        m2 = re.search(r"^#\s+(.+)$", cn_md, re.MULTILINE)
        cn_title = nav_cn_override or (m2.group(1).strip() if m2 else cn_file)

        # Truncate very long H1s
        en_title = en_title[:50]
        cn_title = cn_title[:50]

        doc_data.append({
            "id":       doc_id,
            "cat_en":   cat_en,
            "cat_cn":   cat_cn,
            "emoji":    emoji,
            "en_title": en_title,
            "cn_title": cn_title,
            "en_html":  en_html,
            "cn_html":  cn_html,
            "en_toc":   en_toc,
            "cn_toc":   cn_toc,
        })

    # Serialize for embedding in HTML
    docs_json = json.dumps(doc_data, ensure_ascii=False, separators=(",", ":"))

    # ── HTML template ──────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="zh" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Digital Employee Platform — Docs</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github.min.css" id="hljs-light">
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css" id="hljs-dark" disabled>
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<style>
/* ── Reset & Tokens ──────────────────────────────────── */
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

:root {{
  --bg:        #ffffff;
  --bg2:       #f8f9fa;
  --bg3:       #f1f3f5;
  --border:    #e1e4e8;
  --text:      #24292f;
  --text2:     #57606a;
  --text3:     #8c959f;
  --accent:    #0969da;
  --accent-bg: #ddf4ff;
  --code-bg:   #f6f8fa;
  --sidebar-w: 260px;
  --topbar-h:  52px;
  --font:      'Inter', -apple-system, sans-serif;
  --mono:      'JetBrains Mono', 'Fira Code', monospace;
}}

[data-theme="dark"] {{
  --bg:        #0d1117;
  --bg2:       #161b22;
  --bg3:       #21262d;
  --border:    #30363d;
  --text:      #e6edf3;
  --text2:     #8b949e;
  --text3:     #6e7681;
  --accent:    #58a6ff;
  --accent-bg: #121d2f;
  --code-bg:   #161b22;
}}

body {{
  font-family: var(--font);
  font-size: 15px;
  line-height: 1.7;
  color: var(--text);
  background: var(--bg);
  overflow: hidden;
  height: 100vh;
}}

/* ── Layout ──────────────────────────────────────────── */
#app {{ display: flex; height: 100vh; overflow: hidden; }}

/* Topbar */
#topbar {{
  position: fixed; top: 0; left: 0; right: 0; height: var(--topbar-h);
  background: var(--bg); border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 12px; padding: 0 16px;
  z-index: 100;
}}
#topbar .logo {{
  display: flex; align-items: center; gap: 8px;
  font-weight: 700; font-size: 14px; color: var(--text);
  text-decoration: none; white-space: nowrap;
  width: calc(var(--sidebar-w) - 32px);
  flex-shrink: 0;
}}
#topbar .logo span {{ font-size: 18px; }}
#search-wrap {{ flex: 1; max-width: 420px; position: relative; }}
#search {{
  width: 100%; padding: 6px 12px 6px 32px;
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--bg2); color: var(--text); font-size: 13px;
  font-family: var(--font); outline: none;
}}
#search:focus {{ border-color: var(--accent); background: var(--bg); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 15%, transparent); }}
#search-icon {{
  position: absolute; left: 9px; top: 50%; transform: translateY(-50%);
  color: var(--text3); pointer-events: none;
}}
#topbar-right {{ margin-left: auto; display: flex; align-items: center; gap: 8px; }}
.pill-btn {{
  padding: 4px 10px; border-radius: 6px; font-size: 12px; font-weight: 600;
  border: 1px solid var(--border); background: var(--bg2); color: var(--text2);
  cursor: pointer; transition: all .15s;
}}
.pill-btn:hover {{ background: var(--bg3); color: var(--text); }}
.pill-btn.active {{ background: var(--accent-bg); border-color: var(--accent); color: var(--accent); }}
.icon-btn {{
  width: 32px; height: 32px; border-radius: 6px; display: flex; align-items: center;
  justify-content: center; border: 1px solid var(--border); background: var(--bg2);
  cursor: pointer; color: var(--text2); transition: all .15s;
}}
.icon-btn:hover {{ background: var(--bg3); color: var(--text); }}

/* Sidebar */
#sidebar {{
  width: var(--sidebar-w); flex-shrink: 0;
  background: var(--bg2); border-right: 1px solid var(--border);
  overflow-y: auto; padding: calc(var(--topbar-h) + 12px) 0 16px;
  height: 100vh; position: sticky; top: 0;
}}
.nav-section {{ margin-bottom: 4px; }}
.nav-cat {{
  font-size: 11px; font-weight: 600; text-transform: uppercase;
  letter-spacing: .06em; color: var(--text3);
  padding: 8px 16px 4px;
}}
.nav-item {{
  display: flex; align-items: center; gap: 8px;
  padding: 6px 16px; cursor: pointer;
  font-size: 13px; color: var(--text2); border-radius: 0;
  transition: all .12s; text-decoration: none; border: none;
  background: transparent; width: 100%; text-align: left;
}}
.nav-item:hover {{ background: var(--bg3); color: var(--text); }}
.nav-item.active {{ background: var(--accent-bg); color: var(--accent); font-weight: 600; }}
.nav-item .emoji {{ font-size: 14px; flex-shrink: 0; width: 20px; }}

/* Page TOC */
#toc {{
  width: 220px; flex-shrink: 0;
  padding: calc(var(--topbar-h) + 16px) 0 16px 0;
  overflow-y: auto; height: 100vh; position: sticky; top: 0;
  border-left: 1px solid var(--border);
}}
#toc-inner {{ padding: 0 16px; }}
#toc-inner p {{ font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--text3); margin-bottom: 8px; }}
.toc-link {{
  display: block; font-size: 12px; color: var(--text2); text-decoration: none;
  padding: 3px 0 3px 8px; border-left: 2px solid transparent;
  transition: all .12s; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}}
.toc-link:hover {{ color: var(--text); border-color: var(--border); }}
.toc-link.active {{ color: var(--accent); border-color: var(--accent); }}
.toc-link.depth-1 {{ padding-left: 20px; }}
.toc-link.depth-2 {{ padding-left: 32px; font-size: 11px; }}

/* Content */
#main {{ flex: 1; overflow-y: auto; padding: calc(var(--topbar-h) + 32px) 48px 80px; min-width: 0; }}

/* Markdown content */
.md-content h1 {{ font-size: 1.9em; font-weight: 700; border-bottom: 1px solid var(--border); padding-bottom: .4em; margin: .5em 0 .8em; }}
.md-content h2 {{ font-size: 1.4em; font-weight: 700; border-bottom: 1px solid var(--border); padding-bottom: .3em; margin: 1.8em 0 .7em; }}
.md-content h3 {{ font-size: 1.15em; font-weight: 600; margin: 1.4em 0 .5em; }}
.md-content h4 {{ font-size: 1em;    font-weight: 600; margin: 1.2em 0 .4em; color: var(--text2); }}
.md-content p  {{ margin: .6em 0; }}
.md-content ul, .md-content ol {{ padding-left: 1.6em; margin: .6em 0; }}
.md-content li {{ margin: .25em 0; }}
.md-content a  {{ color: var(--accent); text-decoration: none; }}
.md-content a:hover {{ text-decoration: underline; }}
.md-content blockquote {{
  border-left: 4px solid var(--border); padding: 8px 16px;
  color: var(--text2); background: var(--bg2); border-radius: 0 6px 6px 0;
  margin: 1em 0;
}}
.md-content code:not([class]) {{
  font-family: var(--mono); font-size: .85em;
  background: var(--code-bg); color: var(--text);
  padding: .15em .4em; border-radius: 4px;
  border: 1px solid var(--border);
}}
.md-content pre {{
  background: var(--code-bg); border: 1px solid var(--border);
  border-radius: 8px; padding: 16px 20px; overflow-x: auto;
  margin: 1em 0; font-size: .875em; line-height: 1.6;
  position: relative;
}}
.md-content pre code {{
  font-family: var(--mono); background: none; border: none; padding: 0;
  color: inherit; font-size: inherit;
}}

/* Tables */
.md-content table {{
  border-collapse: collapse; width: 100%; margin: 1em 0;
  font-size: .9em; overflow-x: auto; display: block;
}}
.md-content th {{
  background: var(--bg2); border: 1px solid var(--border);
  padding: 8px 12px; text-align: left; font-weight: 600; font-size: .85em;
  white-space: nowrap;
}}
.md-content td {{
  border: 1px solid var(--border); padding: 7px 12px;
  vertical-align: top;
}}
.md-content tr:nth-child(even) td {{ background: var(--bg2); }}

/* Checkboxes (task lists) */
.md-content input[type=checkbox] {{ margin-right: 6px; accent-color: var(--accent); }}
.md-content li.task-list-item {{ list-style: none; margin-left: -1.6em; padding-left: 1.6em; }}

/* Headings anchors */
.md-content .headerlink {{ opacity: 0; margin-left: 8px; font-size: .75em; }}
.md-content :is(h1,h2,h3,h4):hover .headerlink {{ opacity: .5; }}

/* Search results overlay */
#search-results {{
  position: absolute; top: calc(100% + 4px); left: 0; right: 0;
  background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0,0,0,.15); max-height: 380px; overflow-y: auto;
  z-index: 200; display: none;
}}
#search-results.open {{ display: block; }}
.sr-item {{
  padding: 10px 14px; cursor: pointer; border-bottom: 1px solid var(--border);
  transition: background .1s;
}}
.sr-item:last-child {{ border-bottom: none; }}
.sr-item:hover {{ background: var(--bg2); }}
.sr-item-title {{ font-size: 13px; font-weight: 600; color: var(--text); }}
.sr-item-ctx  {{ font-size: 12px; color: var(--text2); margin-top: 2px; }}
.sr-item-ctx mark {{ background: color-mix(in srgb, var(--accent) 25%, transparent); color: var(--text); border-radius: 2px; padding: 0 1px; }}
.sr-empty {{ padding: 20px; text-align: center; color: var(--text3); font-size: 13px; }}

/* Mobile sidebar overlay */
#sidebar-overlay {{
  display: none; position: fixed; inset: 0; background: rgba(0,0,0,.45);
  z-index: 90; opacity: 0; transition: opacity .2s;
}}
#sidebar-overlay.visible {{ opacity: 1; }}

/* Hamburger button (mobile only) */
#menu-btn {{
  display: none; width: 36px; height: 36px; border-radius: 6px;
  align-items: center; justify-content: center;
  border: 1px solid var(--border); background: var(--bg2);
  cursor: pointer; color: var(--text2); flex-shrink: 0;
  transition: all .15s;
}}
#menu-btn:hover {{ background: var(--bg3); color: var(--text); }}

/* Responsive */
@media (max-width: 900px) {{
  #toc {{ display: none; }}
  #main {{ padding: calc(var(--topbar-h) + 20px) 24px 60px; }}
}}
@media (max-width: 768px) {{
  #menu-btn {{ display: flex; }}
  :root {{ --sidebar-w: 260px; }}
  #sidebar {{
    position: fixed; top: 0; left: 0; height: 100vh; z-index: 95;
    transform: translateX(-100%); transition: transform .25s ease;
    padding-top: calc(var(--topbar-h) + 12px);
    box-shadow: 2px 0 12px rgba(0,0,0,.15);
  }}
  #sidebar.open {{ transform: translateX(0); }}
  #sidebar-overlay {{ display: block; }}
  #main {{ padding: calc(var(--topbar-h) + 16px) 16px 60px; }}
  #topbar .logo {{ width: auto; }}
  #search-wrap {{ max-width: none; }}
}}
@media (max-width: 480px) {{
  :root {{ --sidebar-w: 80vw; }}
  #main {{ padding: calc(var(--topbar-h) + 12px) 12px 60px; }}
  .md-content pre {{ padding: 12px; font-size: .8em; }}
  .md-content table {{ font-size: .8em; }}
}}
</style>
</head>
<body>

<!-- Mobile sidebar overlay -->
<div id="sidebar-overlay" onclick="closeSidebar()"></div>

<!-- Topbar -->
<div id="topbar">
  <button id="menu-btn" onclick="toggleSidebar()" aria-label="Toggle menu">
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
      <path fill-rule="evenodd" d="M2.5 12a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5m0-4a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5m0-4a.5.5 0 0 1 .5-.5h10a.5.5 0 0 1 0 1H3a.5.5 0 0 1-.5-.5"/>
    </svg>
  </button>
  <a class="logo" href="#" onclick="navigate('overview');return false;">
    <span>🤖</span>
    <span id="logo-text">Digital Employee Docs</span>
  </a>
  <div id="search-wrap">
    <svg id="search-icon" width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
      <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001q.044.06.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1 1 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0"/>
    </svg>
    <input id="search" type="text" placeholder="Search docs…" autocomplete="off">
    <div id="search-results"></div>
  </div>
  <div id="topbar-right">
    <button class="pill-btn active" id="btn-en" onclick="setLang('en')">EN</button>
    <button class="pill-btn"        id="btn-cn" onclick="setLang('zh')">中文</button>
    <button class="icon-btn" id="theme-btn" onclick="toggleTheme()" title="Toggle dark mode">
      <svg id="icon-moon" width="15" height="15" viewBox="0 0 16 16" fill="currentColor">
        <path d="M6 .278a.77.77 0 0 1 .08.858 7.2 7.2 0 0 0-.878 3.46c0 4.021 3.278 7.277 7.318 7.277q.792-.001 1.533-.16a.79.79 0 0 1 .81.316.73.73 0 0 1-.031.893A8.35 8.35 0 0 1 8.344 16C3.734 16 0 12.286 0 7.71 0 4.266 2.114 1.312 5.124.06A.75.75 0 0 1 6 .278"/>
      </svg>
      <svg id="icon-sun" width="15" height="15" viewBox="0 0 16 16" fill="currentColor" style="display:none">
        <path d="M8 11a3 3 0 1 1 0-6 3 3 0 0 1 0 6m0 1a4 4 0 1 0 0-8 4 4 0 0 0 0 8M8 0a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 0m0 13a.5.5 0 0 1 .5.5v2a.5.5 0 0 1-1 0v-2A.5.5 0 0 1 8 13m8-5a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2a.5.5 0 0 1 .5.5M3 8a.5.5 0 0 1-.5.5h-2a.5.5 0 0 1 0-1h2A.5.5 0 0 1 3 8m10.657-5.657a.5.5 0 0 1 0 .707l-1.414 1.415a.5.5 0 1 1-.707-.708l1.414-1.414a.5.5 0 0 1 .707 0m-9.193 9.193a.5.5 0 0 1 0 .707L3.05 13.657a.5.5 0 0 1-.707-.707l1.414-1.414a.5.5 0 0 1 .707 0m9.193 2.121a.5.5 0 0 1-.707 0l-1.414-1.414a.5.5 0 0 1 .707-.707l1.414 1.414a.5.5 0 0 1 0 .707M4.464 4.465a.5.5 0 0 1-.707 0L2.343 3.05a.5.5 0 1 1 .707-.707l1.414 1.414a.5.5 0 0 1 0 .707"/>
      </svg>
    </button>
  </div>
</div>

<!-- Body -->
<div id="app">
  <!-- Sidebar -->
  <nav id="sidebar"><div id="nav-list"></div></nav>

  <!-- Main content -->
  <main id="main">
    <div id="content" class="md-content"></div>
  </main>

  <!-- Page TOC -->
  <aside id="toc">
    <div id="toc-inner">
      <p id="toc-label">On this page</p>
      <div id="toc-links"></div>
    </div>
  </aside>
</div>

<script>
// ── Data ────────────────────────────────────────────────────────────────────
const DOCS = {docs_json};

// ── State ───────────────────────────────────────────────────────────────────
let lang        = localStorage.getItem('docs_lang')  || 'zh';
let theme       = localStorage.getItem('docs_theme') || 'light';
let currentDoc  = localStorage.getItem('docs_cur')   || 'overview';

// ── Initialise ───────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {{
  applyTheme(theme);
  applyLang(lang);
  buildSidebar();
  navigate(currentDoc, false);

  document.getElementById('search').addEventListener('input', onSearch);
  document.addEventListener('click', e => {{
    if (!document.getElementById('search-wrap').contains(e.target))
      closeSearch();
  }});

  // Scroll spy for TOC
  document.getElementById('main').addEventListener('scroll', onScroll, {{ passive: true }});
}});

// ── Navigation ───────────────────────────────────────────────────────────────
function navigate(docId, scroll=true) {{
  const doc = DOCS.find(d => d.id === docId);
  if (!doc) return;
  currentDoc = docId;
  localStorage.setItem('docs_cur', docId);

  const html = lang === 'en' ? doc.en_html : doc.cn_html;
  document.getElementById('content').innerHTML = html;

  // Syntax highlight
  document.querySelectorAll('#content pre code').forEach(el => hljs.highlightElement(el));

  // Sidebar active state
  document.querySelectorAll('.nav-item').forEach(el => {{
    el.classList.toggle('active', el.dataset.id === docId);
  }});

  // TOC
  buildToc(doc);

  if (scroll) document.getElementById('main').scrollTo(0, 0);
}}

// ── Sidebar ──────────────────────────────────────────────────────────────────
function buildSidebar() {{
  const list = document.getElementById('nav-list');
  const cats = {{}};
  DOCS.forEach(d => {{
    const cat = lang === 'en' ? d.cat_en : d.cat_cn;
    if (!cats[cat]) cats[cat] = [];
    cats[cat].push(d);
  }});

  list.innerHTML = '';
  for (const [cat, docs] of Object.entries(cats)) {{
    const sec = document.createElement('div');
    sec.className = 'nav-section';
    sec.innerHTML = `<div class="nav-cat">${{cat}}</div>`;
    docs.forEach(d => {{
      const btn = document.createElement('button');
      btn.className = 'nav-item' + (d.id === currentDoc ? ' active' : '');
      btn.dataset.id = d.id;
      const title = lang === 'en' ? d.en_title : d.cn_title;
      btn.innerHTML = `<span class="emoji">${{d.emoji}}</span><span>${{title.replace(/ — .+/, '').replace(/\s*·.+/, '').slice(0,36)}}</span>`;
      btn.onclick = () => {{ navigate(d.id); closeSidebar(); }};
      sec.appendChild(btn);
    }});
    list.appendChild(sec);
  }}
}}

// ── TOC ──────────────────────────────────────────────────────────────────────
function buildToc(doc) {{
  const items = lang === 'en' ? doc.en_toc : doc.cn_toc;
  const container = document.getElementById('toc-links');
  container.innerHTML = '';
  items.forEach(item => {{
    if (item.depth > 2) return;
    const a = document.createElement('a');
    a.className = `toc-link depth-${{item.depth}}`;
    a.href = '#' + item.id;
    a.textContent = item.name;
    a.onclick = e => {{
      e.preventDefault();
      const el = document.getElementById(item.id);
      if (el) el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
    }};
    container.appendChild(a);
  }});
}}

function onScroll() {{
  const headings = document.querySelectorAll('#content h1[id],#content h2[id],#content h3[id]');
  const scrollTop = document.getElementById('main').scrollTop + 80;
  let active = null;
  headings.forEach(h => {{ if (h.offsetTop <= scrollTop) active = h.id; }});
  document.querySelectorAll('.toc-link').forEach(a => {{
    a.classList.toggle('active', a.getAttribute('href') === '#' + active);
  }});
}}

// ── Language ─────────────────────────────────────────────────────────────────
function setLang(l) {{
  lang = l;
  localStorage.setItem('docs_lang', l);
  applyLang(l);
  buildSidebar();
  navigate(currentDoc, false);
}}

function applyLang(l) {{
  document.getElementById('btn-en').classList.toggle('active', l === 'en');
  document.getElementById('btn-cn').classList.toggle('active', l === 'zh');
  document.getElementById('toc-label').textContent = l === 'en' ? 'On this page' : '本页目录';
  document.getElementById('logo-text').textContent = l === 'en' ? 'Digital Employee Docs' : '数字员工文档';
  document.querySelector('#search').placeholder = l === 'en' ? 'Search docs…' : '搜索文档…';
}}

// ── Theme ────────────────────────────────────────────────────────────────────
function toggleTheme() {{
  applyTheme(theme === 'light' ? 'dark' : 'light');
}}

function applyTheme(t) {{
  theme = t;
  localStorage.setItem('docs_theme', t);
  document.documentElement.setAttribute('data-theme', t);
  document.getElementById('icon-moon').style.display = t === 'light' ? '' : 'none';
  document.getElementById('icon-sun').style.display  = t === 'dark'  ? '' : 'none';
  document.getElementById('hljs-light').disabled = (t === 'dark');
  document.getElementById('hljs-dark').disabled  = (t === 'light');
}}

// ── Search ───────────────────────────────────────────────────────────────────
let searchTimer = null;
function onSearch(e) {{
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => runSearch(e.target.value.trim()), 200);
}}

function runSearch(query) {{
  const results = document.getElementById('search-results');
  if (!query) {{ results.classList.remove('open'); return; }}

  const terms = query.toLowerCase().split(/\s+/).filter(Boolean);
  const hits = [];

  DOCS.forEach(doc => {{
    const html  = lang === 'en' ? doc.en_html : doc.cn_html;
    const title = lang === 'en' ? doc.en_title : doc.cn_title;
    // Strip tags for plain-text search
    const plain = html.replace(/<[^>]+>/g, ' ').replace(/\\s+/g, ' ');
    const lc    = plain.toLowerCase();
    if (terms.every(t => lc.includes(t))) {{
      const idx  = lc.indexOf(terms[0]);
      const ctx  = plain.slice(Math.max(0, idx-40), idx+120).trim();
      const highlighted = terms.reduce((s, t) =>
        s.replace(new RegExp(t, 'gi'), m => `<mark>${{m}}</mark>`), ctx);
      hits.push({{ doc, title, ctx: highlighted }});
    }}
  }});

  results.innerHTML = '';
  if (!hits.length) {{
    results.innerHTML = `<div class="sr-empty">${{lang==='en'?'No results found':'未找到相关内容'}}</div>`;
  }} else {{
    hits.slice(0,8).forEach(h => {{
      const div = document.createElement('div');
      div.className = 'sr-item';
      div.innerHTML = `<div class="sr-item-title">${{h.doc.emoji}} ${{h.title.slice(0,50)}}</div><div class="sr-item-ctx">${{h.ctx}}</div>`;
      div.onclick = () => {{ navigate(h.doc.id); closeSearch(); document.getElementById('search').value=''; }};
      results.appendChild(div);
    }});
  }}
  results.classList.add('open');
}}

function closeSearch() {{
  document.getElementById('search-results').classList.remove('open');
}}

// ── Mobile sidebar ────────────────────────────────────────────────────────────
function toggleSidebar() {{
  const sidebar  = document.getElementById('sidebar');
  const overlay  = document.getElementById('sidebar-overlay');
  const isOpen   = sidebar.classList.contains('open');
  sidebar.classList.toggle('open', !isOpen);
  overlay.classList.toggle('visible', !isOpen);
}}

function closeSidebar() {{
  document.getElementById('sidebar').classList.remove('open');
  document.getElementById('sidebar-overlay').classList.remove('visible');
}}
</script>
</body>
</html>"""

    out_path = ROOT / "docs" / "index.html"
    out_path.write_text(html, encoding="utf-8")
    size_kb = out_path.stat().st_size / 1024
    print(f"✅ Generated: {out_path}  ({size_kb:.0f} KB)")
    print(f"   Docs included: {len(doc_data)}")
    for d in doc_data:
        print(f"   • {d['id']:12s}  EN: {len(d['en_html'])//1024}KB  CN: {len(d['cn_html'])//1024}KB")


if __name__ == "__main__":
    build()
