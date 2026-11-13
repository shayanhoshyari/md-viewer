"""Markdown to HTML: MarkdownIt setup, callouts, fences, PlantUML, math, numbering, outline."""

from __future__ import annotations

import base64
import html
import re
import zlib
from dataclasses import dataclass
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
from md_viewer.notes import Note, Target, parse_note, row_without_note

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


def note_html(quote: str, text: str) -> str:
    """A note box; the page's block numbering adds `data-note-block`."""
    quote_html = f'<div class="md-note-quote">{html.escape(quote)}</div>' if quote else ""
    return f'<aside class="md-note">{quote_html}<div class="md-note-text">{html.escape(text)}</div></aside>\n'


def note_boxes(state: StateCore) -> None:
    """Show each note as a note box: a note line in place, a row's note in a full-width row below it.

    Note tokens get `meta["note"]`, and their `map` is the note's line (for a row note, the row's).
    """
    lines = state.src.split("\n")
    tokens = state.tokens
    columns = 0
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.type == "html_block" and token.map is not None:
            note = parse_note(token.content.rstrip("\r\n"))
            if note is not None and not note.on_row and "\n" not in token.content.rstrip("\r\n"):
                token.content = note_html(note.quote, note.text)
                token.meta["note"] = True
        elif token.type == "thead_open":
            columns = sum(1 for t in tokens[index : group_end(tokens, index)] if t.type == "th_open")
        elif token.type == "tr_open" and token.map is not None and tokens[index - 1].type != "thead_open":
            note = parse_note(lines[token.map[0]].rstrip("\r"))
            if note is not None and note.on_row:
                close = group_end(tokens, index)
                box = Token("html_block", "", 0, map=list(token.map), level=token.level)
                box.content = (
                    f'<tr class="md-note-row"><td colspan="{columns}">{note_html(note.quote, note.text)}</td></tr>\n'
                )
                box.meta["note"] = True
                tokens.insert(close + 1, box)
        index += 1


DEFAULT_SORT_RE = re.compile(r"^<!-- default-sort: (.+?)(?: (asc|desc))? -->$")


def default_sort(state: StateCore) -> None:
    """A `<!-- default-sort: <column> [asc|desc] -->` line before a table marks that header cell.

    The cell gets `data-default-sort` set to the direction; the page sorts by it on load.
    """
    tokens = state.tokens
    for index, token in enumerate(tokens[:-1]):
        if token.type != "html_block" or tokens[index + 1].type != "table_open":
            continue
        match = DEFAULT_SORT_RE.match(token.content.strip())
        if not match:
            continue
        column, direction = match.group(1).strip().casefold(), match.group(2) or "asc"
        for cell, inline in zip(tokens[index + 1 :], tokens[index + 2 :]):
            if cell.type == "thead_close":
                break
            if cell.type == "th_open" and inline.content.strip().casefold() == column:
                cell.attrSet("data-default-sort", direction)
                break


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
    md.core.ruler.after("note_boxes", "default_sort", default_sort)
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
        mark_note_targets(tokens, note_targets(tokens, source, env[LINE_OFFSET]), env[LINE_OFFSET])
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


def note_line(token: Token, offset: int) -> int | None:
    """The 0-based file line of a note token, or None for any other token."""
    return offset + token.map[0] if token.meta.get("note") and token.map is not None else None


