"""Markdown to HTML: MarkdownIt setup, callouts, fences, PlantUML, math, numbering, outline."""

from __future__ import annotations

import base64
import html
import re
import zlib
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.rules_core import StateCore
from markdown_it.token import Token
from mdit_py_plugins.anchors import anchors_plugin
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin
from pygments.lexers import get_lexer_by_name
from pygments.lexers.special import TextLexer
from pygments.util import ClassNotFound

from md_viewer.highlight import code_block
from md_viewer.notes import Target, parse_note

PLANTUML_SVG_URL = "https://www.plantuml.com/plantuml/svg/"


def github_slug(text: str) -> str:
    text = text.lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s+", "-", text.strip())


def github_alerts(state: StateCore) -> None:
    """Turn a top-level quote beginning with a GitHub alert marker into a callout."""
    tokens = state.tokens
    # Work backwards so removing a marker-only paragraph does not shift later quotes.
    for index in range(len(tokens) - 3, -1, -1):
        opening = tokens[index]
        if opening.type != "blockquote_open" or opening.level != 0:
            continue
        if tokens[index + 1].type != "paragraph_open" or tokens[index + 2].type != "inline":
            continue
        inline = tokens[index + 2]
        marker = re.match(r"^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\][ \t]*(?:\n|$)", inline.content)
        if not marker:
            continue
        closing = next(
            token for token in tokens[index + 3 :] if token.type == "blockquote_close" and token.level == opening.level
        )
        kind = marker.group(1).lower()
        opening.type, opening.tag = "alert_open", "div"
        opening.attrSet("class", f"markdown-alert markdown-alert-{kind}")
        closing.type, closing.tag = "alert_close", "div"
        inline.content = inline.content[marker.end() :]
        if not inline.content:
            del tokens[index + 1 : index + 4]
        title = Token("html_block", "", 0)
        title.content = f'<p class="markdown-alert-title">{kind.title()}</p>\n'
        tokens.insert(index + 1, title)


LINE_OFFSET = "md_viewer_line_offset"  # env key: file lines dropped before the parsed source (front matter)


def note_html(quote: str, text: str, line: int) -> str:
    quote_html = f'<div class="md-note-quote">{html.escape(quote)}</div>' if quote else ""
    return (
        f'<aside class="md-note" data-note-line="{line}">{quote_html}'
        f'<div class="md-note-text">{html.escape(text)}</div></aside>\n'
    )


def note_boxes(state: StateCore) -> None:
    """Show each note comment as a note box, carrying its 1-based line in the file."""
    offset = state.env.get(LINE_OFFSET, 0)
    for token in state.tokens:
        if token.type != "html_block" or token.map is None:
            continue
        note = parse_note(token.content.rstrip("\r\n"))
        if note is not None and "\n" not in token.content.rstrip("\r\n"):
            token.content = note_html(note.quote, note.text, offset + token.map[0] + 1)
            token.meta["note"] = True


def build_markdown() -> MarkdownIt:
    md = (
        MarkdownIt("commonmark", {"html": True, "linkify": True})
        .enable(["strikethrough", "table"])
        .use(anchors_plugin, permalink=False, slug_func=github_slug, max_level=6)
        .use(dollarmath_plugin, allow_labels=True, allow_space=False, allow_digits=False, double_inline=True)
        .use(footnote_plugin)
        .use(tasklists_plugin)
    )
    md.core.ruler.after("block", "github_alerts", github_alerts)
    md.core.ruler.after("github_alerts", "note_boxes", note_boxes)
    md.add_render_rule("fence", render_fence)
    return md


def plantuml_url(source: str) -> str:
    """Encode UTF-8 diagram text for PlantUML's SVG renderer."""
    compressor = zlib.compressobj(level=9, wbits=-15)
    compressed = compressor.compress(source.encode("utf-8")) + compressor.flush()
    alphabet = bytes.maketrans(
        b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/",
        b"0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_",
    )
    encoded = base64.b64encode(compressed).translate(alphabet).rstrip(b"=")
    return PLANTUML_SVG_URL + encoded.decode("ascii")


