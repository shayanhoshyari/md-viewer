UV := $(shell command -v uv 2>/dev/null)

.PHONY: dev lint test goldens publish _check_uv

dev: _check_uv
	$(UV) sync --extra dev

lint: _check_uv
	$(UV) run --extra dev ruff check .
	$(UV) run --extra dev ruff format --check .
	$(UV) run --extra dev ty check src/

test: _check_uv
	$(UV) run --extra dev pytest -q tests/

# Regenerate the saved responses in tests/goldens/ from the current code; review the diff.
goldens: _check_uv
	MD_VIEWER_UPDATE_GOLDENS=1 $(UV) run --extra dev pytest -q tests/test_goldens.py

# Mirror the committed state of this folder, without plans/, to the public repo.
publish: _check_uv
	$(UV) run --script scripts/publish.py

_check_uv:
ifndef UV
	$(error uv not found. Install it from https://docs.astral.sh/uv/getting-started/installation/)
endif