def note_targets(tokens: list[Token], source: str, offset: int) -> list[tuple[int, int, Target]]:
    """(opening token, closing token, where its note goes) for each block that can take a note.

    The blocks are the rendered diff's (top-level blocks, and the items of top-level lists) plus
    each table body row. A raw HTML block takes none, since a line right after it joins it. A new
    note line goes below the notes already after a block.
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
            line = note_line(opening, offset)
            if previous is not None and line is not None:
                first, last, target = targets[previous]
                note = line if target.note is None else target.note
                targets[previous] = (first, last, Target(offset + opening.map[1], target.indent, note=note))
            else:
                previous = None
        elif opening.type in {"bullet_list_open", "ordered_list_open"}:
            item = index + 1
            while item < end:
                item_end = group_end(tokens, item)
                start, stop = tokens[item].map or (0, 0)
                level = tokens[item].level + 1
                inside = (note_line(t, offset) for t in tokens[item:item_end] if t.level == level)
                note = next((line for line in inside if line is not None), None)
                indent = item_indent(lines[start])
                targets.append((item, item_end, Target(offset + last_line(start, stop), indent, note=note)))
                item = item_end + 1
            previous = None
        else:
            start, stop = opening.map
            targets.append((index, end, Target(offset + last_line(start, stop), "")))
            previous = len(targets) - 1
            if opening.type == "table_open":
                targets.extend(row_targets(tokens, index, end, offset))
        index = end + 1
    return targets


def row_targets(tokens: list[Token], start: int, end: int, offset: int) -> list[tuple[int, int, Target]]:
    """One target per body row of the table between tokens `start` and `end`."""
    rows: list[tuple[int, int, Target]] = []
    in_body = False
    for index in range(start, end):
        token = tokens[index]
        in_body = in_body or token.type == "tbody_open"
        if not in_body or token.type != "tr_open" or token.map is None:
            continue
        close = group_end(tokens, index)
        line = offset + token.map[0]
        has_note = close + 1 < len(tokens) and note_line(tokens[close + 1], offset) == line
        rows.append((index, close, Target(line, "", row=True, note=line if has_note else None)))
    return rows


BLOCK_KINDS = {
    "alert_open": "callout",
    "blockquote_open": "quote",
    "bullet_list_open": "list",
    "code_block": "code block",
    "fence": "code block",
    "footnote_block_open": "footnotes",
    "heading_open": "heading",
    "hr": "rule",
    "list_item_open": "list item",
    "tr_open": "table row",
    "math_block": "math",
    "ordered_list_open": "list",
    "paragraph_open": "paragraph",
    "table_open": "table",
}


@dataclass(frozen=True)
class FoundNote:
    """A note in a file, with the block it's on. Lines are 1-based; `kind` is "" above every block."""

    line: int
    note: Note
    kind: str
    start: int
    end: int
    source: list[str]


def find_notes(text: str) -> list[FoundNote]:
    """Every note the rendered page shows, each with its row or the nearest block that starts above it."""
    tokens, env, source = parse_markdown(text)
    offset = env[LINE_OFFSET]
    lines = [line.rstrip("\r") for line in text.split("\n")]
    blocks = [
        (offset + (tokens[first].map or (0, 0))[0] + 1, tokens[first])
        for first, _, target in note_targets(tokens, source, offset)
        if not target.row
    ]
    found: list[FoundNote] = []
    for number in sorted(line + 1 for token in tokens if (line := note_line(token, offset)) is not None):
        note = parse_note(lines[number - 1])
        if note is None:
            continue
        above = [(start, token) for start, token in blocks if start < number]
        if note.on_row:
            header = lines[above[-1][0] - 1] if above else ""
            found.append(FoundNote(number, note, "table row", number, number, [header, row_without_note(note.lead)]))
            continue
        if not above:
            found.append(FoundNote(number, note, "", 0, 0, []))
            continue
        start, token = above[-1]
        end = number - 1
        while end > start and (not lines[end - 1].strip() or parse_note(lines[end - 1])):
            end -= 1
        body = [line for line in lines[start - 1 : end] if not parse_note(line)]
        kind = BLOCK_KINDS.get(token.type, token.type.removesuffix("_open").replace("_", " "))
        found.append(FoundNote(number, note, kind, start, end, body))
    return found


ATTR_OPENERS = {
    "alert_open",
    "blockquote_open",
    "heading_open",
    "hr",
    "list_item_open",
    "paragraph_open",
    "table_open",
    "tr_open",
}


def mark_note_targets(tokens: list[Token], targets: list[tuple[int, int, Target]], offset: int) -> None:
    """Number the blocks with `data-block` (`data-noted` if they have a note) and their note boxes with
    `data-note-block`. Blocks whose renderer drops attributes get a wrapper."""
    note_tokens = {line: token for token in tokens if (line := note_line(token, offset)) is not None}
    for number, (first, last, target) in reversed(list(enumerate(targets))):
        attrs = {"data-block": str(number)}
        box = note_tokens.get(target.note) if target.note is not None else None
        if box is not None:
            attrs["data-noted"] = ""
            box.content = box.content.replace(
                '<aside class="md-note"', f'<aside class="md-note" data-note-block="{number}"', 1
            )
        opening = tokens[first]
        if opening.type in ATTR_OPENERS:
            for name, value in attrs.items():
                opening.attrSet(name, value)
            continue
        attr_html = "".join(f' {name}="{value}"' if value else f" {name}" for name, value in attrs.items())
        before = Token("html_block", "", 0, content=f'<div class="md-block"{attr_html}>\n')
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
