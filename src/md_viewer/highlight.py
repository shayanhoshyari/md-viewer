"""Pygments highlighting shared by markdown fences, the source view, the PDF and pygments.css."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from pygments import highlight
from pygments.formatters.html import HtmlFormatter
from pygments.lexers import get_lexer_for_filename, guess_lexer
from pygments.lexers.special import TextLexer
from pygments.util import ClassNotFound

# Highlighting is two-stage. The server renders Pygments markup so the page is
# readable immediately (and with JS off); the browser then re-highlights each
# block with Shiki, which uses the same TextMate grammars and themes as VS Code
# and so resolves function calls, parameters and types that Pygments' lexers
# lump together. Both stages emit the same `<span class="line" id="L-n">` shape,
# so line anchors and highlighting work regardless of which stage you see.
PYGMENTS_STYLE = "friendly"
SHIKI_VERSION = "3.23.0"
SHIKI_THEME = "light-plus"


# Grammars fetched on demand, so this list costs nothing until a page uses one.
SHIKI_LANGS = {
    "bash",
    "c",
    "cpp",
    "csv",
    "diff",
    "docker",
    "dotenv",
    "go",
    "graphql",
    "hcl",
    "html",
    "ini",
    "java",
    "javascript",
    "json",
    "jsonc",
    "jsonl",
    "make",
    "markdown",
    "proto",
    "python",
    "regexp",
    "rust",
    "sql",
    "toml",
    "tsx",
    "typescript",
    "xml",
    "yaml",
}


PYGMENTS_FORMATTER = HtmlFormatter(style=PYGMENTS_STYLE, linespans="L")
LINE_SPAN_RE = re.compile(r'<span id="L-(\d+)">')


def highlight_lines(code: str, lexer: Any) -> str:
    """Highlight `code` as a flat run of `<span class="line" id="L-n">` elements."""
    raw = highlight(code, lexer, PYGMENTS_FORMATTER)
    inner = raw.split("<pre>", 1)[-1].rsplit("</pre>", 1)[0]
    inner = inner.replace("<span></span>", "", 1)
    inner = LINE_SPAN_RE.sub(r'<span class="line" id="L-\1">', inner)
    return re.sub(r"\n</span>", "</span>", inner).strip("\n")


def code_block(code: str, lexer: Any, language: str, *, linenos: bool) -> str:
    """Wrap highlighted `code` in the shell that the Shiki client script upgrades."""
    classes = "code-block" + (" with-linenos" if linenos else "")
    lang_attr = f' data-lang="{html.escape(language)}"' if language in SHIKI_LANGS else ""
    return f'<div class="{classes}"{lang_attr}><pre><code>{highlight_lines(code, lexer)}</code></pre></div>'


def render_source(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        lexer = get_lexer_for_filename(path.name, text)
    except ClassNotFound:
        try:
            lexer = guess_lexer(text)
        except ClassNotFound:
            lexer = TextLexer()
    language = next((alias for alias in lexer.aliases if alias in SHIKI_LANGS), "")
    return code_block(text, lexer, language, linenos=True)