def render_fence(self: Any, tokens: Any, idx: int, options: Any, env: Any) -> str:
    token = tokens[idx]
    language = token.info.strip().split(maxsplit=1)[0] if token.info else ""
    code = token.content
    if language == "mermaid":
        return f'<div class="mermaid">{html.escape(code)}</div>\n'
    if language == "plantuml":
        # Only the diagram is sent to the public renderer, not the page/referrer.
        # Keep remote SVG in an image context and retain escaped source offline.
        url = plantuml_url(code)
        return (
            '<figure class="plantuml">'
            f'<a href="{url}" target="_blank" rel="noopener noreferrer">'
            f'<img src="{url}" alt="PlantUML diagram (source below)" '
            'loading="lazy" referrerpolicy="no-referrer"></a>'
            "<details><summary>Diagram source · rendered by public PlantUML server</summary>"
            f"<pre><code>{html.escape(code)}</code></pre></details></figure>\n"
        )
    try:
        lexer = get_lexer_by_name(language) if language else TextLexer()
    except ClassNotFound:
        lexer = TextLexer()
    return code_block(code, lexer, language, linenos=False) + "\n"


MD = build_markdown()


def strip_myst_metadata(text: str) -> str:
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return text
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return "".join(lines[index + 1 :])
    return text


def section_numbers_enabled(source: str) -> bool:
    """Recognize a standalone opt-out near the top, excluding fenced examples."""
    fence: tuple[str, int] | None = None
    for line in source.splitlines()[:20]:
        if fence:
            if re.match(r"^ {0,3}" + re.escape(fence[0]) + "{" + str(fence[1]) + r",}\s*$", line):
                fence = None
            continue
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if opening and not (opening.group(1)[0] == "`" and "`" in opening.group(2)):
            fence = (opening.group(1)[0], len(opening.group(1)))  # ty: ignore[unsound-assignment]
        elif line.strip() == "<!-- section-numbers: false -->":
            return False
    return True


def parse_markdown(source: str) -> tuple[list[Token], dict[str, Any], str]:
    """Tokens (headings numbered unless opted out), the parse env, and the source without front matter."""
    stripped = strip_myst_metadata(source)
    env: dict[str, Any] = {LINE_OFFSET: source.count("\n") - stripped.count("\n")}
    source = stripped
    tokens = MD.parse(source, env)
    if section_numbers_enabled(source):
        counters = [0] * 7
        for index, token in enumerate(tokens):
            if token.type != "heading_open" or token.tag == "h1":
                continue
            depth = int(token.tag[1])
            counters[depth] += 1
            for deeper in range(depth + 1, 7):
                counters[deeper] = 0
            number = ".".join(str(counters[level]) for level in range(2, depth + 1)) + ". "
            inline = tokens[index + 1]
            assert inline.children is not None
            inline.children.insert(0, Token("text", "", 0, content=number))
    return tokens, env, source


def render_markdown(path: Path, *, notes: bool = False) -> str:
    """The page body; with `notes`, every block that can take a note carries `data-block`."""
    tokens, env, source = parse_markdown(path.read_text(encoding="utf-8", errors="replace"))
    if notes:
        mark_note_targets(tokens, note_targets(tokens, source, env[LINE_OFFSET]))
    body = MD.renderer.render(tokens, MD.options, {})
    outline = outline_html(tokens)
    if not outline:
        return body  # ty: ignore[unsound-return-statement]
    head, sep, tail = body.partition("</h1>")
    return head + sep + "\n" + outline + tail if sep else outline + body  # ty: ignore[unsound-return-statement]


