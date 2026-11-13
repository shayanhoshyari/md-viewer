"""The public API: what `md_viewer` exports, and that importing it doesn't load the server."""

from __future__ import annotations

import subprocess
import sys

import md_viewer


def test_exports() -> None:
    assert sorted(md_viewer.__all__) == ["Link", "check_links", "link_problem", "links_of"]
    assert all(hasattr(md_viewer, name) for name in md_viewer.__all__)


def test_import_does_not_load_the_server() -> None:
    code = "import sys, md_viewer; print(sorted(m for m in ('fastapi', 'uvicorn', 'weasyprint') if m in sys.modules))"
    out = subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True).stdout
    assert out.strip() == "[]"
