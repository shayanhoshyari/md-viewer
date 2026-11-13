---
name: md-viewer
description: Serve markdown in the browser with section numbers, a table of contents, a file tree, diagrams and math, plus git diffs with a source control panel and notes left from the browser. Use this when the user wants to read or preview a markdown file or folder in a browser, asks to open, view, or serve markdown, or wants to see in a browser what changed in a file or commit. Also use it when asked to check, handle or address notes left in markdown files (`<!-- note: … -->` lines).
---

# Markdown viewer

`bin/md-serve` serves a folder of markdown and source files as browsable pages. The user can run the same command from a terminal (as `md-serve` if it is linked onto their `PATH`).

## Run it

Start it in the background (Bash `run_in_background`), then give the user the URL it prints:

```bash
${CLAUDE_SKILL_DIR}/bin/md-serve <path>
```

- `<path>` is a folder, served as the root, or a file, which serves its parent folder; the printed URL opens that file. It defaults to the current directory.
- The port is a free one picked at start; read it from the `serving <root> at http://127.0.0.1:<port>/...` line. `--port N` pins one.
- The first run builds the skill's venv, which takes a minute; uv prints its progress.
- Every running server is listed at the top of the sidebar; clicking one switches to it. The ⧉ beside it copies the root path.
- To show a different file under the same root, give its URL rather than starting a second server: `http://127.0.0.1:<port>/<path relative to root>`. Headings link as `#<github-style-slug>`.

## What it shows

H2–H6 section numbers and a table of contents (`<!-- section-numbers: false -->` near the top turns numbering off), GitHub callouts, sortable tables, Mermaid and PlantUML fences, LaTeX math (`$x$`, `$$…$$`; `$5` stays text), and `Rendered | Diff | Source | Raw | PDF` tabs. [DESIGN.md](DESIGN.md) is the full spec.

The Diff tab has a source control panel on the right (changed files, then Uncommitted, Staged, Unstaged and recent commits) and takes its choices from the URL, so hand over a link to the exact view: `commit=<sha>` for what one commit changed, `base` (`auto`, `uncommitted`, `staged`, `unstaged` or a commit SHA, with `to` for a second commit), `layout=split` for side by side, and `mode=rendered` for a block-level diff of rendered markdown, e.g. `…/plan.md?view=diff&commit=a1b2c3d&mode=rendered`.

## Notes

On the Rendered tab, the user can leave notes on a block (hover it, click **+ note**; selecting text first quotes it). They are saved into the file as comment lines right after the block, e.g. `<!-- note "quoted words": tighten this -->`. [DESIGN.md](DESIGN.md#notes) has the format.

When asked to check, handle or address the notes:

1. `grep -rn '<!-- note' <file or folder>` to find them.
2. Act on each one; the block above it (and the quote, if any) is what it refers to.
3. Delete the note lines that were handled. Leave the rest and say why.

The PDF tab needs `brew install pango`; without it that tab shows the hint and everything else works.