def group_end(tokens: list[Token], start: int) -> int:
    """Index of the token that closes the group opened at `start` (itself for a single token)."""
    opening = tokens[start]
    if opening.nesting != 1:
        return start
    if opening.type == "footnote_block_open":
        # The footnote plugin leaves inner tokens at level 0, so find its own close.
        return next(i for i in range(start + 1, len(tokens)) if tokens[i].type == "footnote_block_close")
    return next(
        i for i in range(start + 1, len(tokens)) if tokens[i].nesting == -1 and tokens[i].level == opening.level
    )


LIST_MARKER_RE = re.compile(r"^( {0,3})([-+*]|\d{1,9}[.)])( *)(.?)")


def item_indent(line: str) -> str:
    """Spaces up to a list item's content column, so a note line stays inside the item."""
    match = LIST_MARKER_RE.match(line)
    if not match:
        return "  "
    lead, marker, spaces, rest = match.groups()
    gap = len(spaces) if rest and 1 <= len(spaces) <= 4 else 1
    return " " * (len(lead) + len(marker) + gap)


def note_targets(tokens: list[Token], source: str, offset: int) -> list[tuple[int, int, Target]]:
    """(opening token, closing token, where a new note goes) for each block that can take notes.

    The blocks are the rendered diff's: top-level blocks, and the items of top-level lists. A raw
    HTML block takes none, since a line right after it joins it. Notes already after a block are
    skipped, so a new note goes below them.
    """
    lines = source.split("\n")

    def last_line(start: int, end: int) -> int:
        while end > start + 1 and not lines[end - 1].strip():
            end -= 1
        return end

    targets: list[tuple[int, int, Target]] = []
    previous: int | None = None  # index in targets of the block that notes below would belong to
    index = 0
    while index < len(tokens):
        opening = tokens[index]
        end = group_end(tokens, index)
        if opening.map is None:
            previous = None
        elif opening.type == "html_block":
            if previous is not None and opening.meta.get("note"):
                first, last, target = targets[previous]
                targets[previous] = (first, last, Target(offset + opening.map[1], target.indent))
            else:
                previous = None
        elif opening.type in {"bullet_list_open", "ordered_list_open"}:
            item = index + 1
            while item < end:
                item_end = group_end(tokens, item)
                start, stop = tokens[item].map or (0, 0)
                indent = item_indent(lines[start])
                targets.append((item, item_end, Target(offset + last_line(start, stop), indent)))
                item = item_end + 1
            previous = None
        else:
            start, stop = opening.map
            targets.append((index, end, Target(offset + last_line(start, stop), "")))
            previous = len(targets) - 1
        index = end + 1
    return targets


ATTR_OPENERS = {"paragraph_open", "heading_open", "blockquote_open", "alert_open", "table_open", "list_item_open", "hr"}


def mark_note_targets(tokens: list[Token], targets: list[tuple[int, int, Target]]) -> None:
    """Number the blocks with `data-block`; blocks whose renderer drops attributes get a wrapper."""
    for number, (first, last, _) in reversed(list(enumerate(targets))):
        opening = tokens[first]
        if opening.type in ATTR_OPENERS:
            opening.attrSet("data-block", str(number))
            continue
        before = Token("html_block", "", 0, content=f'<div class="md-block" data-block="{number}">\n')
        after = Token("html_block", "", 0, content="</div>\n")
        tokens[last + 1 : last + 1] = [after]
        tokens[first:first] = [before]


def outline_html(tokens: list[Token]) -> str:
    """Build a table of contents from H2 and H3 headings, after numbering."""
    items: list[str] = []
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or token.tag not in {"h2", "h3"}:
            continue
        inline = tokens[index + 1]
        assert inline.children is not None
        text = "".join(child.content for child in inline.children if child.type in {"text", "code_inline"})
        anchor = str(token.attrGet("id") or "")
        items.append(f'<li class="toc-d{token.tag[1]}"><a href="#{html.escape(anchor)}">{html.escape(text)}</a></li>')
    if len(items) < 2:
        return ""
    return '<nav class="toc"><details open><summary>Contents</summary><ul>' + "".join(items) + "</ul></details></nav>"
