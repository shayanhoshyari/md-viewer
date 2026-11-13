# md-viewer

A local markdown viewer, packaged as a [Claude Code](https://claude.com/claude-code) skill. Point it at a folder and it serves the markdown and source files as browsable pages: section numbers, a table of contents, a file tree, Mermaid and PlantUML diagrams, LaTeX math, and PDF export. A Diff tab shows git changes, source or rendered, beside a source control panel.

It exists because VS Code's markdown preview shows one page at a time. Here every page has its own URL, so you can open many documents side by side in browser tabs.

![md-viewer showing its own DESIGN.md](https://github.com/user-attachments/assets/55b348c7-070e-4e5f-a87a-8d622aae6f1a)

You can also leave notes on the rendered page. They are saved into the file as `<!-- note: … -->` lines, and Claude can then be asked to "check the notes" and act on them. The ⧉ button in the sidebar copies the served folder's path, to start `claude` there.

> [!NOTE]
> This is a personal project, shaped around the author's own use. It runs only on your machine, binds to `127.0.0.1` by default, and its only write to disk is note lines.

## Install

Needs [uv](https://docs.astral.sh/uv/getting-started/installation/). Clone it into Claude Code's skills folder:

```bash
git clone https://github.com/shayanhoshyari/md-viewer ~/.claude/skills/md-viewer
```

Claude picks it up when you ask to view or preview markdown. To run it yourself, use `~/.claude/skills/md-viewer/bin/md-viewer serve [PATH]`; the first run builds its venv. The PDF tab also needs `brew install pango`.

## More

- [SKILL.md](SKILL.md): what Claude does with it, URL options for diffs, and handling notes.
- [DESIGN.md](DESIGN.md): the full spec: routes, diff, notes, security.
- [CHANGELOG.md](CHANGELOG.md): releases.
- [AGENTS.md](AGENTS.md): development notes (`make dev lint test`).
