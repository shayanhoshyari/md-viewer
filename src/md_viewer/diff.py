"""The diff view: query parameters, the git layer, and the page body."""

from __future__ import annotations

import html
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.parse import urlencode

from md_viewer.diff_blocks import rendered_diff
from md_viewer.diff_text import diff_table, unified_table

SHA_RE = re.compile(r"[0-9a-f]{7,40}")
BASES = ("auto", "uncommitted", "staged", "unstaged")
LAYOUTS = ("unified", "split")
MODES = ("text", "rendered")
HISTORY_LIMIT = 20


class BadDiffParam(ValueError):
    """A query parameter the diff view does not accept."""


@dataclass(frozen=True)
class DiffRequest:
    base: str = "auto"
    to: str = "worktree"
    layout: str = "unified"
    mode: str = "text"
    commit: str = ""

    @classmethod
    def from_query(cls, query: Mapping[str, str], *, markdown: bool) -> DiffRequest:
        base = query.get("base") or "auto"
        to = query.get("to") or "worktree"
        layout = query.get("layout") or "unified"
        mode = query.get("mode") or "text"
        commit = query.get("commit") or ""
        if base not in BASES and not SHA_RE.fullmatch(base):
            raise BadDiffParam(f"base must be one of {', '.join(BASES)} or a commit SHA, not {base!r}")
        if to != "worktree" and not SHA_RE.fullmatch(to):
            raise BadDiffParam(f"to must be worktree or a commit SHA, not {to!r}")
        if layout not in LAYOUTS:
            raise BadDiffParam(f"layout must be unified or split, not {layout!r}")
        if mode not in MODES:
            raise BadDiffParam(f"mode must be text or rendered, not {mode!r}")
        if commit and not SHA_RE.fullmatch(commit):
            raise BadDiffParam(f"commit must be a commit SHA, not {commit!r}")
        if commit and base != "auto":
            raise BadDiffParam("commit can't be combined with base")
        if not SHA_RE.fullmatch(base):
            to = "worktree"
        if not markdown:
            mode = "text"
        return cls(base, to, layout, mode, commit)

    def query(self, **changes: str) -> str:
        """`?view=diff` plus every parameter that differs from its default."""
        request = replace(self, **changes)
        if request.commit:
            request = replace(request, base="auto")
        if not SHA_RE.fullmatch(request.base):
            request = replace(request, to="worktree")
        params = {"view": "diff"}
        for name, value in vars(request).items():
            if value != getattr(DiffRequest, name):
                params[name] = value
        return "?" + urlencode(params)


def git(cwd: Path, *args: str) -> str | None:
    """Stdout of a git command, or None when it fails."""
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, encoding="utf-8", errors="replace", check=False
    )
    return result.stdout if result.returncode == 0 else None


@dataclass(frozen=True)
class Commit:
    sha: str
    short: str
    date: str
    subject: str
    path: str  # the file's repo-relative path at this commit


