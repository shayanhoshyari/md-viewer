# md-viewer design

A local web server that shows a folder of markdown and source files as browsable pages. This file is the spec; the code follows it, and `SKILL.md` links here instead of repeating it.

## Command line

```text
md-viewer serve [PATH] [--host H] [--port N]
md-viewer notes [PATH]
md-viewer links [PATH]
md-viewer restart
```

`python -m md_viewer` is the same command.

### md-viewer serve

- `PATH` defaults to the current directory. A folder is served as the root. A file serves its parent folder, and the printed URL opens that file.
- `--host` defaults to `127.0.0.1`. `--port` defaults to `0`, a free port picked by the OS.
- The socket is bound before anything is printed, so the URL carries the real port. The one line printed is:

  ```text
  serving <root> at http://<host>:<port>/<file, URL-quoted, or nothing for a folder>
  ```

- A path that doesn't exist is a usage error (exit status 2).
- Once bound, the server registers itself (see [Server list](#server-list)) and unregisters when it shuts down, Ctrl-C and SIGTERM included.
- `bin/md-viewer` runs the package with `uv run --frozen --no-dev --project <skill folder>`, so it works from any directory and through the `~/.local/bin/md-viewer` link. The first run builds `.venv/`.

### md-viewer notes

Lists the [notes](#notes) in a markdown file, or in every `.md` file under a folder (skipping what the file tree skips), so an agent handling them reads only the notes and the blocks they're on. `PATH` defaults to the current directory. For each note it prints the file and line, the kind of block the note is on and its lines, that block's source (at most 15 lines), the quote if any, and the text:

```text
plans/next.md:19  paragraph, lines 15-18
  > The comment is an extra cell past the header's column count,
  > which markdown-it and GFM drop.
  quote: the header's column count
  note: will allowing this after any line be simpler?
```

Notes are separated by a blank line. A note above every block shows `top of file` and no source. No notes prints nothing. Blocks are found by the same code the server uses to place notes, so the two agree. A path that doesn't exist is a usage error.

### md-viewer links

Lists relative links and images that point at a missing file or heading, in a markdown file or every `.md` file under a folder (skipping what the file tree skips). `PATH` defaults to the current directory.

- A link's target, relative to its file, must exist; a folder counts. A `#anchor` into a `.md` file, or alone for the same file, must be the id of one of its headings as the viewer renders them (GitHub-style slugs, from the same parser). Anchors into other files aren't checked.
- Links with a scheme or host (`https:`, `mailto:`) aren't checked, so the command is offline. Links in code are not links.
- It prints one line per problem, `doc.md:12: missing file: other.md` or `doc.md:14: missing anchor: other.md#setup`, with the line the link is on and paths relative to the current directory, and exits 1 if there were any. No problems prints nothing.
- The checker is part of the [public API](#public-api), so a folder's own checker can depend on the package and add its rules on top of `links_of` and `link_problem`.

### md-viewer restart

Restarts every running server on the code now on disk, for use while developing md-viewer. Each server keeps its process, folder and port, so the terminal or agent task that started it still owns it and open tabs need only a reload.

- It reads the [registry](#server-list) like any reader, pruning dead entries, and sends `POST /_restart` to each live server at once.
- It then waits, for up to 15 seconds, until each port answers `/_whoami` with a new id.
- It prints one line per server, sorted by root, `restarted ~/notes  http://127.0.0.1:8000/` or `failed ~/notes: <reason>`, and exits 1 if any failed. No servers prints nothing.

## Public API

Other code imports only what `md_viewer` exports in `__all__`; every other module is internal and can change in any release. Importing `md_viewer` loads the markdown parser but not the server (FastAPI, uvicorn, WeasyPrint).

- `Link`: a relative link or image: `source` file, 1-based `line`, `target` as written, resolved `path`, unquoted `anchor`.
- `links_of(path) -> list[Link]`: the relative links and images in a markdown file.
- `link_problem(link) -> str | None`: `missing file: …`, `missing anchor: …`, or None.
- `check_links(files, display=str) -> list[str]`: the lines `md-viewer links` prints.

## Routes and views

Every request path is relative to the root. One route serves everything except the three static files, `PUT` and `DELETE /_notes` (see [Notes](#notes)), `GET /_whoami`, `GET /_servers` and `POST /_restart` (see [Server list](#server-list)). The API is described by Swagger UI at `/_docs` and the OpenAPI schema at `/_openapi.json`, which list only the `/_notes`, `/_whoami`, `/_servers` and `/_restart` routes. FastAPI's default `/docs`, `/redoc` and `/openapi.json` are off, so those paths reach the served folder like any other.

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
- **Tables**: click a header to sort by that column: ascending, descending, then file order. Cells compare as text, with numbers in them compared as numbers. Rows with that cell empty go last in both directions, as in spreadsheets.
- **Fences**: highlighted like the source view, without line numbers. `mermaid` fences render in the browser with Mermaid. `plantuml` fences become an SVG image from the public PlantUML server, with the source in a collapsed block below.
- **Math**: `$…$` inline and `$$…$$` blocks, rendered in the browser by KaTeX. A `$` opens math only when followed by a non-space, non-digit, so `$5`, `$200k` and SQL `$1` stay text.

## Notes

Quick notes left in the browser for the next Claude session to act on. They live in the markdown file as HTML comments, one per block: on its own line right after the block, or at the end of a table row's line.

```markdown
<!-- note: tighten this, drop the second example -->
<!-- note "the selected words": why is this here? -->

| Name | Status |
| --- | --- |
| Acme | open | <!-- note: follow up by Friday -->
```

- **Format**: `<!-- note: <text> -->`, or `<!-- note "<quote>": <text> -->` when text was selected, ending its line. Before it is either whitespace only (a note line) or text ending in `|` (a row note). Such a line is a note whoever wrote it; nothing else is (`<!-- section-numbers: false -->` isn't). A note inside a code block is code, not a note. In the quote, `"` and `\` are written `\"` and `\\`; in the quote and the text, `|` is written `\|`, so the comment stays one table cell. The viewer writes notes on one line, with `-->` in the text written `-- >`.
- **Row notes**: a row note is an extra cell past the header's column count, which tables drop, so the table renders unchanged; on a row with fewer cells than the header it is an empty-looking cell. The header row takes none, since an extra header cell would stop the table being one.
- **Blocks**: the units the rendered diff cuts (top-level blocks and the items of top-level lists), plus each table body row. A raw HTML block takes no notes, since a line right after it joins it; hovering it hides **+ note**. A note line on a list item is indented to the item's content column, so the list stays one list.
- **One note per block**: saving a note on a block that has one replaces it. A block holding several hand-written notes shows them all; saving replaces the first.
- **Rendered view**: each block carries `data-block="<n>"` (fences, math and diagrams in a `div.md-block` wrapper; rows on their `<tr>`), and `data-noted` if it has a note. Hovering a block without a note shows **+ note** in the left margin; hovering a table's header row targets the table. With text selected inside a block, the note quotes it. The editor opens under the block (under a row, in a full-width row): ⌘/Ctrl+Enter saves, Esc cancels. Notes show as yellow boxes under their block, a row's in a full-width row below it, with ✎ and ×; each box carries `data-note-block`. Sorting a table keeps each row's note under it. Every save reloads the page.
- **Elsewhere**: Source and Raw show notes as they are. The rendered diff shows notes as the same boxes, line notes as their own blocks and row notes inside their table, without the buttons. The PDF leaves them out. `md-viewer notes` lists them (see [md-viewer notes](#md-viewer-notes)).
- **Writing**: `PUT /_notes` with JSON `{path, version, block, quote, text}` sets the block's note, adding it or replacing the one there; `DELETE /_notes` with `{path, version, block}` removes it. `version` is the SHA-256 of the file the page showed (the page carries it as `data-notes-version`). The server finds the line itself: a new note line goes after the block and any notes below it; a row note is appended to the row's line after one space. Deleting a row note removes it and that space. Answers are JSON: `{version}`, or `{error}` with 400 (bad request, no such block, no note to delete, not markdown, no text), 403 (origin), 404 (not under the root), 409 (the file changed since the page loaded) or 415 (not JSON).

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
- **`POST /_restart`**: answers 202, then, after the answer is sent, the server deletes its registry entry and replaces itself with `os.execv`, running `python -m md_viewer serve <path> --host <host> --port <bound port>`. The process ID, parent, output and working folder stay; the code is loaded again from disk. The port is the one actually bound, so a server started on a free port comes back on the same one. There is no graceful shutdown: requests in flight are dropped. The entry is deleted first because the new process registers under a new id, and the old entry, with the same process and port, would otherwise still look alive. An app made without a restart command answers 404.
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
- The one write is `PUT` or `DELETE /_notes`, to a `.md` file under the root. The server builds the new text and refuses unless removing every note from the old and the new text (a note line whole; a row note with the one space before it) leaves them identical, so nothing but notes can change. It also refuses unless the file still has the version the page showed. It writes a temp file in the same folder and renames it over the original, keeping its mode, line endings and final newline.
- Writes are accepted only when `Host` is a loopback name (`127.0.0.1`, `localhost`, `[::1]`, so a rebound DNS name fails), `Origin` is that same `http://host:port`, and the body is `application/json`, which a page on another site can't send without a CORS preflight that the server never grants. Notes therefore work only from the machine running the server.
- Query values reach git only as commit SHAs that match `^[0-9a-f]{7,40}$` and that `git rev-parse --verify` accepts.
