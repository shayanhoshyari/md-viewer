"""Compare responses with the saved ones in goldens/. `make goldens` rewrites them."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from conftest import shas
from fastapi.testclient import TestClient

from md_viewer.app import create_app
from md_viewer.pdf import pdf_document

GOLDENS = Path(__file__).parent / "goldens"
STATIC = Path(__file__).parent.parent / "src" / "md_viewer" / "static"
UPDATE = bool(os.environ.get("MD_VIEWER_UPDATE_GOLDENS"))

# (golden name, which root, request path)
CASES = [
    ("rendered", "repo", "/doc.md"),
    ("rendered-nonum", "repo", "/nonum.md"),
    ("source-md", "repo", "/doc.md?view=source"),
    ("source-py", "repo", "/code.py"),
    ("source-makefile", "repo", "/Makefile"),
    ("raw", "repo", "/doc.md?view=raw"),
    ("diff-dirty", "repo", "/dirty.md?view=diff"),
    ("diff-clean", "repo", "/clean.md?view=diff"),
    ("diff-new", "repo", "/new.md?view=diff"),
    ("diff-py", "repo", "/code.py?view=diff"),
    ("diff-no-repo", "loose", "/alone.md?view=diff"),
    ("diff-dirty-split", "repo", "/dirty.md?view=diff&layout=split"),
    ("diff-py-rendered", "repo", "/code.py?view=diff&mode=rendered"),
    ("diff-bad-param", "repo", "/dirty.md?view=diff&base=HEAD~1"),
    ("diff-unknown-sha", "repo", "/dirty.md?view=diff&base=0123456789"),
    ("diff-history-auto", "history", "/history.md?view=diff"),
    ("diff-history-base", "history", "/history.md?view=diff&base={c1}"),
    ("diff-history-base-to", "history", "/history.md?view=diff&base={c2}&to={c4}"),
    ("diff-staged", "history", "/staged.md?view=diff&base=staged"),
    ("diff-unstaged", "history", "/staged.md?view=diff&base=unstaged&layout=split"),
    ("diff-blocks-split", "history", "/blocks.md?view=diff&mode=rendered&layout=split"),
    ("diff-blocks-unified", "history", "/blocks.md?view=diff&mode=rendered"),
    ("diff-front-matter", "history", "/front.md?view=diff&mode=rendered"),
    ("diff-commit", "history", "/sub/pair-b.md?view=diff&commit={c5}"),
    ("diff-commit-untouched", "history", "/history.md?view=diff&commit={c5}"),
    ("diff-commit-rename", "history", "/history.md?view=diff&commit={c3}"),
    ("diff-no-extension", "history", "/sub/NOTES?view=diff&commit={c5}"),
    ("raw-no-extension", "history", "/sub/NOTES?view=raw"),
    ("diff-binary", "history", "/logo.bin?view=diff&commit={c5}"),
    ("diff-commit-with-base", "history", "/history.md?view=diff&commit={c5}&base=staged"),
    ("rendered-notes", "history", "/notes.md"),
    ("diff-notes-rendered", "history", "/notes.md?view=diff&mode=rendered"),
    ("listing-root", "repo", "/"),
    ("listing-sub", "repo", "/notes/"),
    ("readme-redirect", "repo", "/docs"),
    ("binary-png", "repo", "/image.png"),
    ("binary-txt", "repo", "/notes/plain.txt"),
    ("not-found", "repo", "/missing.md"),
    ("escape-symlink", "repo", "/escape.md"),
    ("escape-dotdot", "repo", "/%2e%2e/outside.md"),
    ("static-pygments", "repo", "/_static/pygments.css"),
]


def normalize(data: bytes, roots: list[Path], commits: list[str]) -> bytes:
    for root in roots:
        data = data.replace(str(root).encode(), b"<root>")
    for number, sha in enumerate(commits, start=1):
        for prefix in (sha, sha[:12], sha[:7]):
            data = data.replace(prefix.encode(), f"<c{number}>".encode())
    return re.sub(rb"Last commit: [0-9a-f]+", b"Last commit: <sha>", data)


def check(name: str, actual: bytes) -> None:
    path = GOLDENS / name
    if UPDATE:
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(actual)
        return
    assert path.exists(), f"no golden {name}; run `make goldens`"
    assert actual == path.read_bytes(), f"{name} differs from its golden"


@pytest.mark.parametrize(("name", "which", "url"), CASES, ids=[c[0] for c in CASES])
def test_response(name: str, which: str, url: str, request: pytest.FixtureRequest) -> None:
    root: Path = request.getfixturevalue(which)
    commits = shas(root) if which == "history" else []
    url = url.format(**{f"c{number}": sha[:7] for number, sha in enumerate(commits, start=1)})
    client = TestClient(create_app(root), follow_redirects=False)
    response = client.get(url)
    head = [f"status: {response.status_code}", f"content-type: {response.headers.get('content-type', '')}"]
    if "location" in response.headers:
        head.append(f"location: {response.headers['location']}")
    data = "\n".join(head).encode() + b"\n\n" + response.content
    check(name, normalize(data, [root], commits))


@pytest.mark.parametrize(("name", "media_type"), [("style.css", "text/css"), ("client.js", "text/javascript")])
def test_static_file(name: str, media_type: str, repo: Path) -> None:
    response = TestClient(create_app(repo)).get(f"/_static/{name}")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith(media_type)
    assert response.content == (STATIC / name).read_bytes()


def test_pdf_document() -> None:
    body = '<div class="markdown-body"><h1>Title</h1><p>Body.</p></div>'
    check("pdf-document.html", pdf_document("doc.md", body, Path("sub/doc.md")).encode())