@dataclass(frozen=True)
class Repo:
    """A file inside a git repository: where to run git, and its path from the repo root."""

    cwd: Path
    path: str
    worktree: Path

    @classmethod
    def locate(cls, path: Path) -> Repo | None:
        prefix = git(path.parent, "rev-parse", "--show-prefix")
        if prefix is None:
            return None
        return cls(path.parent, prefix.strip() + path.name, path)

    def history(self, limit: int = HISTORY_LIMIT) -> list[Commit] | None:
        """Commits that touched the file, newest first, following renames; None when git fails."""
        out = git(
            self.cwd,
            "log",
            "--follow",
            f"-n{limit}",
            "--date=short",
            "--format=%x1e%H%x1f%h%x1f%ad%x1f%s",
            "--name-only",
            "--",
            self.worktree.name,
        )
        if out is None:
            return None
        commits = []
        for chunk in out.split("\x1e")[1:]:
            header, _, names = chunk.partition("\n")
            sha, short, date, subject = header.split("\x1f", 3)
            paths = [line for line in names.splitlines() if line]
            commits.append(Commit(sha, short, date, subject, paths[0] if paths else self.path))
        return commits

    def show(self, rev: str, path: str | None = None) -> str:
        """The file at a revision (`""` is the index); empty when it isn't there."""
        return git(self.cwd, "show", f"{rev}:{path or self.path}") or ""

    def current(self) -> str:
        return self.worktree.read_text(encoding="utf-8", errors="replace")

    def verify(self, sha: str) -> Commit | None:
        """The commit a SHA names, or None when git doesn't know it."""
        if not SHA_RE.fullmatch(sha):
            return None
        full = git(self.cwd, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}")
        if full is None or not full.strip():
            return None
        info = git(self.cwd, "log", "-1", "--date=short", "--format=%H%x1f%h%x1f%ad%x1f%s", full.strip())
        if info is None or not info.strip():
            return None
        full_sha, short, date, subject = info.rstrip("\n").split("\x1f", 3)
        return Commit(full_sha, short, date, subject, self.path)


@dataclass(frozen=True)
class DiffSides:
    label: str
    old: str
    new: str
    # What the panel highlights: uncommitted, staged, unstaged, a full commit SHA, or "" for none.
    selection: str = ""


def path_at(repo: Repo, commit: Commit, history: list[Commit]) -> str:
    """The file's repo-relative name at a commit, when the history knows it."""
    path = next((c.path for c in history if c.sha == commit.sha), None)
    if path is None:
        # Not one of the listed commits: use the name of the newest listed commit at or before it.
        for c in history:
            if git(repo.cwd, "merge-base", "--is-ancestor", c.sha, commit.sha) is not None:
                return c.path
    return path or repo.path


def at_commit(repo: Repo, commit: Commit, history: list[Commit]) -> str:
    """The file at a commit, under the name it had there."""
    return repo.show(commit.sha, path_at(repo, commit, history))


def commit_change(repo: Repo, commit: Commit, history: list[Commit]) -> DiffSides:
    """What a commit changed in the file: its first parent → the commit."""
    path = path_at(repo, commit, history)
    out = git(repo.cwd, "diff-tree", "-r", "-z", "--no-commit-id", "--name-status", "-M", "--root", commit.sha) or ""
    items = out.split("\0")
    old_path, touched, index = path, False, 0
    while index + 1 < len(items):
        status = items[index]
        if status[:1] in {"R", "C"}:
            if items[index + 2] == path:
                old_path, touched = items[index + 1], True
            index += 3
        else:
            touched = touched or items[index + 1] == path
            index += 2
    label = f"Commit {commit.short} {commit.subject}"
    if not touched:
        new = repo.show(commit.sha, path)
        return DiffSides(label, new, new, commit.sha)
    old = repo.show(f"{commit.sha}^", old_path)
    return DiffSides(label, old, repo.show(commit.sha, path), commit.sha)


