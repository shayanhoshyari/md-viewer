"""The FastAPI app: static files and one route that serves every view."""

from __future__ import annotations

import codecs
import html
import json
import mimetypes
import os
import sys
import tempfile
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, ValidationError
from starlette.background import BackgroundTask

from md_viewer.diff import render_diff
from md_viewer.highlight import PYGMENTS_FORMATTER, render_source
from md_viewer.layout import CLIENT_JS, STYLE, directory_listing, page, resolve_safe, short_path, view_links
from md_viewer.markdown import LINE_OFFSET, note_targets, parse_markdown, render_markdown
from md_viewer.notes import NoteError, delete_note, set_note, version
from md_viewer.pdf import PDF_SETUP_HINT, render_pdf
from md_viewer.registry import live_servers, unregister
from md_viewer.scm import source_control_panel

BINARY_EXTS = {".gif", ".ico", ".jpeg", ".jpg", ".pdf", ".png", ".svg", ".webp"}
SOURCE_EXTS = {
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".py",
    ".pyi",
    ".sh",
    ".sql",
    ".toml",
    ".ts",
    ".yaml",
    ".yml",
}


def looks_like_text(path: Path) -> bool:
    """No NUL byte and valid UTF-8 in the first 8 KB."""
    with path.open("rb") as file:
        head = file.read(8192)
    if b"\0" in head:
        return False
    try:
        codecs.getincrementaldecoder("utf-8")().decode(head, final=False)
    except UnicodeDecodeError:
        return False
    return True


# Notes are written only from pages the viewer served on this machine.
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]"}


class NoteDelete(BaseModel):
    """`DELETE /_notes`: remove the note on `block` of the file at `path`, as the page showed it."""

    path: str
    version: str
    block: int


class NoteSet(NoteDelete):
    """`PUT /_notes`: set the note on `block`, replacing the one it has."""

    quote: str = ""
    text: str


def error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def same_origin(request: Request) -> bool:
    """Host is a loopback name (not a rebound DNS name) and Origin is this same server."""
    host = request.headers.get("host", "")
    hostname = host.rsplit(":", 1)[0] if not host.endswith("]") else host
    return hostname in LOOPBACK_HOSTS and request.headers.get("origin") == f"http://{host}"


def write_atomically(path: Path, text: str) -> None:
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as file:
            file.write(text)
        os.chmod(temp, path.stat().st_mode & 0o7777)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


def apply_note(root: Path, note: NoteDelete) -> JSONResponse:
    try:
        target = resolve_safe(root, note.path)
    except HTTPException:
        return error(404, "not found")
    if not target.is_file():
        return error(404, "not found")
    if target.suffix.lower() != ".md":
        return error(400, "notes are only for markdown files")
    data = target.read_bytes()
    if version(data) != note.version:
        return error(409, "The file changed since this page loaded. Reload to see it.")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return error(400, "the file is not UTF-8")
    try:
        tokens, env, source = parse_markdown(text)
        targets = note_targets(tokens, source, env[LINE_OFFSET])
        if not 0 <= note.block < len(targets):
            raise NoteError("no such block")
        block = targets[note.block][2]
        new = set_note(text, block, note.text, note.quote) if isinstance(note, NoteSet) else delete_note(text, block)
    except NoteError as exc:
        return error(400, str(exc))
    write_atomically(target, new)
    return JSONResponse({"version": version(new.encode("utf-8"))})


def exec_restart(server_id: str | None, argv: list[str]) -> None:
    """Replace this process with `argv`, after removing its registry entry."""
    if server_id is not None:
        unregister(server_id)
    sys.stdout.flush()
    sys.stderr.flush()
    os.execv(argv[0], argv)


