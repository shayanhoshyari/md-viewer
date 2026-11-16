"""The Edit view and `PUT /_file`."""

from __future__ import annotations

import html
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from md_viewer.app import create_app
from md_viewer.notes import version

ORIGIN = "http://127.0.0.1:8123"


@pytest.fixture
def site(tmp_path: Path) -> Path:
    (tmp_path / "doc.md").write_text("\n# Doc <&>\n\nBody.\n")
    (tmp_path / "code.py").write_text("x = 1\n")
    return tmp_path


def current(root: Path, name: str = "doc.md") -> str:
    return version((root / name).read_bytes())


def put(root: Path, body: dict, **headers: str):  # noqa: ANN201
    client = TestClient(create_app(root), base_url=ORIGIN)
    return client.put("/_file", json=body, headers={"Origin": ORIGIN, **headers})


def test_edit_page(site: Path) -> None:
    page = TestClient(create_app(site)).get("/doc.md?view=edit").text
    # One newline after the tag, which the parser drops, so the file's leading blank line survives.
    assert f'data-version="{current(site)}" spellcheck="false">\n{html.escape(chr(10) + "# Doc <&>")}' in page
    assert '<a href="/doc.md?view=edit" class="active">Edit</a>' in page
    assert "?view=edit" not in TestClient(create_app(site)).get("/code.py").text


def test_save(site: Path) -> None:
    r = put(site, {"path": "doc.md", "version": current(site), "text": "# New\n\nText"})
    assert r.status_code == 200, r.text
    assert (site / "doc.md").read_text() == "# New\n\nText"
    assert r.json()["version"] == current(site)


def test_crlf_kept(site: Path) -> None:
    doc = site / "doc.md"
    doc.write_bytes(b"# Doc\r\n\r\nBody.\r\n")
    r = put(site, {"path": "doc.md", "version": current(site), "text": "# Doc\n\nNew body.\n"})
    assert r.status_code == 200, r.text
    assert doc.read_bytes() == b"# Doc\r\n\r\nNew body.\r\n"


def test_mode_kept(site: Path) -> None:
    doc = site / "doc.md"
    doc.chmod(0o600)
    assert put(site, {"path": "doc.md", "version": current(site), "text": "x\n"}).status_code == 200
    assert doc.stat().st_mode & 0o777 == 0o600


def test_refusals(site: Path) -> None:
    before = (site / "doc.md").read_bytes()
    ok = {"path": "doc.md", "version": current(site), "text": "changed\n"}
    assert put(site, {**ok, "version": "stale"}).status_code == 409
    assert put(site, ok, Origin="http://evil.example").status_code == 403
    client = TestClient(create_app(site), base_url=ORIGIN)
    assert client.put("/_file", json=ok).status_code == 403  # no Origin
    rebound = TestClient(create_app(site), base_url="http://evil.example:8123")
    assert rebound.put("/_file", json=ok, headers={"Origin": "http://evil.example:8123"}).status_code == 403
    form = client.put("/_file", content="{}", headers={"Origin": ORIGIN, "Content-Type": "text/plain"})
    assert form.status_code == 415
    assert put(site, {"path": "doc.md", "version": current(site)}).status_code == 400  # no text
    assert put(site, {**ok, "path": "../outside.md"}).status_code == 404
    assert put(site, {**ok, "path": "missing.md"}).status_code == 404
    assert put(site, {**ok, "path": "code.py", "version": current(site, "code.py")}).status_code == 400
    assert (site / "doc.md").read_bytes() == before
    assert (site / "code.py").read_text() == "x = 1\n"


def test_not_utf8(site: Path) -> None:
    (site / "latin.md").write_bytes(b"caf\xe9\n")
    page = TestClient(create_app(site)).get("/latin.md?view=edit").text
    assert "not UTF-8" in page and "<textarea" not in page
    assert put(site, {"path": "latin.md", "version": current(site, "latin.md"), "text": "x"}).status_code == 400