def diff_sides(repo: Repo, request: DiffRequest, history: list[Commit]) -> DiffSides:
    """The two versions the request compares. Raises BadDiffParam for an unknown commit."""
    base = request.base
    if request.commit:
        commit = repo.verify(request.commit)
        if commit is None:
            raise BadDiffParam(f"commit {request.commit!r} is not a commit in this repository")
        return commit_change(repo, commit, history)
    if base == "auto":
        if not history:
            return DiffSides("New file, never committed", "", repo.current(), "uncommitted")
        head, current = repo.show("HEAD"), repo.current()
        if head != current:
            return DiffSides("Uncommitted changes against HEAD", head, current, "uncommitted")
        last = history[0]
        parent_path = history[1].path if len(history) > 1 else last.path
        old = repo.show(f"{last.sha}^", parent_path)
        label = f"No uncommitted changes. Last commit: {last.short} {last.subject}"
        return DiffSides(label, old, head, last.sha)
    if base == "uncommitted":
        label = "Uncommitted changes: HEAD → working tree"
        return DiffSides(label, repo.show("HEAD"), repo.current(), "uncommitted")
    if base == "staged":
        return DiffSides("Staged changes: HEAD → index", repo.show("HEAD"), repo.show(""), "staged")
    if base == "unstaged":
        return DiffSides("Unstaged changes: index → working tree", repo.show(""), repo.current(), "unstaged")
    old_commit = repo.verify(base)
    if old_commit is None:
        raise BadDiffParam(f"base {base!r} is not a commit in this repository")
    old = at_commit(repo, old_commit, history)
    if request.to == "worktree":
        return DiffSides(f"{old_commit.short} {old_commit.subject} → working tree", old, repo.current())
    new_commit = repo.verify(request.to)
    if new_commit is None:
        raise BadDiffParam(f"to {request.to!r} is not a commit in this repository")
    new = at_commit(repo, new_commit, history)
    return DiffSides(f"{old_commit.short} {old_commit.subject} → {new_commit.short} {new_commit.subject}", old, new)


def controls(request: DiffRequest, *, markdown: bool) -> str:
    """The bar above the diff: layout and mode toggles."""
    toggles = [("layout", [("unified", "Unified"), ("split", "Split")])]
    if markdown:
        toggles.append(("mode", [("text", "Text"), ("rendered", "Rendered")]))
    parts = ['<div class="diff-controls">']
    for name, choices in toggles:
        links = []
        for value, label in choices:
            active = ' class="active"' if getattr(request, name) == value else ""
            links.append(f'<a href="{html.escape(request.query(**{name: value}))}"{active}>{label}</a>')
        parts.append(f'<span class="toggle">{"".join(links)}</span>')
    parts.append("</div>")
    return "".join(parts)


@dataclass(frozen=True)
class DiffPage:
    body: str
    status: int = 200
    # Set inside a repository, for the source control panel.
    repo: Repo | None = None
    request: DiffRequest | None = None
    selection: str = ""


def render_diff(
    path: Path, query: Mapping[str, str] | None = None, *, markdown: bool = False, binary: bool = False
) -> DiffPage:
    """The diff page body and status, plus what the source control panel needs."""
    try:
        request = DiffRequest.from_query(query or {}, markdown=markdown)
    except BadDiffParam as error:
        return DiffPage(f'<p class="diff-label">{html.escape(str(error))}</p>', 400)
    repo = Repo.locate(path)
    history = repo.history() if repo else None
    if repo is None or history is None:
        return DiffPage('<p class="diff-label">Not in a git repository.</p>')
    if binary:
        selection = request.base if request.base in {"uncommitted", "staged", "unstaged"} else ""
        if request.commit:
            commit = repo.verify(request.commit)
            selection = commit.sha if commit else ""
        note = '<p class="diff-label">Binary file: no text diff.</p>'
        return DiffPage(note, 200, repo, request, selection)
    try:
        sides = diff_sides(repo, request, history)
    except BadDiffParam as error:
        return DiffPage(f'<p class="diff-label">{html.escape(str(error))}</p>', 400)
    bar = controls(request, markdown=markdown)
    label = f'<p class="diff-label">{html.escape(sides.label)}</p>'
    if sides.old == sides.new:
        note = '<p class="diff-label">This file has no changes here. Pick a changed file in the panel on the right.</p>'
        return DiffPage(bar + label + note, 200, repo, request, sides.selection)
    if request.mode == "rendered":
        rendered = rendered_diff(sides.old, sides.new, request.layout)
        return DiffPage(bar + label + rendered, 200, repo, request, sides.selection)
    table = unified_table if request.layout == "unified" else diff_table
    body = table(sides.old, sides.new) or '<p class="diff-label">No line changes.</p>'
    return DiffPage(bar + label + body, 200, repo, request, sides.selection)
