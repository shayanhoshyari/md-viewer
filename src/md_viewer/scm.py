"""The source control panel beside the diff: changed files on top, selections and commits below."""

from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from md_viewer.diff import DiffRequest, Repo, git

COMMIT_LIMIT = 50
STATUS_NAMES = {"M": "modified", "A": "added", "D": "deleted", "R": "renamed", "C": "copied", "U": "untracked"}


@dataclass(frozen=True)
class Change:
    status: str  # one letter: M, A, D, R, C, U, or T for a type change
    path: str  # root-relative, POSIX


@dataclass(frozen=True)
class Scope:
    """Where the served root sits in the repository, so git's paths can be shown root-relative."""

    top: Path
    root: Path

    @classmethod
    def find(cls, repo: Repo, root: Path) -> Scope | None:
        top = git(repo.cwd, "rev-parse", "--show-toplevel")
        if top is None or not top.strip():
            return None
        return cls(Path(top.strip()).resolve(), root.resolve())

    @property
    def pathspec(self) -> str:
        """The root as a pathspec from the top of the repo, or the whole repo when the root contains it."""
        try:
            return self.root.relative_to(self.top).as_posix() or "."
        except ValueError:
            return "."

    def relative(self, repo_path: str) -> str | None:
        """A repo-relative path as a root-relative one, or None when it is outside the root."""
        try:
            return (self.top / repo_path).relative_to(self.root).as_posix()
        except ValueError:
            return None

    def git(self, *args: str) -> str:
        return git(self.top, *args) or ""


def parse_name_status(out: str, scope: Scope) -> list[Change]:
    """Changes from `git diff --name-status -z` output, limited to the root."""
    items = out.split("\0")
    changes: list[Change] = []
    index = 0
    while index + 1 < len(items):
        status = items[index][:1]
        if status in {"R", "C"}:
            path, index = items[index + 2], index + 3
        else:
            path, index = items[index + 1], index + 2
        rel = scope.relative(path)
        if rel is not None:
            changes.append(Change(status, rel))
    return changes


def untracked(scope: Scope) -> list[Change]:
    out = scope.git("ls-files", "-z", "--others", "--exclude-standard", "--full-name", "--", scope.pathspec)
    return [Change("U", rel) for path in out.split("\0") if path and (rel := scope.relative(path)) is not None]


def changes_for(scope: Scope, selection: str) -> list[Change]:
    """The files a selection changed under the root, sorted by path."""
    spec = ("--", scope.pathspec)
    if selection == "uncommitted":
        found = parse_name_status(scope.git("diff", "-z", "--name-status", "-M", "HEAD", *spec), scope)
        found += untracked(scope)
    elif selection == "staged":
        found = parse_name_status(scope.git("diff", "-z", "--name-status", "-M", "--cached", *spec), scope)
    elif selection == "unstaged":
        found = parse_name_status(scope.git("diff", "-z", "--name-status", *spec), scope) + untracked(scope)
    elif selection:
        args = ("diff-tree", "-r", "-z", "--no-commit-id", "--name-status", "-M", "--root", selection, *spec)
        found = parse_name_status(scope.git(*args), scope)
    else:
        found = []
    return sorted(found, key=lambda change: change.path.lower())


@dataclass(frozen=True)
class LogEntry:
    sha: str
    short: str
    date: str
    subject: str


def commits(scope: Scope, limit: int = COMMIT_LIMIT) -> list[LogEntry]:
    out = scope.git("log", f"-n{limit}", "--date=short", "--format=%H%x1f%h%x1f%ad%x1f%s", "--", scope.pathspec)
    return [LogEntry(*line.split("\x1f", 3)) for line in out.splitlines() if line.count("\x1f") >= 3]


def selection_request(request: DiffRequest, selection: str) -> DiffRequest:
    if selection in {"uncommitted", "staged", "unstaged"}:
        return DiffRequest(base=selection, layout=request.layout, mode=request.mode)
    return DiffRequest(commit=selection[:12], layout=request.layout, mode=request.mode)


