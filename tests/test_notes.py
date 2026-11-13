"""Notes: the format, where a note goes, the notes-only rule, and the PUT and DELETE endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from md_viewer.app import create_app
from md_viewer.markdown import LINE_OFFSET, note_targets, parse_markdown
from md_viewer.notes import NoteError, Target, delete_note, format_note, parse_note, set_note, version

ORIGIN = "http://127.0.0.1:8123"


@pytest.mark.parametrize(
    ("text", "quote"),
    [
        ("plain", ""),
        ('say "hi" -->', 'a "quoted" \\ bit'),
        ("multi\nline\n\ttext", "two\nlines"),
        ("a | b", "c | d"),
    ],
)
@pytest.mark.parametrize("lead", ["  ", "| x | y | "])
def test_format_round_trip(text: str, quote: str, lead: str) -> None:
    line = format_note(text, quote, lead)
    assert "\n" not in line and line.count("-->") == 1
    assert "|" not in line[len(lead) :].replace("\\|", "")
    note = parse_note(line)
    assert note is not None
    assert note.lead == lead
    assert note.on_row == (lead != "  ")
    assert note.text == " ".join(text.split()).replace("-->", "-- >")
    assert note.quote == " ".join(quote.split())


@pytest.mark.parametrize(
    "line",
    [
        "<!-- section-numbers: false -->",
        "<!-- notes: x -->",
        "text <!-- note: x -->",
        "<!-- note: x --> text",
        "| a | <!-- note: x --> |",
    ],
)
def test_not_notes(line: str) -> None:
    assert parse_note(line) is None


def targets(text: str) -> list[Target]:
    tokens, env, source = parse_markdown(text)
    return [target for _, _, target in note_targets(tokens, source, env[LINE_OFFSET])]


def insert_into(text: str, block: int) -> str:
    return set_note(text, targets(text)[block], "N")


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
        ("p\n<!-- note: old -->\n\nx\n", 0, "p\n<!-- note: N -->\n\nx\n"),
        ("p\n<!-- note: a -->\n<!-- note: b -->\n", 0, "p\n<!-- note: N -->\n<!-- note: b -->\n"),
        ("- a\n  <!-- note: old -->\n- b\n", 0, "- a\n  <!-- note: N -->\n- b\n"),
        ("| a |\n| - |\n| 1 |\n| 2 |\n", 2, "| a |\n| - |\n| 1 |\n| 2 | <!-- note: N -->\n"),
        ("| a |\n| - |\n| 1 |  \n", 1, "| a |\n| - |\n| 1 |   <!-- note: N -->\n"),
        ("| a |\n| - |\n| 1 | <!-- note: old -->\n", 1, "| a |\n| - |\n| 1 | <!-- note: N -->\n"),
        (
            "| a |\n| - |\n| 1 | <!-- note: r -->\n\nx\n",
            0,
            "| a |\n| - |\n| 1 | <!-- note: r -->\n<!-- note: N -->\n\nx\n",
        ),
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


def test_table_rows_are_blocks() -> None:
    found = targets("| a | b |\n| - | - |\n| 1 | 2 |\n| 3 | 4 | <!-- note: n -->\n")
    assert [(t.index, t.row, t.note) for t in found] == [(4, False, None), (2, True, None), (3, True, 3)]


def test_row_note_keeps_the_table() -> None:
    text = insert_into("| a | b |\n| - | - |\n| 1 | 2 |\n| 3 | 4 |\n", 1)
    tokens, _, _ = parse_markdown(text)
    assert [t.type for t in tokens].count("table_open") == 1
    assert [t.type for t in tokens].count("td_open") == 4


def test_delete() -> None:
    text = 'p\n  <!-- note "q": old -->\n\n| a |\n| - |\n| 1 |  <!-- note: r -->\n'
    assert delete_note(text, targets(text)[0]) == "p\n\n| a |\n| - |\n| 1 |  <!-- note: r -->\n"
    assert delete_note(text, targets(text)[2]) == 'p\n  <!-- note "q": old -->\n\n| a |\n| - |\n| 1 | \n'
    with pytest.raises(NoteError):
        delete_note(text, targets(text)[1])  # the table has no note of its own


def test_set_needs_text() -> None:
    with pytest.raises(NoteError):
        set_note("p\n", targets("p\n")[0], "  ")


def test_only_notes_may_change() -> None:
    with pytest.raises(NoteError):
        set_note("p\n", Target(0, "", row=True), "x")  # `p` is no table row: the result is no note
    with pytest.raises(NoteError):
        delete_note("p\nq\n", Target(0, "", note=1))


@pytest.fixture
def site(tmp_path: Path) -> Path:
    (tmp_path / "doc.md").write_text("# Doc\n\nFirst paragraph.\n<!-- note: existing -->\n\n- item\n")
    (tmp_path / "code.py").write_text("x = 1\n")
    return tmp_path


def send(root: Path, method: str, body: dict, **headers: str):  # noqa: ANN201
    client = TestClient(create_app(root), base_url=ORIGIN)
    return client.request(method, "/_notes", json=body, headers={"Origin": ORIGIN, **headers})


def current(root: Path, name: str = "doc.md") -> str:
    return version((root / name).read_bytes())


def test_put_and_delete(site: Path) -> None:
    doc = site / "doc.md"
    r = send(site, "PUT", {"path": "doc.md", "version": current(site), "block": 2, "text": "fix", "quote": "item"})
    assert r.status_code == 200, r.text
    assert r.json()["version"] == current(site)
    assert doc.read_text().endswith('- item\n  <!-- note "item": fix -->\n')
    r = send(site, "PUT", {"path": "doc.md", "version": current(site), "block": 1, "text": "changed"})
    assert r.status_code == 200, r.text
    assert "<!-- note: changed -->" in doc.read_text() and "existing" not in doc.read_text()
    r = send(site, "DELETE", {"path": "doc.md", "version": current(site), "block": 1})
    assert r.status_code == 200, r.text
    assert doc.read_text() == '# Doc\n\nFirst paragraph.\n\n- item\n  <!-- note "item": fix -->\n'


def test_row_notes_over_http(site: Path) -> None:
    doc = site / "doc.md"
    doc.write_text("| a | b |\n| - | - |\n| 1 | 2 |\n")
    r = send(site, "PUT", {"path": "doc.md", "version": current(site), "block": 1, "text": "x | y"})
    assert r.status_code == 200, r.text
    assert doc.read_text() == "| a | b |\n| - | - |\n| 1 | 2 | <!-- note: x \\| y -->\n"
    page = TestClient(create_app(site)).get("/doc.md").text
    assert '<tr data-block="1" data-noted="">' in page
    assert '<tr class="md-note-row"><td colspan="2"><aside class="md-note" data-note-block="1">' in page
    assert "x | y" in page
    r = send(site, "DELETE", {"path": "doc.md", "version": current(site), "block": 1})
    assert r.status_code == 200, r.text
    assert doc.read_text() == "| a | b |\n| - | - |\n| 1 | 2 |\n"


def test_refusals(site: Path) -> None:
    before = (site / "doc.md").read_bytes()
    ok = {"path": "doc.md", "version": current(site), "block": 1}
    assert send(site, "DELETE", {**ok, "version": "stale"}).status_code == 409
    assert send(site, "DELETE", ok, Origin="http://evil.example").status_code == 403
    client = TestClient(create_app(site), base_url=ORIGIN)
    assert client.request("DELETE", "/_notes", json=ok).status_code == 403  # no Origin
    rebound = TestClient(create_app(site), base_url="http://evil.example:8123")
    headers = {"Origin": "http://evil.example:8123"}
    assert rebound.request("DELETE", "/_notes", json=ok, headers=headers).status_code == 403
    form = client.put("/_notes", content="{}", headers={"Origin": ORIGIN, "Content-Type": "text/plain"})
    assert form.status_code == 415
    assert client.post("/_notes", json=ok, headers={"Origin": ORIGIN}).status_code == 405
    assert send(site, "DELETE", {**ok, "block": 0}).status_code == 400  # no note on the heading
    assert send(site, "DELETE", {**ok, "block": 9}).status_code == 400
    assert send(site, "PUT", {**ok, "text": "  "}).status_code == 400
    assert send(site, "PUT", ok).status_code == 400  # no text
    assert send(site, "DELETE", {**ok, "path": "../outside.md"}).status_code == 404
    assert send(site, "DELETE", {**ok, "path": "code.py", "version": current(site, "code.py")}).status_code == 400
    assert (site / "doc.md").read_bytes() == before


def test_rendered_page_carries_version(site: Path) -> None:
    page = TestClient(create_app(site)).get("/doc.md").text
    assert f'data-notes-version="{current(site)}"' in page
    assert '<p data-block="1" data-noted="">' in page
    assert '<aside class="md-note" data-note-block="1">' in page
    assert 'data-block="2"' in page
