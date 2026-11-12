"""Notes: the line format, where a new note goes, the notes-only rule, and the POST endpoint."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from md_viewer.app import create_app
from md_viewer.markdown import LINE_OFFSET, note_targets, parse_markdown
from md_viewer.notes import NoteError, Target, add_note, delete_note, edit_note, format_note, parse_note, version

ORIGIN = "http://127.0.0.1:8123"


@pytest.mark.parametrize(
    ("text", "quote"),
    [("plain", ""), ('say "hi" -->', 'a "quoted" \\ bit'), ("multi\nline\n\ttext", "two\nlines")],
)
def test_format_round_trip(text: str, quote: str) -> None:
    line = format_note(text, quote, "  ")
    assert "\n" not in line and line.count("-->") == 1
    note = parse_note(line)
    assert note is not None
    assert note.indent == "  "
    assert note.text == " ".join(text.split()).replace("-->", "-- >")
    assert note.quote == " ".join(quote.split())


@pytest.mark.parametrize(
    "line",
    ["<!-- section-numbers: false -->", "<!-- notes: x -->", "text <!-- note: x -->", "<!-- note: x --> text"],
)
def test_not_notes(line: str) -> None:
    assert parse_note(line) is None


def targets(text: str) -> list[Target]:
    tokens, env, source = parse_markdown(text)
    return [target for _, _, target in note_targets(tokens, source, env[LINE_OFFSET])]


def insert_into(text: str, block: int) -> str:
    return add_note(text, targets(text)[block], "N")


@pytest.mark.parametrize(
    ("text", "block", "expected"),
    [
        ("# T\n\npara one\npara two\n\nnext\n", 1, "# T\n\npara one\npara two\n<!-- note: N -->\n\nnext\n"),
        ("# T\n\nnext\n", 0, "# T\n<!-- note: N -->\n\nnext\n"),
        ("| a |\n| - |\n| 1 |\n\nx\n", 0, "| a |\n| - |\n| 1 |\n<!-- note: N -->\n\nx\n"),
        ("```py\nx\n```\n", 0, "```py\nx\n```\n<!-- note: N -->\n"),
        ("> [!NOTE]\n> hi\n\nx\n", 0, "> [!NOTE]\n> hi\n<!-- note: N -->\n\nx\n"),
        ("- a\n- b\n", 0, "- a\n  <!-- note: N -->\n- b\n"),
        ("10. a\n\n10. b\n", 0, "10. a\n    <!-- note: N -->\n\n10. b\n"),
        ("p\n<!-- note: old -->\n\nx\n", 0, "p\n<!-- note: old -->\n<!-- note: N -->\n\nx\n"),
        ("- a\n  <!-- note: old -->\n- b\n", 0, "- a\n  <!-- note: old -->\n  <!-- note: N -->\n- b\n"),
        ("---\nt: 1\n---\n# T\n\np\n", 1, "---\nt: 1\n---\n# T\n\np\n<!-- note: N -->\n"),
        ("# T\r\n\r\np\r\n", 1, "# T\r\n\r\np\r\n<!-- note: N -->\r\n"),
        ("# T\n\np", 1, "# T\n\np\n<!-- note: N -->"),
    ],
)
def test_add_positions(text: str, block: int, expected: str) -> None:
    assert insert_into(text, block) == expected


def test_list_stays_one_list() -> None:
    text = insert_into("1. a\n2. b\n3. c\n", 1)
    tokens, _, _ = parse_markdown(text)
    assert [t.type for t in tokens].count("ordered_list_open") == 1


def test_raw_html_takes_no_notes() -> None:
    assert len(targets("<div>x</div>\n\npara\n")) == 1


def test_edit_and_delete() -> None:
    text = 'p\n  <!-- note "q": old -->\n'
    assert edit_note(text, 2, "new") == 'p\n  <!-- note "q": new -->\n'
    assert delete_note(text, 2) == "p\n"
    with pytest.raises(NoteError):
        delete_note(text, 1)
    with pytest.raises(NoteError):
        edit_note(text, 9, "x")


@pytest.fixture
def site(tmp_path: Path) -> Path:
    (tmp_path / "doc.md").write_text("# Doc\n\nFirst paragraph.\n<!-- note: existing -->\n\n- item\n")
    (tmp_path / "code.py").write_text("x = 1\n")
    return tmp_path


def post(root: Path, body: dict, **headers: str):  # noqa: ANN201
    client = TestClient(create_app(root), base_url=ORIGIN)
    return client.post("/_notes", json=body, headers={"Origin": ORIGIN, **headers})


def current(root: Path, name: str = "doc.md") -> str:
    return version((root / name).read_bytes())


def test_post_add_edit_delete(site: Path) -> None:
    doc = site / "doc.md"
    add = {"path": "doc.md", "version": current(site), "op": "add", "block": 2, "text": "fix", "quote": "item"}
    r = post(site, add)
    assert r.status_code == 200, r.text
    assert r.json()["version"] == current(site)
    assert doc.read_text().endswith('- item\n  <!-- note "item": fix -->\n')
    r = post(site, {"path": "doc.md", "version": current(site), "op": "edit", "line": 4, "text": "changed"})
    assert r.status_code == 200, r.text
    assert "<!-- note: changed -->" in doc.read_text()
    r = post(site, {"path": "doc.md", "version": current(site), "op": "delete", "line": 4})
    assert r.status_code == 200, r.text
    assert doc.read_text() == '# Doc\n\nFirst paragraph.\n\n- item\n  <!-- note "item": fix -->\n'


def test_post_refusals(site: Path) -> None:
    before = (site / "doc.md").read_bytes()
    ok = {"path": "doc.md", "version": current(site), "op": "delete", "line": 4}
    assert post(site, {**ok, "version": "stale"}).status_code == 409
    assert post(site, ok, Origin="http://evil.example").status_code == 403
    client = TestClient(create_app(site), base_url=ORIGIN)
    assert client.post("/_notes", json=ok).status_code == 403  # no Origin
    rebound = TestClient(create_app(site), base_url="http://evil.example:8123")
    assert rebound.post("/_notes", json=ok, headers={"Origin": "http://evil.example:8123"}).status_code == 403
    form = client.post("/_notes", content="{}", headers={"Origin": ORIGIN, "Content-Type": "text/plain"})
    assert form.status_code == 415
    assert post(site, {**ok, "line": 3}).status_code == 400  # not a note
    assert post(site, {**ok, "op": "add", "block": 9, "text": "x"}).status_code == 400
    assert post(site, {**ok, "op": "add", "block": 0, "text": "  "}).status_code == 400
    assert post(site, {**ok, "path": "../outside.md"}).status_code == 404
    assert post(site, {**ok, "path": "code.py", "version": current(site, "code.py")}).status_code == 400
    assert (site / "doc.md").read_bytes() == before


def test_rendered_page_carries_version(site: Path) -> None:
    page = TestClient(create_app(site)).get("/doc.md").text
    assert f'data-notes-version="{current(site)}"' in page
    assert '<aside class="md-note" data-note-line="4">' in page
    assert 'data-block="2"' in page
