from __future__ import annotations

from pathlib import Path

import pytest

from md_viewer.cli import NotesTarget, Target, main, notes_report, parse_args
from md_viewer.registry import Server


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


def test_notes_on_a_folder_skip_dot_folders_but_kept_ones(tmp_path: Path) -> None:
    for rel in [
        "b.md",
        "sub/a.md",
        "sub/.draft.md",
        ".hidden/x.md",
        ".venv/y.md",
        ".claude/z.md",
        ".agents/w.md",
        "sub/c.txt",
    ]:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("<!-- note: n -->\n")
    target = parse_args(["notes", str(tmp_path)])
    assert isinstance(target, NotesTarget)
    assert [p.relative_to(tmp_path).as_posix() for p in target.files] == [
        ".agents/w.md",
        ".claude/z.md",
        "b.md",
        "sub/.draft.md",
        "sub/a.md",
    ]


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


def test_restart_reuses_the_target_and_bound_port(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("# hi\n")
    argv = serve([str(tmp_path / "notes.md")]).restart_argv(8123)
    assert argv[1:] == [
        "-m",
        "md_viewer",
        "serve",
        str(tmp_path.resolve() / "notes.md"),
        "--host",
        "127.0.0.1",
        "--port",
        "8123",
    ]


def test_restart_command_reports_each_server(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    servers = [Server(id="a", port=1, root="/a", pid=11), Server(id="b", port=2, root="/b", pid=12)]
    monkeypatch.setattr("md_viewer.cli.live_servers", lambda _: servers)
    monkeypatch.setattr("md_viewer.cli.restart", lambda s: None if s.id == "a" else "no answer within 15 s")
    assert main(["restart"]) == 1
    assert capsys.readouterr().out == "restarted /a  http://127.0.0.1:1/\nfailed /b: no answer within 15 s\n"


def test_restart_command_without_servers(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("md_viewer.cli.live_servers", lambda _: [])
    assert main(["restart"]) == 0
    assert capsys.readouterr().out == ""


def test_list_command_prints_a_table(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    servers = [
        Server(id="a", port=1, root="/a", pid=4321),
        Server(id="b", port=8000, root=str(Path.home() / "notes"), pid=99),
    ]
    monkeypatch.setattr("md_viewer.cli.live_servers", lambda _: servers)
    assert main(["list"]) == 0
    rows = [line.split() for line in capsys.readouterr().out.splitlines() if line.strip() and "─" not in line]
    assert rows == [
        ["Path", "Port", "PID", "URL"],
        ["/a", "1", "4321", "http://127.0.0.1:1/"],
        ["~/notes", "8000", "99", "http://127.0.0.1:8000/"],
    ]


def test_list_command_without_servers(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("md_viewer.cli.live_servers", lambda _: [])
    assert main(["list"]) == 0
    assert capsys.readouterr().out == ""


def md_files(path: Path) -> list[str]:
    target = parse_args(["notes", str(path)])
    assert isinstance(target, NotesTarget)
    return [p.relative_to(path).as_posix() for p in target.files]


@pytest.fixture
def no_global_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the machine's global git excludes file out of the walk."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "home" / ".config"))


def write(root: Path, *rels: str) -> None:
    for rel in rels:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text("<!-- note: n -->\n")


def test_folder_walk_honors_a_parent_ignore_file(tmp_path: Path, no_global_git: None) -> None:
    root = tmp_path / "repo"
    write(root, "x/plans/archive/a.md", "x/plans/b.md", "c.md")
    (root / ".ignore").write_text("archive/\n")
    assert md_files(root) == ["c.md", "x/plans/b.md"]
    assert md_files(root / "x" / "plans") == ["b.md"]


def test_folder_walk_honors_gitignore_inside_a_repository(tmp_path: Path, no_global_git: None) -> None:
    root = tmp_path / "repo"
    write(root, "kept.md", "built/out.md")
    (root / ".gitignore").write_text("built/\n")
    assert md_files(root) == ["built/out.md", "kept.md"]
    (root / ".git").mkdir()
    assert md_files(root) == ["kept.md"]


def test_single_file_is_checked_even_when_ignored(tmp_path: Path, no_global_git: None) -> None:
    write(tmp_path, "archive/a.md")
    (tmp_path / ".ignore").write_text("archive/\n")
    target = parse_args(["notes", str(tmp_path / "archive" / "a.md")])
    assert isinstance(target, NotesTarget)
    assert target.files == [tmp_path / "archive" / "a.md"]
