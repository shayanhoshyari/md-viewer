"""`md-viewer links`: relative links and images to missing files or headings."""

from __future__ import annotations

from pathlib import Path

import pytest

from md_viewer.cli import LinksTarget, main, parse_args
from md_viewer.links import check_links, links_of

DOC = """---
title: front matter shifts the lines
---
# Top

## Second part

[good](other.md#a-heading) [same file](#second-part) [folder](sub/) ![img](pic.png)
[web](https://example.com/missing) [mail](mailto:a@b.c) [non-md anchor](notes.txt#nowhere)
[no file](gone.md)
[no anchor](other.md#nope)
[no local anchor](#nope)
[quoted](my%20file.md)

```markdown
[in code](not-a-link.md)
```
"""


@pytest.fixture
def site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "doc.md").write_text(DOC)
    (tmp_path / "other.md").write_text("# A heading\n")
    (tmp_path / "my file.md").write_text("x\n")
    (tmp_path / "notes.txt").write_text("x\n")
    (tmp_path / "pic.png").write_bytes(b"")
    (tmp_path / "sub").mkdir()
    return tmp_path


def test_problems(site: Path) -> None:
    assert check_links([Path("doc.md")]) == [
        "doc.md:10: missing file: gone.md",
        "doc.md:11: missing anchor: other.md#nope",
        "doc.md:12: missing anchor: #nope",
    ]


def test_external_and_code_are_not_links(site: Path) -> None:
    targets = [link.target for link in links_of(Path("doc.md"))]
    assert "https://example.com/missing" not in targets and "mailto:a@b.c" not in targets
    assert "not-a-link.md" not in targets
    assert "pic.png" in targets


def test_command_on_a_folder(site: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (site / "sub" / "deep.md").write_text("[up](../gone.md)\n")
    target = parse_args(["links"])
    assert isinstance(target, LinksTarget)
    assert main(["links"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "doc.md:10: missing file: gone.md"
    assert out[-1] == "sub/deep.md:1: missing file: ../gone.md"


def test_command_without_problems(site: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["links", "other.md"]) == 0
    assert capsys.readouterr().out == ""
