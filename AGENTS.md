# md-viewer development notes

`DESIGN.md` is the source of truth: change it first, then the code in `src/md_viewer/`, then `SKILL.md`, which links to it instead of repeating it.

- Using the viewer needs nothing beyond `bin/md-serve`. `make dev` installs the dev tools.
- Run `make lint test` before handing off. Tests are offline and drive the app with `TestClient`.
- Tests don't run `static/client.js`. A change to it is checked in a real browser (the Chrome extension) on a scratch file served by `bin/md-serve`, never on a file that matters.
- `tests/goldens/` holds saved responses. When a change is meant to alter output, run `make goldens` and review the diff.
- Each user-visible change goes in `CHANGELOG.md` with a version bump in `pyproject.toml`.
- New work starts as a plan in `plans/NN-slug.md`.
- This folder is mirrored to the public repo `shayanhoshyari/md-viewer` by `make publish`, without `plans/`; xiaoverse is the source of truth. Keep everything else here safe to publish: no personal names, paths or details, including in tests and goldens.
