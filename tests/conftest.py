"""Fixture folder copied into a git repo with fixed history, plus TestClients for the app."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

FIXTURE = Path(__file__).parent / "fixture"
GIT_ENV = {
    "GIT_AUTHOR_NAME": "Fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.com",
    "GIT_COMMITTER_NAME": "Fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.com",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_NOSYSTEM": "1",
}


def git(cwd: Path, *args: str, date: str = "2026-01-01T00:00:00Z") -> None:
    env = {**os.environ, **GIT_ENV, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "init.defaultBranch=main", *args],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
    )


@pytest.fixture(scope="session")
def repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The fixture as a repo: two commits, then dirty.md edited, new.md never committed, a link out."""
    root = tmp_path_factory.mktemp("repo") / "site"
    shutil.copytree(FIXTURE, root)
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "Add fixture")
    clean = root / "clean.md"
    clean.write_text(clean.read_text().replace("changed this line", "changed this line, here"))
    git(root, "commit", "-q", "-am", "Edit clean.md", date="2026-01-02T00:00:00Z")
    dirty = root / "dirty.md"
    dirty.write_text(dirty.read_text().replace("will be edited", "was edited"))
    (root / "new.md").write_text("# New\n\nNever committed.\n")
    outside = root.parent / "outside.md"
    outside.write_text("# Outside the root\n")
    (root / "escape.md").symlink_to(outside)
    return root


@pytest.fixture(scope="session")
def loose(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A folder outside any git repository."""
    root = tmp_path_factory.mktemp("loose")
    (root / "alone.md").write_text("# Alone\n\nNot in git.\n")
    return root


HISTORY = Path(__file__).parent / "history"


@pytest.fixture(scope="session")
def history(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A repo with history: a file renamed on the way, staged and unstaged edits, a block-level markdown edit."""
    root = tmp_path_factory.mktemp("history") / "site"
    root.mkdir()
    git(root, "init", "-q")

    def version(n: int) -> str:
        lines = [f"Line {i} of the history file." for i in range(1, 6)]
        lines[n - 1] = f"Line {n} was changed in version {n}."
        return "# History\n\n" + "\n".join(lines) + "\n"

    old = root / "old-history.md"
    old.write_text(version(1))
    (root / "staged.md").write_text("# Staged\n\nFirst line.\nSecond line.\nThird line.\n")
    (root / "blocks.md").write_text((HISTORY / "blocks-old.md").read_text())
    (root / "front.md").write_text("---\ntitle: Old\n---\n# Front\n\nBody.\n")
    (root / "notes.md").write_text((HISTORY / "notes-old.md").read_text())
    (root / "sub").mkdir()
    (root / "pair-a.md").write_text("# Pair A\n\nBefore.\n")
    (root / "sub" / "pair-b.md").write_text("# Pair B\n\nBefore.\n")
    (root / "sub" / "NOTES").write_text("Plain text without an extension.\nBefore.\n")
    (root / "logo.bin").write_bytes(b"\x89BIN\x00\x01before")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "Add history files", date="2026-02-01T00:00:00Z")
    old.write_text(version(2))
    git(root, "commit", "-q", "-am", "History v2", date="2026-02-02T00:00:00Z")
    git(root, "mv", "old-history.md", "history.md")
    (root / "history.md").write_text(version(3))
    git(root, "commit", "-q", "-am", "Rename to history.md, v3", date="2026-02-03T00:00:00Z")
    (root / "history.md").write_text(version(4))
    git(root, "commit", "-q", "-am", "History v4", date="2026-02-04T00:00:00Z")
    (root / "pair-a.md").write_text("# Pair A\n\nAfter.\n")
    (root / "sub" / "pair-b.md").write_text("# Pair B\n\nAfter.\n")
    (root / "sub" / "NOTES").write_text("Plain text without an extension.\nAfter.\n")
    (root / "logo.bin").write_bytes(b"\x89BIN\x00\x01after")
    git(root, "commit", "-q", "-am", "Edit both pair files", date="2026-02-05T00:00:00Z")

    staged = root / "staged.md"
    staged.write_text("# Staged\n\nFirst line.\nSecond line, staged.\nThird line.\n")
    git(root, "add", "staged.md")
    staged.write_text("# Staged\n\nFirst line.\nSecond line, staged.\nThird line, unstaged.\n")
    (root / "blocks.md").write_text((HISTORY / "blocks-new.md").read_text())
    (root / "front.md").write_text("---\ntitle: New\n---\n# Front\n\nBody.\n")
    (root / "notes.md").write_text((HISTORY / "notes-new.md").read_text())
    return root


def shas(root: Path) -> list[str]:
    """Full SHAs of the repo's commits, oldest first."""
    out = subprocess.run(["git", "log", "--reverse", "--format=%H"], cwd=root, capture_output=True, text=True)
    return out.stdout.split()
