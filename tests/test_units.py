from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from md_viewer.app import create_app
from md_viewer.diff import BadDiffParam, DiffRequest
from md_viewer.diff_blocks import block_rows, cut_blocks, mark_words, render_blocks
from md_viewer.diff_text import intraline, unified_table
from md_viewer.layout import resolve_safe
from md_viewer.markdown import MD, github_slug, parse_markdown, section_numbers_enabled
from md_viewer.scm import Change, Scope, file_tree, parse_name_status, tree_items


@pytest.mark.parametrize(
    ("text", "slug"),
    [
        ("Hello World", "hello-world"),
        ("1. Setup & run!", "1-setup-run"),
        ("  Trailing  space ", "trailing-space"),
        ("Ünïcode ok", "ünïcode-ok"),
    ],
)
def test_github_slug(text: str, slug: str) -> None:
    assert github_slug(text) == slug


@pytest.mark.parametrize(
    ("source", "math"),
    [
        ("costs $5 and $200k", False),
        ("SQL uses $1 here", False),
        ("a $ b $ c", False),
        ("inline $x^2$ math", True),
        ("$$\nx\n$$", True),
    ],
)
def test_math_dollar_rules(source: str, math: bool) -> None:
    assert ('class="math' in MD.render(source)) is math


@pytest.mark.parametrize(
    ("source", "enabled"),
    [
        ("# T\n\n## A\n", True),
        ("<!-- section-numbers: false -->\n# T\n", False),
        ("```\n<!-- section-numbers: false -->\n```\n", True),
        ("~~~~\n<!-- section-numbers: false -->\n~~~~\n<!-- section-numbers: false -->\n", False),
        ("\n" * 20 + "<!-- section-numbers: false -->\n", True),
    ],
)
def test_section_numbers_enabled(source: str, enabled: bool) -> None:
    assert section_numbers_enabled(source) is enabled


