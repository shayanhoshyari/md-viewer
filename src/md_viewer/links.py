"""`md-viewer links`: relative links and images that point at a missing file or heading.

Importable on its own (no server imports), so other checkers can build on `links_of` and `link_problem`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from urllib.parse import unquote, urlsplit

from md_viewer.markdown import LINE_OFFSET, parse_markdown


@dataclass(frozen=True)
class Link:
    """A relative link or image in a markdown file."""

    source: Path  # the file it's in
    line: int  # 1-based, in that file
    target: str  # as written
    path: Path  # what it points at, resolved; `source` itself for `#anchor` alone
    anchor: str  # unquoted, "" for none


@cache
def anchors_of(path: Path) -> frozenset[str]:
    """The heading ids of a markdown file, as the viewer renders them."""
    tokens, _, _ = parse_markdown(path.read_text(encoding="utf-8", errors="replace"))
    return frozenset(str(t.attrGet("id")) for t in tokens if t.type == "heading_open" and t.attrGet("id") is not None)


def links_of(path: Path) -> list[Link]:
    """Every relative link and image in a markdown file; external URLs are left out."""
    tokens, env, _ = parse_markdown(path.read_text(encoding="utf-8", errors="replace"))
    found: list[Link] = []
    for token in tokens:
        if token.map is None:
            continue
        line = token.map[0] + 1 + env[LINE_OFFSET]
        for child in token.children or ():
            if child.type in ("softbreak", "hardbreak"):
                line += 1
                continue
            target = child.attrGet("href") if child.type == "link_open" else child.attrGet("src")
            if target is None or target == "":
                continue
            target = str(target)
            parts = urlsplit(target)
            if parts.scheme or parts.netloc:
                continue
            resolved = (path.parent / unquote(parts.path)).resolve() if parts.path else path.resolve()
            found.append(Link(path, line, target, resolved, unquote(parts.fragment)))
    return found


def link_problem(link: Link) -> str | None:
    """What's wrong with a link: a missing file, or an anchor no heading in the target `.md` has."""
    if not link.path.exists():
        return f"missing file: {link.target}"
    if link.anchor and link.path.suffix.lower() == ".md" and link.anchor not in anchors_of(link.path):
        return f"missing anchor: {link.target}"
    return None


def check_links(files: list[Path], display: Callable[[Path], str] = str) -> list[str]:
    """One `path:line: problem` line per broken link."""
    problems: list[str] = []
    for path in files:
        for link in links_of(path):
            if (problem := link_problem(link)) is not None:
                problems.append(f"{display(path)}:{link.line}: {problem}")
    return problems
