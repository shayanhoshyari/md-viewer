---
name: md-viewer
description: Serve markdown in the browser with section numbers, a table of contents, a file tree, diagrams and math, plus git diffs with a source control panel and notes left from the browser. Use this when the user wants to read or preview a markdown file or folder in a browser, asks to open, view, or serve markdown, or wants to see in a browser what changed in a file or commit. Also use it when asked to check, handle or address notes left in markdown files (`<!-- note: … -->` lines), or to check the links in markdown files.
---

# Markdown viewer

`bin/md-viewer serve` serves a folder of markdown and source files as browsable pages, `bin/md-viewer notes` lists the notes left in them, and `bin/md-viewer links` checks their links. The user can run the same commands from a terminal (as `md-viewer` if it is linked onto their `PATH`).

## Run it

Start it in the background (Bash `run_in_background`), then give the user the URL it prints:

```bash
${CLAUDE_SKILL_DIR}/bin/md-viewer serve <path>
```

- `<path>` is a folder, served as the root, or a file, which serves its parent folder; the printed URL opens that file. It defaults to the current directory.
- The port is a free one picked at start; read it from the `serving <root> at http://127.0.0.1:<port>/...` line. `--port N` pins one.
- The first run builds the skill's venv, which takes a minute; uv prints its progress.
- Every running server is listed at the top of the sidebar; clicking one switches to it. The ⧉ beside it copies the root path.
- To show a different file under the same root, give its URL rather than starting a second server: `http://127.0.0.1:<port>/<path relative to root>`. Headings link as `#<github-style-slug>`.
- After changing md-viewer's own code, `${CLAUDE_SKILL_DIR}/bin/md-viewer restart` restarts every running server on the new code, each on its folder and port; open tabs need a reload.

## What it shows

H2–H6 section numbers and a table of contents (`<!-- section-numbers: false -->` near the top turns numbering off), GitHub callouts, sortable tables (`<!-- default-sort: Due asc -->` above one sets how it opens), Mermaid and PlantUML fences, LaTeX math (`$x$`, `$$…$$`; `$5` stays text), and `Rendered | Diff | Source | Raw | PDF` tabs. [DESIGN.md](DESIGN.md) is the full spec.

The Diff tab has a source control panel on the right (changed files, then Uncommitted, Staged, Unstaged and recent commits) and takes its choices from the URL, so hand over a link to the exact view: `commit=<sha>` for what one commit changed, `base` (`auto`, `uncommitted`, `staged`, `unstaged` or a commit SHA, with `to` for a second commit), `layout=split` for side by side, and `mode=rendered` for a block-level diff of rendered markdown, e.g. `…/plan.md?view=diff&commit=a1b2c3d&mode=rendered`.

## Notes

On the Rendered tab, the user can leave a note on a block or a table row (hover it, click **+ note**; selecting text first quotes it), one per block. They are saved into the file as comments: a line right after the block, e.g. `<!-- note "quoted words": tighten this -->`, or at the end of a table row's line, e.g. `| Acme | open | <!-- note: follow up -->`. In a note, `\|` stands for `|`. [DESIGN.md](DESIGN.md#notes) has the format.

When asked to check, handle or address the notes:

1. `${CLAUDE_SKILL_DIR}/bin/md-viewer notes <file or folder>` lists each note with its file and line, the block it's on and that block's source, and the quote if any. Read more of the file only where a note needs it.
2. Act on each one.
3. Delete the notes that were handled: a note line whole, a row note with the space before it. Leave the rest and say why.

## Links

When asked to check links in markdown, or after edits where a folder's instructions ask for it, run `${CLAUDE_SKILL_DIR}/bin/md-viewer links <file or folder>`. It prints `path:line: missing file: …` or `missing anchor: …` for each relative link or image that points at a missing file or heading, using the same heading anchors the viewer renders, and nothing when all is well. Fix each one: correct the path or anchor, or drop the link. External URLs aren't checked.

The PDF tab needs `brew install pango`; without it that tab shows the hint and everything else works.
