"""`md-viewer serve` (bind a socket, print the URL line, run uvicorn) and `md-viewer notes`."""

from __future__ import annotations

import argparse
import os
import socket
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI

from md_viewer.app import create_app
from md_viewer.layout import EXCLUDE
from md_viewer.markdown import find_notes
from md_viewer.registry import register, unregister


@dataclass(frozen=True)
class Target:
    """`md-viewer serve`: what to serve, before any socket is bound."""

    root: Path
    host: str
    port: int
    page_path: str

    def url_line(self, port: int) -> str:
        return f"serving {self.root} at http://{self.host}:{port}/{self.page_path}"


@dataclass(frozen=True)
class NotesTarget:
    """`md-viewer notes`: the markdown files to list notes from."""

    files: list[Path]


EXCERPT_LINES = 15


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="md-viewer", description="Browse markdown and source files, and their notes.")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    serve = commands.add_parser(
        "serve", help="serve a folder or file in the browser", description="Serve a folder or file in the browser."
    )
    serve.add_argument("path", nargs="?", default=Path.cwd(), type=Path, help="folder or file to serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=0, type=int, help="default: a free port")
    notes = commands.add_parser(
        "notes", help="list notes with the blocks they're on", description="List notes with the blocks they're on."
    )
    notes.add_argument("path", nargs="?", default=Path.cwd(), type=Path, help="markdown file or folder")
    return parser


def markdown_files(folder: Path) -> list[Path]:
    """Every .md file under `folder`, skipping what the file tree skips."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE and (not d.startswith(".") or d == ".claude"))
        found.extend(Path(dirpath) / name for name in filenames if name.lower().endswith(".md"))
    return sorted(found)


def parse_args(argv: list[str] | None = None) -> Target | NotesTarget:
    """Turn argv into what to do; a missing path exits with a usage error."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.path.exists():
        parser.error(f"{args.path} does not exist")
    if args.command == "notes":
        return NotesTarget(markdown_files(args.path) if args.path.is_dir() else [args.path])
    target = args.path.resolve()
    root = target if target.is_dir() else target.parent
    page_path = "" if target == root else quote(target.name)
    return Target(root=root, host=args.host, port=args.port, page_path=page_path)


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path)


def notes_report(files: list[Path]) -> str:
    """What `md-viewer notes` prints: each note with the block it's on."""
    entries: list[str] = []
    for path in files:
        for found in find_notes(path.read_text(encoding="utf-8", errors="replace")):
            if found.kind:
                where = (
                    f"{found.kind}, line {found.start}"
                    if found.start == found.end
                    else (f"{found.kind}, lines {found.start}-{found.end}")
                )
            else:
                where = "top of file"
            lines = [f"{display_path(path)}:{found.line}  {where}"]
            shown = found.source[:EXCERPT_LINES]
            lines.extend(f"  > {line}".rstrip() for line in shown)
            if len(found.source) > len(shown):
                lines.append(f"  > … {len(found.source) - len(shown)} more lines")
            if found.note.quote:
                lines.append(f"  quote: {found.note.quote}")
            lines.append(f"  note: {found.note.text}")
            entries.append("\n".join(lines))
    return "\n\n".join(entries)


def main(argv: list[str] | None = None) -> int:
    target = parse_args(argv)
    if isinstance(target, NotesTarget):
        report = notes_report(target.files)
        if report:
            print(report)
        return 0
    # Bind first so the printed URL has the real port when the OS picks one.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((target.host, target.port))
    port = sock.getsockname()[1]
    print(target.url_line(port), flush=True)
    server_id = register(target.root, target.host, port)

    # Unregister on lifespan shutdown: after Ctrl-C or SIGTERM, uvicorn re-raises the signal
    # once shutdown is done, so code after `run` never runs.
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        try:
            yield
        finally:
            unregister(server_id)

    app = create_app(target.root, server_id)
    app.router.lifespan_context = lifespan
    try:
        uvicorn.Server(uvicorn.Config(app, log_level="info")).run(sockets=[sock])
    finally:
        unregister(server_id)
    return 0
