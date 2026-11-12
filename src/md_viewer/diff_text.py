"""Line diffs as HTML tables: side by side and unified."""

from __future__ import annotations

import html
import re
from difflib import SequenceMatcher
from itertools import zip_longest

WORD_RE = re.compile(r"\w+|\s+|[^\w\s]")


def intraline(old: str, new: str) -> tuple[str, str]:
    """Escape a changed line pair, marking the changed words when the lines are similar."""
    a, b = WORD_RE.findall(old), WORD_RE.findall(new)
    matcher = SequenceMatcher(None, a, b, autojunk=False)
    if matcher.ratio() < 0.5:
        return html.escape(old), html.escape(new)
    left: list[str] = []
    right: list[str] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        for out, words in ((left, a[i1:i2]), (right, b[j1:j2])):
            text = html.escape("".join(words))
            if text:
                out.append(text if tag == "equal" else f"<mark>{text}</mark>")
    return "".join(left), "".join(right)


def diff_cells(number: int | None, text: str, kind: str) -> str:
    if number is None:
        return '<td class="ln"></td><td class="empty"></td>'
    return f'<td class="ln">{number}</td><td class="{kind}">{text}</td>'


def diff_table(old: str, new: str) -> str:
    """Side-by-side table of the changed hunks with three lines of context."""
    a, b = old.splitlines(), new.splitlines()
    rows: list[str] = []
    groups = SequenceMatcher(None, a, b, autojunk=False).get_grouped_opcodes(3)
    for index, group in enumerate(groups):
        if index:
            rows.append('<tr class="gap"><td colspan="4">⋯</td></tr>')
        for tag, i1, i2, j1, j2 in group:
            for i, j in zip_longest(range(i1, i2), range(j1, j2)):
                left = a[i] if i is not None else ""
                right = b[j] if j is not None else ""
                if tag == "replace" and i is not None and j is not None:
                    left, right = intraline(left, right)
                else:
                    left, right = html.escape(left), html.escape(right)
                old_kind, new_kind = ("same", "same") if tag == "equal" else ("del", "add")
                cells = diff_cells(None if i is None else i + 1, left, old_kind)
                cells += diff_cells(None if j is None else j + 1, right, new_kind)
                rows.append(f"<tr>{cells}</tr>")
    if not rows:
        return ""
    columns = '<col class="ln"><col><col class="ln"><col>'
    return f'<table class="diff"><colgroup>{columns}</colgroup><tbody>{"".join(rows)}</tbody></table>'


def unified_table(old: str, new: str) -> str:
    """One-column table of the changed hunks: both line numbers, removed lines before added ones."""
    a, b = old.splitlines(), new.splitlines()
    rows: list[str] = []

    def row(i: int | None, j: int | None, text: str, kind: str) -> str:
        left = "" if i is None else str(i + 1)
        right = "" if j is None else str(j + 1)
        return f'<tr><td class="ln">{left}</td><td class="ln">{right}</td><td class="{kind}">{text}</td></tr>'

    groups = SequenceMatcher(None, a, b, autojunk=False).get_grouped_opcodes(3)
    for index, group in enumerate(groups):
        if index:
            rows.append('<tr class="gap"><td colspan="3">⋯</td></tr>')
        for tag, i1, i2, j1, j2 in group:
            if tag == "equal":
                rows.extend(row(i, j, html.escape(a[i]), "same") for i, j in zip(range(i1, i2), range(j1, j2)))
                continue
            removed: list[str] = []
            added: list[str] = []
            for i, j in zip_longest(range(i1, i2), range(j1, j2)):
                if tag == "replace" and i is not None and j is not None:
                    left, right = intraline(a[i], b[j])
                else:
                    left = html.escape(a[i]) if i is not None else ""
                    right = html.escape(b[j]) if j is not None else ""
                if i is not None:
                    removed.append(row(i, None, left, "del"))
                if j is not None:
                    added.append(row(None, j, right, "add"))
            rows.extend(removed + added)
    if not rows:
        return ""
    columns = '<col class="ln"><col class="ln"><col>'
    return f'<table class="diff unified"><colgroup>{columns}</colgroup><tbody>{"".join(rows)}</tbody></table>'
