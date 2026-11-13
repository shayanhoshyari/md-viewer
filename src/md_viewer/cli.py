"""`md-viewer serve` (bind a socket, print the URL line, run uvicorn), `notes`, `links` and `restart`."""

from __future__ import annotations

import argparse
import os
import socket
import sys
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI

from md_viewer.app import create_app
from md_viewer.layout import EXCLUDE, short_path
from md_viewer.links import check_links
from md_viewer.markdown import find_notes
from md_viewer.registry import live_servers, register, restart, unregister


@dataclass(frozen=True)
class Target:
    """`md-viewer serve`: what to serve, before any socket is bound."""

    path: Path
    root: Path
    host: str
    port: int
    page_path: str

    def url_line(self, port: int) -> str:
        return f"serving {self.root} at http://{self.host}:{port}/{self.page_path}"

    def restart_argv(self, port: int) -> list[str]:
        """The command `POST /_restart` re-executes: the same target, on the port actually bound."""
        return [sys.executable, "-m", "md_viewer", "serve", str(self.path), "--host", self.host, "--port", str(port)]


@dataclass(frozen=True)
class NotesTarget:
    """`md-viewer notes`: the markdown files to list notes from."""

    files: list[Path]


@dataclass(frozen=True)
class LinksTarget:
    """`md-viewer links`: the markdown files to check."""

    files: list[Path]


@dataclass(frozen=True)
class RestartTarget:
    """`md-viewer restart`: every running server."""


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
    links = commands.add_parser(
        "links",
        help="list relative links to missing files or headings",
        description="List relative links and images that point at a missing file or heading.",
    )
    links.add_argument("path", nargs="?", default=Path.cwd(), type=Path, help="markdown file or folder")
    commands.add_parser(
        "restart",
        help="restart every running server on the current code",
        description="Restart every running server on the current code, keeping its folder and port.",
    )
    return parser


def markdown_files(folder: Path) -> list[Path]:
    """Every .md file under `folder`, skipping what the file tree skips."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDE and (not d.startswith(".") or d == ".claude"))
        found.extend(Path(dirpath) / name for name in filenames if name.lower().endswith(".md"))
    return sorted(found)


def parse_args(argv: list[str] | None = None) -> Target | NotesTarget | LinksTarget | RestartTarget:
    """Turn argv into what to do; a missing path exits with a usage error."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "restart":
        return RestartTarget()
    if not args.path.exists():
        parser.error(f"{args.path} does not exist")
    if args.command in ("notes", "links"):
        files = markdown_files(args.path) if args.path.is_dir() else [args.path]
        return NotesTarget(files) if args.command == "notes" else LinksTarget(files)
    target = args.path.resolve()
    root = target if target.is_dir() else target.parent
    page_path = "" if target == root else quote(target.name)
    return Target(path=target, root=root, host=args.host, port=args.port, page_path=page_path)


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


def restart_all() -> int:
    """`md-viewer restart`: one line per server, exit status 1 when any failed."""
    servers = live_servers(None)
    if not servers:
        return 0
    with ThreadPoolExecutor(max_workers=min(32, len(servers))) as pool:
        failures = list(pool.map(restart, servers))
    for server, failure in zip(servers, failures, strict=True):
        label = short_path(Path(server.root))
        print(f"failed {label}: {failure}" if failure is not None else f"restarted {label}  {server.url}")
    return 1 if any(f is not None for f in failures) else 0


def main(argv: list[str] | None = None) -> int:
    target = parse_args(argv)
    if isinstance(target, RestartTarget):
        return restart_all()
    if isinstance(target, LinksTarget):
        problems = check_links(target.files, display_path)
        for problem in problems:
            print(problem)
        return 1 if problems else 0
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

    app = create_app(target.root, server_id, target.restart_argv(port))
    app.router.lifespan_context = lifespan
    try:
        uvicorn.Server(uvicorn.Config(app, log_level="info")).run(sockets=[sock])
    finally:
        unregister(server_id)
    return 0
