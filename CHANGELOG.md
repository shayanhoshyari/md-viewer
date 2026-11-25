# Changelog

## 0.26.0 - 2026-11-25

- An `md-viewer.toml`, the first one found in the folder or above it, says what is left out: `[tree] ignore` for the file tree and directory listings, `[check] ignore` for `notes` and `links`. An entry is a name matched at any depth or a path relative to the toml. With no toml, a packaged default leaves out `.git`, `.venv`, `node_modules`, `__pycache__`, the tool caches and `.DS_Store`.
- Nothing else is left out: the file tree lists every file type and hidden files and folders. `.ignore` and `.gitignore` files are no longer read, and the dependency on `ignore-python` is gone.
- Walks skip symlinks, so a symlinked folder, such as a virtualenv, no longer fills the tree and slows every page.
- `serve`, `notes` and `links` take a folder only; a file is a usage error. To open a file, add its path to the server's URL.

## 0.25.0 - 2026-11-24

- Read aloud speaks English with the Chinese voice too, instead of the browser's default English voice, which on macOS is the novelty voice Albert.

## 0.24.0 - 2026-11-24

- Read aloud: selecting text on a rendered page shows a 🔊 button that speaks it with the browser's speech, and ⏹ to stop. Text with hanzi speaks only its Chinese, with a Chinese voice (Premium or Enhanced first, then Google, then Tingting) at 0.85 speed. With an online voice the selected text goes to its provider.

## 0.23.0 - 2026-11-21

- The file tree lists `Makefile`s, which open as highlighted source.

## 0.22.0 - 2026-11-21

- The file tree lists JavaScript and TypeScript files (`.js .mjs .cjs .jsx .ts .tsx`), and all of them open as highlighted source.

## 0.21.0 - 2026-11-21

- `md-viewer serve --detach` (`-d`) starts the server in the background, in its own session, and returns once it is up with the usual URL line. If a server already serves that folder, it prints that server's URL instead. Stop one with `kill`, using the process ID from `md-viewer list`.
- `md-viewer serve --log-file [FILE]` logs to a file rotated at 1 MB (two files at most) instead of the terminal, by default `md-viewer-<pid>.log` in the temp folder, and deletes it at shutdown. A detached server always logs this way, and `restart` keeps the file.

## 0.20.0 - 2026-11-21

- `md-viewer notes` and `md-viewer links` on a folder skip what ripgrep skips (`.ignore` and `.gitignore` files in the folder, its subfolders and the folders above it, and git's exclude files), plus dot folders other than `.claude` and `.agents`. This replaces their fixed skip list, so a folder such as `node_modules` is skipped when an ignore file hides it. New dependency: `ignore-python`.
- The file tree shows `.agents` folders, as it does `.claude`.

## 0.19.0 - 2026-11-17

- `md-viewer list` prints a table of the running servers: path, port, process ID and URL.

## 0.18.0 - 2026-11-16

- A ⧉ button beside the path above the tab bar copies the open file's absolute path (a folder's, on a listing).

## 0.17.0 - 2026-11-14

- An Edit tab on markdown files: the source in a plain textarea, saved with ⌘S or Ctrl+S (or the Save button) through `PUT /_file`, from this machine only. A save is refused if the file changed on disk since the page loaded, and the text stays in the page.

## 0.16.1 - 2026-11-14

- `node_modules` folders are hidden from the file tree and listings.

## 0.16.0 - 2026-11-14

- A markdown diff opens in Rendered mode; `?mode=text` (or the Text toggle) shows the line diff.

## 0.15.0 - 2026-11-14

- `md-viewer list` prints every running server's folder and URL, one per line, for finding one again after closing its tab.

## 0.14.0 - 2026-11-13

- A table can open already sorted: put `<!-- default-sort: <column> [asc|desc] -->` on the line before it. Clicking headers still re-sorts.

## 0.13.0 - 2026-11-13

- Sorting a table puts rows whose cell in that column is empty at the bottom, ascending or descending, as spreadsheets do.

## 0.12.0 - 2026-11-13

- A public API: `from md_viewer import Link, links_of, link_problem, check_links`. Everything else in the package is internal.

## 0.11.0 - 2026-11-13

- `md-viewer links [PATH]` lists relative links and images that point at a missing file or heading, using the viewer's own heading anchors. `md_viewer.links` can be imported by other checkers.

