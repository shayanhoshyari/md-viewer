# Changelog

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
