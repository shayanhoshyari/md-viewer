from __future__ import annotations

from pathlib import Path

import pytest

from md_viewer.cli import parse_args


def test_folder_serves_itself(tmp_path: Path) -> None:
    target = parse_args([str(tmp_path)])
    assert target.root == tmp_path.resolve()
    assert target.url_line(8123) == f"serving {tmp_path.resolve()} at http://127.0.0.1:8123/"


def test_file_serves_parent_and_links_the_file(tmp_path: Path) -> None:
    (tmp_path / "notes.md").write_text("# hi\n")
    target = parse_args([str(tmp_path / "notes.md"), "--port", "9000"])
    assert target.root == tmp_path.resolve()
    assert target.port == 9000
    assert target.url_line(9000).endswith("http://127.0.0.1:9000/notes.md")


def test_file_name_is_url_quoted(tmp_path: Path) -> None:
    (tmp_path / "my notes #1.md").write_text("# hi\n")
    assert parse_args([str(tmp_path / "my notes #1.md")]).page_path == "my%20notes%20%231.md"


def test_default_is_current_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert parse_args([]).root == tmp_path.resolve()


def test_missing_path_is_a_usage_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        parse_args([str(tmp_path / "nope.md")])
    assert exc.value.code == 2
    assert "does not exist" in capsys.readouterr().err
