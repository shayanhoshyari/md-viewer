"""The page shell, the sidebar tree, view tabs, directory listings and path safety."""

from __future__ import annotations

import html
from importlib.resources import files
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException

from md_viewer.highlight import SHIKI_THEME, SHIKI_VERSION


def static_text(name: str) -> str:
    """A file from the package's static/ folder."""
    return files("md_viewer").joinpath("static", name).read_text(encoding="utf-8")


STYLE = static_text("style.css")
CLIENT_JS = static_text("client.js")
KATEX_VERSION = "0.16.22"
TREE_FILE_EXTS = {".json", ".md", ".py", ".toml", ".yaml", ".yml"}
# Names hidden from the file tree and directory listings.
EXCLUDE = {".DS_Store", ".git", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__"}


def resolve_safe(root: Path, request_path: str) -> Path:
    target = (root / request_path).resolve()
    if target != root and root not in target.parents:
        raise HTTPException(status_code=404)
    return target


def tree_html(root: Path) -> str:
    def walk(dir_path: Path) -> list[str]:
        try:
            children = sorted(dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return []
        lines: list[str] = []
        for child in children:
            if child.name in EXCLUDE:
                continue
            if child.name.startswith(".") and child.name not in {".gitignore", ".claude"}:
                continue
            if child.is_dir():
                inner = walk(child)
                if not inner:
                    continue
                lines.append(f'<li class="dir"><details><summary>{html.escape(child.name)}/</summary><ul>')
                lines.extend(inner)
                lines.append("</ul></details></li>")
                continue
            if child.suffix.lower() not in TREE_FILE_EXTS:
                continue
            rel = child.relative_to(root)
            href = "/" + quote(rel.as_posix())
            lines.append(f'<li><a href="{href}">{html.escape(child.name)}</a></li>')
        return lines

    return '<ul class="tree-root">' + "\n".join(walk(root)) + "</ul>"


def view_links(rel: Path, current: str, *, markdown: bool, source: bool = True, raw: bool = True) -> str:
    """Tab bar of the file's views; Source is the default view for non-Markdown.

    A file of an unknown type only has Diff, plus Raw when it looks like text.
    """
    href = "/" + quote(rel.as_posix())
    diff = ("diff", "Diff", href + "?view=diff")
    source_tab = ("source", "Source", href + "?view=source" if markdown else href)
    raw_tab = ("raw", "Raw", href + "?view=raw")
    if markdown:
        options = [("rendered", "Rendered", href), diff, source_tab, raw_tab, ("pdf", "PDF", href + "?view=pdf")]
    elif not source:
        options = [diff, raw_tab] if raw else [diff]
    else:
        options = [source_tab, diff, raw_tab]
    links = [
        f'<a href="{url}"' + (' class="active"' if name == current else "") + f">{label}</a>"
        for name, label, url in options
    ]
    return '<div class="views">' + "".join(links) + "</div>"


def short_path(path: Path) -> str:
    """The path with the home folder written as `~`."""
    home = Path.home()
    if path == home or home in path.parents:
        return "~/" + path.relative_to(home).as_posix() if path != home else "~"
    return str(path)


def servers_html(root: Path) -> str:
    """The sidebar header: this server's root, opening a list of every running md-viewer (filled by client.js),
    and a button copying the root path."""
    name = html.escape(root.name or str(root))
    return (
        '<div class="servers-head">'
        f'<details class="servers"><summary title="{html.escape(short_path(root))}">{name}</summary>'
        '<ul class="server-list"><li class="server-note">Looking…</li></ul></details>'
        f'<button class="copy-root" data-root="{html.escape(str(root))}" title="Copy folder path">&#10697;</button>'
        "</div>"
    )


def page(root: Path, title: str, body: str, rel: Path, views: str = "", panel: str = "") -> str:
    body_class = ' class="has-scm"' if panel else ""
    scm_html = ""
    scm_script = ""
    if panel:
        scm_html = '\n  <button class="scm-toggle" title="Toggle source control">&#8644;</button>\n  ' + panel
        scm_script = (
            '\n    try { if (localStorage.getItem("scmHidden")) '
            'document.documentElement.classList.add("scm-hidden"); } catch (e) {}'
        )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <link rel="preconnect" href="https://esm.sh" crossorigin>
  <link rel="stylesheet" href="/_static/pygments.css">
  <link rel="stylesheet" href="/_static/style.css">
  <script>
    try {{ if (localStorage.getItem("navHidden")) document.documentElement.classList.add("nav-hidden"); }} catch (e) {{}}{scm_script}
    window.__shikiVersion = "{SHIKI_VERSION}";
    window.__shikiTheme = "{SHIKI_THEME}";
  </script>
  <script type="module">
    import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
    mermaid.initialize({{ startOnLoad: true }});
  </script>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/katex.min.css">
  <script type="module">
    import katex from "https://cdn.jsdelivr.net/npm/katex@{KATEX_VERSION}/dist/katex.mjs";
    for (const el of document.querySelectorAll(".markdown-body .math")) {{
      katex.render(el.textContent, el, {{ displayMode: el.classList.contains("block"), throwOnError: false }});
    }}
  </script>
</head>
<body{body_class}>
  <aside class="sidebar">
    {servers_html(root)}
    <input class="tree-filter" type="search" placeholder="Filter files ( / )" autocomplete="off" spellcheck="false">
    {tree_html(root)}
  </aside>
  <main class="content">
    <button class="nav-toggle" title="Toggle sidebar">&#9776;</button>
    <div class="path">{html.escape(rel.as_posix())}{views}</div>
    {body}
  </main>{scm_html}
  <script type="module" src="/_static/client.js"></script>
</body>
</html>"""  # noqa: E501


def directory_listing(path: Path, rel: Path) -> str:
    rows = []
    if rel.parts:
        rows.append('<li><a href="../">../</a></li>')
    for child in sorted(path.iterdir()):
        if child.name in EXCLUDE:
            continue
        suffix = "/" if child.is_dir() else ""
        name = child.name + suffix
        rows.append(f'<li><a href="{quote(name)}">{html.escape(name)}</a></li>')
    return "<h1>Directory</h1><ul>" + "\n".join(rows) + "</ul>"