def create_app(root: Path, server_id: str | None = None, restart_argv: list[str] | None = None) -> FastAPI:
    """`server_id` is this server's registry id; without one, `/_servers` lists only this server.

    `restart_argv` is the command `POST /_restart` replaces the process with; without one, it answers 404.
    """
    # API docs live under the viewer's own `_` prefix; /docs and the like belong to the served folder.
    app = FastAPI(
        title="md-viewer",
        version=package_version("md-viewer"),
        docs_url="/_docs",
        redoc_url=None,
        openapi_url="/_openapi.json",
    )

    @app.get("/_static/style.css", include_in_schema=False)
    def style() -> Response:
        return Response(STYLE, media_type="text/css")

    @app.get("/_static/pygments.css", include_in_schema=False)
    def pygments_css() -> Response:
        return Response(PYGMENTS_FORMATTER.get_style_defs(".code-block"), media_type="text/css")

    @app.get("/_static/client.js", include_in_schema=False)
    def client() -> Response:
        return Response(CLIENT_JS, media_type="text/javascript")

    @app.get("/_whoami")
    def whoami() -> JSONResponse:
        return JSONResponse({"id": server_id, "root": str(root)})

    @app.get("/_servers")
    def servers() -> JSONResponse:
        found = [s for s in live_servers(server_id) if s.id != server_id] if server_id is not None else []
        listed = [{"root": s.root, "label": short_path(Path(s.root)), "url": s.url, "current": False} for s in found]
        listed.append({"root": str(root), "label": short_path(root), "url": "/", "current": True})
        return JSONResponse(sorted(listed, key=lambda s: s["root"]))

    @app.post("/_restart", status_code=202)
    def restart() -> JSONResponse:
        """Reload the code: the server re-executes itself on the same folder and port, after this answer."""
        if restart_argv is None:
            return error(404, "this server can't restart itself")
        return JSONResponse(
            {"restarting": True}, status_code=202, background=BackgroundTask(exec_restart, server_id, restart_argv)
        )

    async def note_request(request: Request, model: type[NoteDelete]) -> NoteDelete | JSONResponse:
        """The request's note, or the error to answer with."""
        if not same_origin(request):
            return error(403, "notes are accepted only from this viewer's own pages")
        if request.headers.get("content-type", "").split(";")[0].strip() != "application/json":
            return error(415, "send JSON")
        try:
            return model.model_validate(json.loads(await request.body()))
        except (ValueError, ValidationError) as exc:
            return error(400, f"bad request: {exc}")

    def body_schema(model: type[BaseModel]) -> dict[str, Any]:
        # The body is read by hand, so the origin and JSON checks come first; this is for the docs.
        return {
            "requestBody": {"content": {"application/json": {"schema": model.model_json_schema()}}, "required": True}
        }

    @app.put("/_notes", openapi_extra=body_schema(NoteSet))
    async def set_note_route(request: Request) -> Response:
        """Set a block's note, replacing the one it has."""
        note = await note_request(request, NoteSet)
        return note if isinstance(note, JSONResponse) else apply_note(root, note)

    @app.delete("/_notes", openapi_extra=body_schema(NoteDelete))
    async def delete_note_route(request: Request) -> Response:
        """Remove a block's note."""
        note = await note_request(request, NoteDelete)
        return note if isinstance(note, JSONResponse) else apply_note(root, note)

    @app.get("/{request_path:path}", include_in_schema=False)
    def serve(request: Request, request_path: str = "", view: str = "") -> Response:
        target = resolve_safe(root, request_path)
        if not target.exists():
            raise HTTPException(status_code=404)
        rel = target.relative_to(root)
        if target.is_dir():
            for index in ("README.md", "AGENTS.md"):
                if (target / index).exists():
                    href = "/" + quote((rel / index).as_posix())
                    return RedirectResponse(href)
            return HTMLResponse(page(root, rel.as_posix() or ".", directory_listing(target, rel), rel))
        suffix = target.suffix.lower()
        is_text = suffix in SOURCE_EXTS or target.name in {"Makefile", "OWNERS"}
        is_markdown = suffix == ".md"
        if view in {"diff", "raw"} and not is_text:
            # Files of other types get a diff and a plain-text Raw view when they look like text,
            # so the source control panel's links stay in the viewer instead of downloading.
            looks_text = suffix not in BINARY_EXTS and looks_like_text(target)
            if view == "raw" and looks_text:
                return Response(target.read_bytes(), media_type="text/plain; charset=utf-8")
            if view == "diff":
                views = view_links(rel, "diff", markdown=False, source=False, raw=looks_text)
                diff = render_diff(target, request.query_params, binary=not looks_text)
                panel = ""
                if diff.repo is not None and diff.request is not None:
                    panel = source_control_panel(diff.repo, root, target, diff.request, diff.selection)
                return HTMLResponse(page(root, target.name, diff.body, rel, views, panel), status_code=diff.status)
        if suffix in BINARY_EXTS or not is_text:
            media_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            return Response(target.read_bytes(), media_type=media_type)
        if view == "raw":
            return Response(target.read_bytes(), media_type="text/plain; charset=utf-8")
        if view == "diff":
            views = view_links(rel, "diff", markdown=is_markdown)
            diff = render_diff(target, request.query_params, markdown=is_markdown)
            panel = ""
            if diff.repo is not None and diff.request is not None:
                panel = source_control_panel(diff.repo, root, target, diff.request, diff.selection)
            return HTMLResponse(page(root, target.name, diff.body, rel, views, panel), status_code=diff.status)
        if is_markdown and view == "pdf":
            filename = quote(target.with_suffix(".pdf").name)
            headers = {"Content-Disposition": f"inline; filename*=UTF-8''{filename}"}
            try:
                pdf = render_pdf(target, rel)
            except OSError:
                body = f'<div class="markdown-body"><p>{html.escape(PDF_SETUP_HINT)}</p></div>'
                views = view_links(rel, "pdf", markdown=True)
                return HTMLResponse(page(root, target.name, body, rel, views), status_code=500)
            return Response(pdf, media_type="application/pdf", headers=headers)
        if is_markdown and view != "source":
            notes_attrs = (
                f' data-notes-path="{html.escape(rel.as_posix())}" data-notes-version="{version(target.read_bytes())}"'
            )
            body = f'<div class="markdown-body"{notes_attrs}>{render_markdown(target, notes=True)}</div>'
            views = view_links(rel, "rendered", markdown=True)
            return HTMLResponse(page(root, target.name, body, rel, views))
        views = view_links(rel, "source", markdown=is_markdown)
        return HTMLResponse(page(root, target.name, render_source(target), rel, views))

    return app
