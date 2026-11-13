from __future__ import annotations

from pathlib import Path

import pytest

from md_viewer.cli import NotesTarget, Target, main, notes_report, parse_args


def serve(argv: list[str]) -> Target:
    target = parse_args(["serve", *argv])
    assert isinstance(target, Target)
    return target


def test_folder_serves_itself(tmp_path: Path) -> None:
    target = serve([str(tmp_path)])
    assert target.root == tmp_path.resolve()
    assert target.url_line(8123) == f"serving {tmp_path.resolve()} at http://127.0.0.1:8123/"


def test_file_serves_parent_and_links_the_file(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("# hi\n")
    target = serve([str(tmp_path / "notes.md"), "--port", "9000"])
    assert target.root == tmp_path.resolve()
    assert target.port == 9000
    assert target.url_line(9000).endswith("http://127.0.0.1:9000/notes.md")


def test_file_name_is_url_quoted(tmp_path: Path) -> None:
    (tmp_path / "my notes #1.md").write_text("# hi\n")
    assert serve([str(tmp_path / "my notes #1.md")]).page_path == "my%20notes%20%231.md"


def test_default_is_current_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert serve([]).root == tmp_path.resolve()


def test_missing_path_is_a_usage_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        parse_args(["serve", str(tmp_path / "nope.md")])
    assert exc.value.code == 2
    assert "does not exist" in capsys.readouterr().err


def test_a_command_is_required(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        parse_args([])
    assert exc.value.code == 2


NOTED = """# T

Intro para
second line
<!-- note: tighten -->

- a
- b
  <!-- note "b": why b -->

| x | y |
| - | - |
| 1 | 2 |
<!-- note: on the table -->
"""


def test_notes_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.md").write_text(NOTED)
    assert notes_report([Path("a.md")]) == (
        "a.md:5  paragraph, lines 3-4\n  > Intro para\n  > second line\n  note: tighten\n\n"
        "a.md:9  list item, line 8\n  > - b\n  quote: b\n  note: why b\n\n"
        "a.md:14  table, lines 11-13\n  > | x | y |\n  > | - | - |\n  > | 1 | 2 |\n  note: on the table"
    )


def test_notes_report_top_of_file_and_long_blocks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    code = "\n".join(f"line {n}" for n in range(20))
    (tmp_path / "a.md").write_text(f"<!-- note: first -->\n\n```\n{code}\n```\n<!-- note: long -->\n")
    report = notes_report([Path("a.md")])
    assert report.startswith("a.md:1  top of file\n  note: first\n\na.md:25  code block, lines 3-24\n")
    assert "  > … 7 more lines\n  note: long" in report


def test_notes_on_a_folder_skip_hidden_and_excluded(tmp_path: Path) -> None:
    for rel in ["b.md", "sub/a.md", ".hidden/x.md", ".venv/y.md", ".claude/z.md", "sub/c.txt"]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("<!-- note: n -->\n")
    target = parse_args(["notes", str(tmp_path)])
    assert isinstance(target, NotesTarget)
    assert [p.relative_to(tmp_path).as_posix() for p in target.files] == [".claude/z.md", "b.md", "sub/a.md"]


def test_notes_command_prints_nothing_without_notes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a.md").write_text("# T\n\n<!-- not a note -->\n")
    assert main(["notes", str(tmp_path / "a.md")]) == 0
    assert capsys.readouterr().out == ""


def test_notes_in_code_blocks_are_not_notes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.md").write_text("```markdown\n<!-- note: example -->\n```\n\n    <!-- note: indented code -->\n")
    assert notes_report([Path("a.md")]) == ""


def test_notes_report_on_a_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "a.md").write_text("# T\n\n| a | b |\n| - | - |\n| 1 | 2 |\n| 3 | 4 | <!-- note: x \\| y -->\n")
    assert notes_report([Path("a.md")]) == ("a.md:6  table row, line 6\n  > | a | b |\n  > | 3 | 4 |\n  note: x | y")
