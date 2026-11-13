# md-viewer development notes

`DESIGN.md` is the source of truth: change it first, then the code in `src/md_viewer/`, then `SKILL.md`, which links to it instead of repeating it.

- Using the viewer needs nothing beyond `bin/md-viewer`. `make dev` installs the dev tools.
- Run `make lint test` before handing off. Tests are offline and drive the app with `TestClient`.
- Tests don't run `static/client.js`. A change to it is checked in a real browser (the Chrome extension) on a scratch file served by `bin/md-viewer serve`, never on a file that matters.
- `tests/goldens/` holds saved responses. When a change is meant to alter output, run `make goldens` and review the diff.
- A test checks behavior the code computes. No golden or assertion that only restates a file or constant back to itself, such as a static asset copied byte for byte.
- Each user-visible change goes in `CHANGELOG.md` with a version bump in `pyproject.toml`.
- New work starts as a plan in `plans/NN-slug.md`.
- Code outside this folder imports only what `md_viewer/__init__.py` exports in `__all__`, the public API. A change to it is called out in `CHANGELOG.md`, and `tests/test_api.py` pins it.
- This folder is mirrored to the public repo `shayanhoshyari/md-viewer` by `make publish`, without `plans/` and `scripts/`; xiaoverse is the source of truth. Keep everything else here safe to publish: no personal names, paths or details, including in tests and goldens.
