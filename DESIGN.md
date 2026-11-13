# md-viewer design

A local web server that shows a folder of markdown and source files as browsable pages. This file is the spec; the code follows it, and `SKILL.md` links here instead of repeating it.

## Command line

```text
md-serve [PATH] [--host H] [--port N]
```

- `PATH` defaults to the current directory. A folder is served as the root. A file serves its parent folder, and the printed URL opens that file.
- `--host` defaults to `127.0.0.1`. `--port` defaults to `0`, a free port picked by the OS.
- The socket is bound before anything is printed, so the URL carries the real port. The one line printed is:

  ```text
  serving <root> at http://<host>:<port>/<file, URL-quoted, or nothing for a folder>
  ```

- A path that doesn't exist is a usage error (exit status 2).
- Once bound, the server registers itself (see [Server list](#server-list)) and unregisters when it shuts down, Ctrl-C and SIGTERM included.
- `bin/md-serve` runs the package with `uv run --frozen --no-dev --project <skill folder>`, so it works from any directory and through the `~/.local/bin/md-serve` link. The first run builds `.venv/`.

## Routes and views

Every request path is relative to the root. One route serves everything except the three static files, `POST /_notes` (see [Notes](#notes)), and `GET /_whoami` and `GET /_servers` (see [Server list](#server-list)). FastAPI's built-in `/docs`, `/redoc` and `/openapi.json` pages are turned off, so those paths reach the served folder like any other.

- `/_static/style.css`, `/_static/client.js`: package files from `static/`. `/_static/pygments.css`: the Pygments `friendly` style, scoped to `.code-block`.
- A folder redirects to its `README.md`, else its `AGENTS.md`, else shows a listing of its entries (with `../` below the root).
- A file whose suffix is in the source set (`.css .html .ini .js .json .md .py .pyi .sh .sql .toml .ts .yaml .yml`), or named `Makefile` or `OWNERS`, is text and gets views. Anything else, including images and PDFs, is served as-is with a type guessed from its name, except that `?view=diff` and `?view=raw` stay in the viewer: a file that looks like text (no NUL byte, valid UTF-8 in its first 8 KB) gets a diff and a `text/plain` Raw view (tabs `Diff | Raw`), and a binary file gets a diff page saying it is binary, with the source control panel (tab `Diff`).
- Text files take `?view=`:

  | View | Markdown | Other text |
  | --- | --- | --- |
  | (none) | rendered | source |
  | `diff` | diff | diff |
  | `source` | source | source |
  | `raw` | `text/plain` bytes | `text/plain` bytes |
  | `pdf` | letter-size PDF | (source) |

- Pages show a tab bar: `Rendered | Diff | Source | Raw | PDF` for markdown, `Source | Diff | Raw` for other text.
- **Diff**: what changed in the file, from git. See [Diff](#diff).
- **Source**: Pygments markup with line numbers. Each line is `<span class="line" id="L-n">`; `#L-12` and `#L-10-L-20` highlight and scroll to lines. In the browser, Shiki (VS Code's grammars and `light-plus` theme) re-highlights blocks in the same shape; if the CDN is unreachable the Pygments markup stays.

## Diff

The diff view compares two versions of the file. Every choice is a query parameter, so a URL reproduces the view. Parameters equal to their default are left out of generated links.

| Parameter | Values | Default |
| --- | --- | --- |
| `base` | `auto`, `uncommitted`, `staged`, `unstaged`, or a commit SHA (7–40 hex) | `auto` |
| `to` | `worktree` or a commit SHA; read only when `base` is a SHA | `worktree` |
| `commit` | a commit SHA: what that commit changed; only with `base=auto` | none |
| `layout` | `unified`, `split` | `unified` |
| `mode` | `text`, `rendered` (markdown only; ignored for other files) | `text` |

An unknown value is a 400 page saying which parameter is wrong. Outside a git repository the page says so.

What `base` compares, old → new:

- `auto`: uncommitted changes when the working tree differs from `HEAD`; otherwise the last commit that touched the file, against its parent; a file never committed shows as all added. The label above the diff says which it picked.
- `uncommitted`: `HEAD` → working tree.
- `staged`: `HEAD` → index.
- `unstaged`: index → working tree.
- `<sha>`: the file at that commit → `to`, which is the working tree or the file at another commit. Any commit git knows works. A side where the file doesn't exist is empty.

`commit=<sha>` compares the file at the commit's first parent (under its old name if the commit renamed it) → the file at the commit. A root commit's parent side is empty.

**Control bar**, above the diff: the label, and **Unified | Split** and, for markdown, **Text | Rendered** toggles.

**Source control panel**: a right-hand column in the Diff view inside a git repository, like VS Code's. A button at the top right hides it; the choice is kept in `localStorage`.

- **Selections**, at the bottom: Uncommitted, Staged and Unstaged, each with the number of changed files under the root, then the last 50 commits that touched anything under the root, as the subject with `<short sha> · <date>` below. Clicking one keeps the current file and switches to `base=uncommitted|staged|unstaged` or `commit=<sha>`.
- **Changed files**, at the top: the files the current selection changed under the root, as a folder tree (folders first, each open and collapsible; a folder holding only one folder shows as `a/b`), each file with a status letter (`M` modified, `A` added, `D` deleted, `R` renamed, `U` untracked). Clicking one opens its diff with the same selection, layout and mode; the left tree follows as if it had been clicked there. Deleted files are greyed out with no link.
- `auto` highlights what it resolved to: Uncommitted when the file has uncommitted changes or was never committed, else the file's last commit.
- `base=<sha>` (with `to`) is reachable only by URL; the panel then highlights nothing.
- When the file didn't change in the selection, the page says so and points to the panel.

**Text mode** shows changed hunks with three lines of context and `⋯` between hunks. Similar changed lines mark the changed words. `unified` is one column with both line numbers, removed lines before added ones; `split` is a side-by-side table.

**Rendered mode** (markdown) compares blocks instead of lines:

- Each side is cut into blocks: every top-level element (paragraph, heading, table, fence, quote, callout, HTML block, …) is one, and a top-level list is cut into its items. Blocks match when their source lines match, ignoring trailing whitespace.
- Each block is rendered as part of its own document: reference links and footnotes resolve, and headings are numbered by that side's rules. Numbers are not compared, so inserting a section doesn't mark later headings changed. List items keep their list and number.
- Removed blocks have a red edge and tint, added ones green; a changed block shows as its old and new versions.
- In a changed pair whose text is at least half the same, the changed words are marked, as in Text mode. Only text is compared, not tags or link targets. Mermaid, PlantUML and math blocks get no marks, since a script reads their text; in code blocks Shiki's re-highlighting replaces them.
- `unified` stacks old above new; `split` puts old and new side by side, one row per block pair.
- The whole document shows. Unchanged runs longer than two blocks on each side of a change get a "⋯ n unchanged blocks" bar that collapses them in place.
- Mermaid, math, Shiki and table sorting work as on the rendered page. Old-side headings have no `id`, so anchors stay unique. A change only in the front matter says so and points to Text mode.

## Markdown

- CommonMark with raw HTML, linkify, strikethrough, tables, footnotes and task lists. A leading MyST `---` metadata block is dropped.
- **Heading ids**: GitHub-style slugs on every heading, so `#<slug>` links work.
- **Numbering**: H2–H6 are numbered at render time (`1.`, `1.1.`, …); files are not changed. A line `<!-- section-numbers: false -->` in the first 20 lines, outside a code fence, turns it off.
- **Outline**: with two or more H2/H3 headings, a collapsible table of contents goes after the H1 (or at the top without one), numbered like the headings.
- **Callouts**: a top-level quote starting with `[!NOTE]`, `[!TIP]`, `[!IMPORTANT]`, `[!WARNING]` or `[!CAUTION]` alone on its line becomes a GitHub-style callout.
- **Tables**: click a header to sort by that column: ascending, descending, then file order.
- **Fences**: highlighted like the source view, without line numbers. `mermaid` fences render in the browser with Mermaid. `plantuml` fences become an SVG image from the public PlantUML server, with the source in a collapsed block below.
- **Math**: `$…$` inline and `$$…$$` blocks, rendered in the browser by KaTeX. A `$` opens math only when followed by a non-space, non-digit, so `$5`, `$200k` and SQL `$1` stay text.

## Notes

Quick notes left in the browser for the next Claude session to act on. They live in the markdown file as one comment line each, right after the block they refer to:

```markdown
<!-- note: tighten this, drop the second example -->
<!-- note "the selected words": why is this here? -->
```

- **Format**: a line matching `^\s*<!-- note( "<quote>")?: <text> -->\s*$` is a note, whoever wrote it; no other line is (`<!-- section-numbers: false -->` isn't). In the quote, `"` and `\` are written `\"` and `\\`. The viewer writes notes as one line, with `-->` in the text written `-- >`.
- **Blocks**: the units the rendered diff cuts: top-level blocks, and the items of top-level lists. A raw HTML block takes no notes, since a line right after it joins it; hovering it hides **+ note**. A note on a list item is indented to the item's content column, so the list stays one list. A new note goes below the block's existing notes.
- **Rendered view**: each block carries `data-block="<n>"` (fences, math and diagrams in a `div.md-block` wrapper). Hovering one shows **+ note** in the left margin; with text selected inside a block, the note quotes it. The editor opens under the block: ⌘/Ctrl+Enter saves, Esc cancels. Notes show as yellow boxes under their block with ✎ and ×. Every save reloads the page.
- **Elsewhere**: Source and Raw show note lines as they are. The rendered diff shows notes as the same boxes, as their own blocks, without the buttons. The PDF leaves them out.
- **Writing**: `POST /_notes` with JSON `{path, version, op: add|edit|delete, block, line, quote, text}`. `version` is the SHA-256 of the file the page showed (the page carries it as `data-notes-version`). `add` takes `block`, and the server finds the line and indent itself; `edit` (text only, the quote is kept) and `delete` take `line`, 1-based, which must be a note. Answers are JSON: `{version}`, or `{error}` with 400 (bad request, not a note, not markdown, no text), 403 (origin), 404 (not under the root), 409 (the file changed since the page loaded) or 415 (not JSON).

## Sidebar

- At the top, the server list (see [Server list](#server-list)).
- A tree of the root: folders first, then files, case-insensitive. Only `.json .md .py .toml .yaml .yml` files appear; empty folders and hidden entries (except `.gitignore` and `.claude`) are left out. `.git`, `.venv`, `__pycache__`, `.pytest_cache`, `.ruff_cache` and `.DS_Store` are hidden from the tree and from listings.
- The current file is highlighted and its folders opened.
- The filter box (`/` to focus, Esc to clear) hides files whose name doesn't match, and folders with no matches, without opening or closing any. A closed folder with matches turns accent-colored and shows its count.
- The ☰ button hides the sidebar; the choice is kept in `localStorage`.

## Server list

Every running md-viewer is listed at the top of every page, so you can jump between them. There is no daemon: each server registers in a shared folder, and whoever reads the list checks the entries and prunes the dead ones.

- **Registry**: `$XDG_STATE_HOME/md-viewer/servers/` (default `~/.local/state/md-viewer/servers/`), or `MD_VIEWER_STATE_DIR`. Each server writes one file, `<id>.json` with `{id, pid, host, port, root, started}`, where `id` is a random UUID. The file is written to a temp name and renamed into place. A server writes and deletes only its own file, except that a reader deletes the files of servers it found dead.
- **Liveness**: `GET /_whoami` answers `{id, root}`. An entry is alive when `http://127.0.0.1:<port>/_whoami` answers its `id` within 300 ms. All entries are probed at once, in threads. Connection refused, a different `id`, a bad answer or an unreadable file deletes the entry. A timeout hides it but keeps it, in case the server is only busy. The server's own entry isn't probed.
- **`GET /_servers`**: `[{root, label, url, current}]`, sorted by root. `label` is the root with the home folder written `~`. This server is included with `url` `/` and `current` true. An app made without a registry id lists only itself.
- **Sidebar**: the header is this server's folder name, with the `~` path as its tooltip. Beside it, a ⧉ button copies the absolute root path to the clipboard (for `cd` and starting `claude` there) and shows ✓ for a moment. Clicking it opens a list fetched from `/_servers` each time it opens, showing each other server's folder name with its `~` path below, linking to its `url`. While loading it says "Looking…"; with none it says "No other servers".

## PDF

The PDF view prints the rendered markdown with WeasyPrint on letter paper with page numbers: no sidebar, scripts or tabs, styles from `static/style.css` plus `static/print.css`. PlantUML and Pygments are included; Mermaid and math print as source. WeasyPrint needs Pango, Cairo and GLib (`brew install pango`). Without them only this view fails, with a page saying so and status 500.

## External requests

The server itself never fetches anything except, for the PDF view, PlantUML SVGs, and other md-viewers' `/_whoami` on `127.0.0.1`. Pages load from CDNs in the browser:

- Mermaid 11 and KaTeX 0.16.22 from `cdn.jsdelivr.net`;
- Shiki 3.23.0 and its grammars from `esm.sh`, only for languages a page uses;
- PlantUML SVGs from `www.plantuml.com`, which receive only the diagram text (no referrer).

## Security

- It binds `127.0.0.1` by default.
- Every request path is resolved, symlinks included, and must stay under the root; anything else is a 404.
- The one write is `POST /_notes`, to a `.md` file under the root. The server builds the new text and refuses unless removing every note line from the old and the new text leaves them identical, so nothing but note lines can change. It also refuses unless the file still has the version the page showed. It writes a temp file in the same folder and renames it over the original, keeping its mode, line endings and final newline.
- Writes are accepted only when `Host` is a loopback name (`127.0.0.1`, `localhost`, `[::1]`, so a rebound DNS name fails), `Origin` is that same `http://host:port`, and the body is `application/json`, which a page on another site can't send without a CORS preflight that the server never grants. Notes therefore work only from the machine running the server.
- Query values reach git only as commit SHAs that match `^[0-9a-f]{7,40}$` and that `git rev-parse --verify` accepts.