## 0.10.0 - 2026-11-13

- `md-viewer restart` restarts every running server on the code now on disk. Each keeps its process, folder and port, so open tabs only need a reload. It works through a new `POST /_restart` route.

## 0.9.0 - 2026-11-13

- Notes on table rows: hover a row and click **+ note**. The note is saved at the end of the row's line (`| a | b | <!-- note: … -->`), which tables ignore, and shows in a full-width row below it that moves with the row when sorting. Hovering the header row notes the whole table.
- One note per block: a block with a note offers ✎ and × instead of **+ note**, and saving replaces its note.
- **Breaking** for scripts calling the API: `POST /_notes` with `add`/`edit`/`delete` is replaced by `PUT /_notes` (set a block's note) and `DELETE /_notes` (remove it), both addressed by block.
- `md-viewer notes` lists row notes with their table's header and the row.

## 0.8.0 - 2026-11-13

- **Breaking**: the command is now `md-viewer`, with subcommands; `md-serve PATH` becomes `md-viewer serve PATH`. `python -m md_viewer` runs the same command.
- `md-viewer notes [PATH]` lists the notes in a file or folder, each with the block it's on and that block's source, so handling notes doesn't need the whole file.
- Swagger UI for the viewer's API at `/_docs`, with the schema at `/_openapi.json`.

## 0.7.0 - 2026-11-12

- A ⧉ button beside the sidebar header copies the served folder's path, ready to `cd` into and start `claude`.

## 0.6.1 - 2026-11-12

- A README and MIT license, and `make publish`, which mirrors this folder (without `plans/`) to the public repo `shayanhoshyari/md-viewer`.

## 0.6.0 - 2026-11-12

- The sidebar header now names the served folder and opens a list of every running md-viewer; click one to switch to it. Servers register themselves in `~/.local/state/md-viewer/servers/`, and the list checks each one is still answering, dropping the ones that aren't.

## 0.5.0 - 2026-11-12

- Notes: on the Rendered tab, hover a block and click **+ note** (select text first to quote it) to save a note into the file as a `<!-- note: … -->` line after the block. Notes show as boxes with edit and delete, and in the rendered diff. This is the viewer's first write to disk: it can change only note lines, refuses if the file changed since the page loaded, and accepts writes only from its own pages on this machine.

## 0.4.2 - 2026-11-12

- Clicking a changed file of an unknown type in the panel (for example an extensionless file) no longer downloads it: text files get a diff, binary files a page saying so, both with the panel.

## 0.4.1 - 2026-11-12

- The panel's changed files show as a folder tree, like VS Code's tree view.

## 0.4.0 - 2026-11-12

- The Diff view has a VS Code-style source control panel on the right, which hides like the left sidebar. At the top it lists the files changed in the current selection; clicking one opens its diff with the same selection. At the bottom are Uncommitted, Staged, Unstaged and the last 50 commits under the served folder.
- New `commit=<sha>` parameter: what that commit changed in the file.
- The Base and To dropdowns are gone; `base=<sha>` and `to` still work in the URL.

## 0.3.1 - 2026-11-12

- Rendered diffs show the whole document on first open; the "⋯ n unchanged blocks" bars now collapse runs instead of expanding them.

## 0.3.0 - 2026-11-12

- Rendered diffs mark the changed words inside a changed block.

## 0.2.1 - 2026-11-12

- The Diff tab defaults to the unified layout; `layout=split` gives side by side.

## 0.2.0 - 2026-11-12

- The Diff tab has a control bar, and every choice is in the URL:
  - `base`: what to compare against. Auto (as before), uncommitted, staged, unstaged, or any commit, picked from the last 20 commits that touched the file, following renames; `to` compares two commits.
  - `layout=unified`: one column instead of side by side.
  - `mode=rendered` (markdown): compares rendered blocks instead of lines, with list items as their own blocks and long unchanged runs folded.
- A bad `base`, `to`, `layout` or `mode` is a 400 page saying which one.

## 0.1.1 - 2026-11-12

- A served folder named `docs/` (or a file at `/redoc` or `/openapi.json`) now shows as itself instead of FastAPI's built-in API pages.

## 0.1.0 - 2026-11-12

- Converted from a single PEP 723 script to a `uv` package with tests. No behavior change; `--help` now names the program `md-serve`.
