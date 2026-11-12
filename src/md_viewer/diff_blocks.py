"""Rendered markdown diffs: cut each side into blocks, diff the block sequences, render each block."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, replace
from difflib import SequenceMatcher

from markdown_it.token import Token

from md_viewer.markdown import MD, group_end, parse_markdown, strip_myst_metadata

CONTEXT = 2  # unchanged blocks shown around each change


@dataclass(frozen=True)
class Block:
    key: str  # what is compared: the block's source lines, trailing whitespace stripped
    html: str
    kind: str  # the opening token's type, so a changed paragraph pairs with a paragraph


def source_key(lines: list[str], token: Token) -> str | None:
    if token.map is None:
        return None
    return "\n".join(line.rstrip() for line in lines[token.map[0] : token.map[1]]).strip("\n")


def cut_blocks(source: str, tokens: list[Token]) -> list[tuple[str | None, list[Token]]]:
    """(key, tokens) per block: each top-level group, with a top-level list cut into its items."""
    lines = source.splitlines()
    blocks: list[tuple[str | None, list[Token]]] = []
    index = 0
    while index < len(tokens):
        end = group_end(tokens, index)
        opening = tokens[index]
        if opening.type in {"bullet_list_open", "ordered_list_open"}:
            item = index + 1
            while item < end:
                item_end = group_end(tokens, item)
                wrapper = Token(
                    opening.type, opening.tag, 1, attrs=dict(opening.attrs), markup=opening.markup, block=True
                )
                if opening.type == "ordered_list_open":
                    number = int(tokens[item].info or 1)
                    if number == 1:
                        wrapper.attrs.pop("start", None)
                    else:
                        wrapper.attrSet("start", str(number))
                closing = tokens[end]
                group = [wrapper, *tokens[item : item_end + 1], closing]
                blocks.append((source_key(lines, tokens[item]), group))
                item = item_end + 1
        else:
            blocks.append((source_key(lines, opening), tokens[index : end + 1]))
        index = end + 1
    return blocks


def render_blocks(text: str, *, old: bool) -> list[Block]:
    tokens, env, source = parse_markdown(text)
    if old:
        for token in tokens:
            if token.type == "heading_open" and token.attrs:
                token.attrs.pop("id", None)
    result = []
    for key, group in cut_blocks(source, tokens):
        rendered = MD.renderer.render(group, MD.options, env)
        result.append(Block(rendered if key is None else key, rendered, group[0].type))
    return result


Row = tuple[str, Block | None, Block | None]  # kind (same, del, add, change), old block, new block


def similar(a: Block, b: Block) -> bool:
    return a.kind == b.kind and SequenceMatcher(None, a.key, b.key, autojunk=False).ratio() >= 0.5


def pair_changed(old: list[Block], new: list[Block]) -> list[Row]:
    """Rows for a changed run.

    Each old block pairs with the next similar new one, in order; the rest are removed or added.
    """
    if len(old) == len(new) == 1 and old[0].kind == new[0].kind:
        return [("change", old[0], new[0])]
    rows: list[Row] = []
    j = 0
    for a in old:
        match = next((k for k in range(j, len(new)) if similar(a, new[k])), None)
        if match is None:
            rows.append(("del", a, None))
            continue
        rows.extend(("add", None, b) for b in new[j:match])
        rows.append(("change", a, new[match]))
        j = match + 1
    rows.extend(("add", None, b) for b in new[j:])
    return rows


HTML_PIECE_RE = re.compile(r"(<[^>]*>)|([^<]+)")
# Words, runs of spaces, entities and single symbols; an entity such as &lt; is never split.
ATOM_RE = re.compile(r"&#?\w+;|\w+|\s+|[^\w\s]")
UNMARKED = re.compile(r'class="(?:mermaid|plantuml)"|class="math')  # text that a script reads back


def atoms(rendered: str) -> list[tuple[str, str]]:
    """The HTML as ("tag", text) and ("atom", text) pieces, in order."""
    pieces: list[tuple[str, str]] = []
    for tag, text in HTML_PIECE_RE.findall(rendered):
        if tag:
            pieces.append(("tag", tag))
        else:
            pieces.extend(("atom", atom) for atom in ATOM_RE.findall(text))
    return pieces


def marked(pieces: list[tuple[str, str]], changed: set[int]) -> str:
    """Rebuild the HTML, wrapping each run of changed atoms (between tags) in <mark>."""
    out: list[str] = []
    run: list[str] = []
    atom_index = 0

    def flush() -> None:
        text = "".join(run)
        run.clear()
        core = text.strip()
        if not core:
            out.append(text)
            return
        start = text.index(core)
        out.append(text[:start] + "<mark>" + core + "</mark>" + text[start + len(core) :])

    for kind, text in pieces:
        if kind == "tag":
            flush()
            out.append(text)
            continue
        if atom_index in changed:
            run.append(text)
        else:
            flush()
            out.append(text)
        atom_index += 1
    flush()
    return "".join(out)


def mark_words(old: str, new: str) -> tuple[str, str]:
    """Mark the changed words of a changed block pair, leaving tags alone, when the blocks are similar."""
    if UNMARKED.search(old) or UNMARKED.search(new):
        return old, new
    a, b = atoms(old), atoms(new)
    a_text = [text for kind, text in a if kind == "atom"]
    b_text = [text for kind, text in b if kind == "atom"]
    matcher = SequenceMatcher(None, a_text, b_text, autojunk=False)
    if matcher.ratio() < 0.5:
        return old, new
    a_changed: set[int] = set()
    b_changed: set[int] = set()
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            a_changed.update(range(i1, i2))
            b_changed.update(range(j1, j2))
    return marked(a, a_changed), marked(b, b_changed)


def with_marks(row: Row) -> Row:
    kind, a, b = row
    if kind != "change" or a is None or b is None:
        return row
    old, new = mark_words(a.html, b.html)
    return kind, replace(a, html=old), replace(b, html=new)


def block_rows(old: list[Block], new: list[Block]) -> list[Row]:
    matcher = SequenceMatcher(None, [b.key for b in old], [b.key for b in new], autojunk=False)
    rows: list[Row] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            rows.extend(("same", old[i], new[j]) for i, j in zip(range(i1, i2), range(j1, j2)))
            continue
        rows.extend(with_marks(row) for row in pair_changed(old[i1:i2], new[j1:j2]))
    return rows


def cell(block: Block | None, kind: str) -> str:
    if block is None:
        return '<div class="bcell empty"></div>'
    return f'<div class="bcell {kind} markdown-body">{block.html}</div>'


def row_html(row: Row, layout: str) -> str:
    kind, a, b = row
    if layout == "split":
        if kind == "same":
            return f'<div class="brow">{cell(a, "same")}{cell(b, "same")}</div>'
        return f'<div class="brow">{cell(a, "del")}{cell(b, "add")}</div>'
    if kind == "same":
        return f'<div class="brow">{cell(b, "same")}</div>'
    cells = (cell(a, "del") if a else "") + (cell(b, "add") if b else "")
    return f'<div class="brow">{cells}</div>'


def fold(rows: list[Row], layout: str) -> str:
    """Show CONTEXT unchanged blocks around each change; fold longer unchanged runs."""
    out: list[str] = []
    index = 0
    while index < len(rows):
        if rows[index][0] != "same":
            out.append(row_html(rows[index], layout))
            index += 1
            continue
        end = index
        while end < len(rows) and rows[end][0] == "same":
            end += 1
        run = rows[index:end]
        keep_head = CONTEXT if index > 0 else 0
        keep_tail = CONTEXT if end < len(rows) else 0
        if len(run) <= keep_head + keep_tail + 1:
            out.extend(row_html(r, layout) for r in run)
        else:
            hidden = run[keep_head : len(run) - keep_tail]
            out.extend(row_html(r, layout) for r in run[:keep_head])
            noun = "block" if len(hidden) == 1 else "blocks"
            inner = "".join(row_html(r, layout) for r in hidden)
            summary = f"<summary>⋯ {len(hidden)} unchanged {noun}</summary>"
            out.append(f'<details class="bfold" open>{summary}{inner}</details>')
            out.extend(row_html(r, layout) for r in run[len(run) - keep_tail :])
        index = end
    return "".join(out)


def rendered_diff(old: str, new: str, layout: str) -> str:
    rows = block_rows(render_blocks(old, old=True), render_blocks(new, old=False))
    if all(kind == "same" for kind, _, _ in rows):
        if old == new:
            return '<p class="diff-label">No changes.</p>'
        if strip_myst_metadata(old) == strip_myst_metadata(new):
            return '<p class="diff-label">Only the front matter changed; see Text mode.</p>'
        return '<p class="diff-label">No changes to the rendered blocks (only whitespace); see Text mode.</p>'
    return f'<div class="bdiff {html.escape(layout)}">{fold(rows, layout)}</div>'