def test_resolve_safe(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    (root / "a").mkdir()
    assert resolve_safe(root, "") == root
    assert resolve_safe(root, "a/../a/b.md") == root / "a" / "b.md"
    for escape in ("..", "../x.md", "a/../../x.md"):
        with pytest.raises(HTTPException):
            resolve_safe(root, escape)


def test_intraline_marks_changed_words() -> None:
    assert intraline("the quick fox", "the slow fox") == ("the <mark>quick</mark> fox", "the <mark>slow</mark> fox")


def test_intraline_dissimilar_lines_are_only_escaped() -> None:
    assert intraline("<a>", "totally different") == ("&lt;a&gt;", "totally different")


def test_pdf_view_returns_pdf_or_setup_hint(repo: Path) -> None:
    response = TestClient(create_app(repo)).get("/clean.md?view=pdf")
    if response.status_code == 200:
        assert response.headers["content-type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")
    else:
        assert response.status_code == 500
        assert "brew install pango" in response.text


def test_fastapi_builtin_routes_do_not_shadow_files(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "README.md").write_text("# Docs\n")
    (tmp_path / "openapi.json").write_text('{"mine": true}\n')
    client = TestClient(create_app(tmp_path), follow_redirects=False)
    assert client.get("/docs").headers["location"] == "/docs/README.md"
    assert client.get("/redoc").status_code == 404
    assert client.get("/openapi.json?view=raw").text == '{"mine": true}\n'


def test_api_docs_list_only_the_api(tmp_path: Path) -> None:
    client = TestClient(create_app(tmp_path))
    assert "swagger" in client.get("/_docs").text.lower()
    schema = client.get("/_openapi.json").json()
    assert sorted(schema["paths"]) == ["/_notes", "/_restart", "/_servers", "/_whoami"]
    notes = schema["paths"]["/_notes"]
    assert sorted(notes) == ["delete", "put"]
    assert "text" in notes["put"]["requestBody"]["content"]["application/json"]["schema"]["properties"]


@pytest.mark.parametrize("base", ["--output=x", "HEAD~1", "abc", "a" * 41, "ABCDEF0"])
def test_diff_request_rejects_bad_base(base: str) -> None:
    with pytest.raises(BadDiffParam):
        DiffRequest.from_query({"base": base}, markdown=True)


def test_diff_request_defaults_and_links() -> None:
    request = DiffRequest.from_query({"to": "abcdef0", "mode": "rendered"}, markdown=False)
    assert request == DiffRequest()  # `to` needs a SHA base; mode is text for non-markdown
    sha = DiffRequest.from_query({"base": "abcdef0", "to": "1234567"}, markdown=True)
    assert sha.query(layout="split") == "?view=diff&base=abcdef0&to=1234567&layout=split"
    assert sha.query(base="auto") == "?view=diff"


def keys(text: str) -> list[str]:
    tokens, _, source = parse_markdown(text)
    return [key or "" for key, _ in cut_blocks(source, tokens)]


def test_cut_blocks_lists_and_fences() -> None:
    text = "- a\n- b\n\n3. x\n4. y\n\n```\none\n\ntwo\n```\n"
    assert keys(text) == ["- a", "- b", "3. x", "4. y", "```\none\n\ntwo\n```"]
    blocks = render_blocks(text, old=False)
    assert blocks[2].html.startswith('<ol start="3">') and blocks[3].html.startswith('<ol start="4">')


def test_inserted_section_is_only_additions() -> None:
    old = "# T\n\n## A\n\nx\n\n## B\n\ny\n"
    new = "# T\n\n## A\n\nx\n\n## New\n\nz\n\n## B\n\ny\n"
    rows = block_rows(render_blocks(old, old=True), render_blocks(new, old=False))
    assert [kind for kind, _, _ in rows] == ["same", "same", "same", "add", "add", "same", "same"]
    assert "3. B" in str(rows[-2][2] and rows[-2][2].html)  # renumbered, still unchanged


def test_changed_run_pairs_by_type() -> None:
    old = "Gone paragraph.\n\n| a |\n| - |\n| 1 |\n"
    new = "| a |\n| - |\n| 2 |\n"
    rows = block_rows(render_blocks(old, old=True), render_blocks(new, old=False))
    assert [kind for kind, _, _ in rows] == ["del", "change"]


@pytest.mark.parametrize(
    ("old", "new", "kinds"),
    [
        ("a\nb\n", "a\nx\nb\n", ["same", "add", "same"]),
        ("a\nx\nb\n", "a\nb\n", ["same", "del", "same"]),
        ("a\nold line\nb\n", "a\nnew line\nb\n", ["same", "del", "add", "same"]),
    ],
)
def test_unified_rows(old: str, new: str, kinds: list[str]) -> None:
    assert re.findall(r'<td class="(same|del|add)">', unified_table(old, new)) == kinds


def test_mark_words_in_rendered_blocks() -> None:
    old, new = mark_words(
        "<p>Use <code>layout=unified</code>, and more &lt;text&gt;.</p>",
        "<p>Use <code>layout=split</code> for side by side, and more &lt;text&gt;.</p>",
    )
    assert old == "<p>Use <code>layout=<mark>unified</mark></code>, and more &lt;text&gt;.</p>"
    assert (
        new == "<p>Use <code>layout=<mark>split</mark></code> <mark>for side by side</mark>, and more &lt;text&gt;.</p>"
    )


def test_mark_words_skips_dissimilar_and_scripted_blocks() -> None:
    assert mark_words("<p>One two three</p>", "<p>Four five six</p>") == (
        "<p>One two three</p>",
        "<p>Four five six</p>",
    )
    mermaid = ('<div class="mermaid">graph A--&gt;B</div>', '<div class="mermaid">graph A--&gt;C</div>')
    assert mark_words(*mermaid) == mermaid


def test_scope_maps_repo_paths_to_root(tmp_path: Path) -> None:
    below = Scope(tmp_path, tmp_path / "site")
    assert below.pathspec == "site"
    assert below.relative("site/a/b.md") == "a/b.md"
    assert below.relative("other/c.md") is None
    above = Scope(tmp_path / "repo", tmp_path)
    assert above.pathspec == "."
    assert above.relative("x.md") == "repo/x.md"


def test_parse_name_status_renames_and_root() -> None:
    scope = Scope(Path("/r"), Path("/r/site"))
    out = "M\0site/a.md\0R095\0site/old.md\0site/new.md\0D\0elsewhere.md\0A\0site/sub/c.md\0"
    assert parse_name_status(out, scope) == [Change("M", "a.md"), Change("R", "new.md"), Change("A", "sub/c.md")]


def test_commit_param_rules() -> None:
    assert DiffRequest.from_query({"commit": "abcdef0"}, markdown=True).query() == "?view=diff&commit=abcdef0"
    with pytest.raises(BadDiffParam):
        DiffRequest.from_query({"commit": "abcdef0", "base": "staged"}, markdown=True)
    with pytest.raises(BadDiffParam):
        DiffRequest.from_query({"commit": "HEAD"}, markdown=True)


def test_changed_files_tree_compacts_single_folder_chains() -> None:
    changes = [Change("M", "src/pkg/a.py"), Change("A", "src/pkg/static/b.css"), Change("M", "README.md")]
    out = tree_items(file_tree(changes), "README.md", DiffRequest())
    summaries = re.findall(r"<summary>([^<]*)</summary>", out)
    assert summaries == ["src/pkg", "static"]
    assert out.index("src/pkg") < out.index("README.md")  # folders before files