def href(rel: str, request: DiffRequest) -> str:
    return "/" + quote(rel) + request.query()


def file_item(change: Change, current: str, request: DiffRequest) -> str:
    path = PurePosixPath(change.path)
    title = html.escape(f"{change.path} ({STATUS_NAMES.get(change.status, change.status)})")
    inner = (
        f'<span class="scm-name">{html.escape(path.name)}</span>'
        f'<span class="scm-status scm-{html.escape(change.status)}">{html.escape(change.status)}</span>'
    )
    css = "current" if change.path == current else ""
    if change.status == "D":
        return f'<li><span class="scm-file deleted" title="{title}">{inner}</span></li>'
    link = html.escape(href(change.path, request))
    return f'<li><a class="scm-file {css}" href="{link}" title="{title}">{inner}</a></li>'


@dataclass
class Folder:
    folders: dict[str, Folder]
    files: list[Change]


def file_tree(changes: list[Change]) -> Folder:
    tree = Folder({}, [])
    for change in changes:
        node = tree
        for part in PurePosixPath(change.path).parts[:-1]:
            node = node.folders.setdefault(part, Folder({}, []))
        node.files.append(change)
    return tree


def tree_items(node: Folder, current: str, request: DiffRequest) -> str:
    """Folders first, then files, both by name. A folder holding only one folder shows as `a/b`, as in VS Code."""
    items: list[str] = []
    for name in sorted(node.folders, key=str.lower):
        child, label = node.folders[name], name
        while len(child.folders) == 1 and not child.files:
            ((inner_name, child),) = child.folders.items()
            label += "/" + inner_name
        inner = tree_items(child, current, request)
        summary = f"<summary>{html.escape(label)}</summary>"
        items.append(f'<li class="scm-folder"><details open>{summary}<ul>{inner}</ul></details></li>')
    for change in sorted(node.files, key=lambda c: PurePosixPath(c.path).name.lower()):
        items.append(file_item(change, current, request))
    return "".join(items)


def source_control_panel(repo: Repo, root: Path, file: Path, request: DiffRequest, selection: str) -> str:
    """The right-hand panel. `selection` is what the diff shows: a mode name, a full SHA, or ""."""
    scope = Scope.find(repo, root)
    if scope is None:
        return ""
    current = file.resolve().relative_to(scope.root).as_posix()
    log = commits(scope)
    titles = {"uncommitted": "Uncommitted", "staged": "Staged", "unstaged": "Unstaged"}
    selected_title = titles.get(selection) or next(
        (entry.subject for entry in log if entry.sha == selection), selection[:7] or "nothing selected"
    )
    files = changes_for(scope, selection)
    keep = selection_request(request, selection) if selection else request
    file_items = tree_items(file_tree(files), current, keep) or '<li class="scm-empty">No changes</li>'

    def choice(value: str, label: str, detail: str) -> str:
        css = "scm-choice current" if value == selection else "scm-choice"
        link = html.escape(href(current, selection_request(request, value)))
        return (
            f'<li><a class="{css}" href="{link}"><span class="scm-subject">{html.escape(label)}</span>'
            f'<span class="scm-detail">{html.escape(detail)}</span></a></li>'
        )

    modes = []
    for value, label in titles.items():
        count = len(changes_for(scope, value))
        modes.append(choice(value, label, f"{count} file" + ("" if count == 1 else "s")))
    commit_items = "".join(choice(entry.sha, entry.subject, f"{entry.short} · {entry.date}") for entry in log)
    return (
        '<aside class="scm">'
        f'<section class="scm-files"><h2>Changes <span class="scm-detail">{html.escape(selected_title)}</span></h2>'
        f"<ul>{file_items}</ul></section>"
        '<section class="scm-choices"><h2>Source control</h2>'
        f"<ul>{''.join(modes)}</ul><h2>Commits</h2><ul>{commit_items}</ul></section>"
        "</aside>"
    )
