"""`md-viewer serve` (bind a socket, print the URL line, run uvicorn; or detach a child that does), `notes`, `links`,
`list` and `restart`."""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import os
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import AsyncGenerator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from rich import box
from rich.console import Console
from rich.table import Table

from md_viewer.app import create_app
from md_viewer.config import ConfigError, find_config, walk
from md_viewer.layout import short_path
from md_viewer.links import check_links
from md_viewer.markdown import find_notes
from md_viewer.registry import live_servers, register, restart, unregister


@dataclass(frozen=True)
class Target:
    """`md-viewer serve`: what to serve, before any socket is bound."""

    root: Path
    host: str
    port: int
    detach: bool = False
    log_file: Path | None = None

    def url_line(self, port: int) -> str:
        return f"serving {self.root} at http://{self.host}:{port}/"

    def serve_argv(self, port: int) -> list[str]:
        """`md-viewer serve` for this target in the foreground, through this Python."""
        return [sys.executable, "-m", "md_viewer", "serve", str(self.root), "--host", self.host, "--port", str(port)]

    def restart_argv(self, port: int) -> list[str]:
        """The command `POST /_restart` re-executes: the same target, on the port actually bound, same log file."""
        log = [] if self.log_file is None else ["--log-file", str(self.log_file)]
        return [*self.serve_argv(port), *log]

    def detached_argv(self) -> list[str]:
        """The child `--detach` starts: a foreground server logging to a file, the default one unless given."""
        return [*self.serve_argv(self.port), "--log-file", *([] if self.log_file is None else [str(self.log_file)])]


@dataclass(frozen=True)
class NotesTarget:
    """`md-viewer notes`: the markdown files to list notes from."""

    files: list[Path]


@dataclass(frozen=True)
class LinksTarget:
    """`md-viewer links`: the markdown files to check."""

    files: list[Path]


@dataclass(frozen=True)
class ListTarget:
    """`md-viewer list`: every running server."""


@dataclass(frozen=True)
class RestartTarget:
    """`md-viewer restart`: every running server."""


EXCERPT_LINES = 15
DETACH_TIMEOUT = 15.0
LOG_MAX_BYTES = 1_000_000
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def default_log_file(pid: int) -> Path:
    """Where a server with this process ID logs when `--log-file` has no value."""
    return Path(tempfile.gettempdir()) / f"md-viewer-{pid}.log"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="md-viewer", description="Browse markdown and source files, and their notes.")
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")
    serve = commands.add_parser(
        "serve", help="serve a folder in the browser", description="Serve a folder in the browser."
    )
    serve.add_argument("path", nargs="?", default=Path.cwd(), type=Path, help="folder to serve")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", default=0, type=int, help="default: a free port")
    serve.add_argument(
        "-d", "--detach", action="store_true", help="run in the background; print the URL once it is up, then return"
    )
    serve.add_argument(
        "--log-file",
        nargs="?",
        type=Path,
        const=default_log_file(os.getpid()),
        help="log to a file, rotated at 1 MB, instead of the terminal; no value: $TMPDIR/md-viewer-<pid>.log",
    )
    notes = commands.add_parser(
        "notes", help="list notes with the blocks they're on", description="List notes with the blocks they're on."
    )
    notes.add_argument("path", nargs="?", default=Path.cwd(), type=Path, help="folder of markdown files")
    links = commands.add_parser(
        "links",
        help="list relative links to missing files or headings",
        description="List relative links and images that point at a missing file or heading.",
    )
    links.add_argument("path", nargs="?", default=Path.cwd(), type=Path, help="folder of markdown files")
    commands.add_parser(
        "list", help="list running servers and their URLs", description="List every running server and its URL."
    )
    commands.add_parser(
        "restart",
        help="restart every running server on the current code",
        description="Restart every running server on the current code, keeping its folder and port.",
    )
    return parser


def markdown_files(folder: Path) -> list[Path]:
    """Every .md file under `folder`, skipping what the config's `[check]` list ignores."""
    return [p for p in walk(folder, find_config(folder).check) if p.suffix.lower() == ".md"]


def parse_args(argv: list[str] | None = None) -> Target | NotesTarget | LinksTarget | ListTarget | RestartTarget:
    """Turn argv into what to do; a path that isn't a folder, or a bad config, exits with a usage error."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "list":
        return ListTarget()
    if args.command == "restart":
        return RestartTarget()
    if not args.path.exists():
        parser.error(f"{args.path} does not exist")
    if not args.path.is_dir():
        parser.error(f"{args.path} is not a folder")
    if args.command in ("notes", "links"):
        try:
            files = markdown_files(args.path)
        except ConfigError as exc:
            parser.error(str(exc))
        return NotesTarget(files) if args.command == "notes" else LinksTarget(files)
    log_file = None if args.log_file is None else args.log_file.absolute()
    return Target(
        root=args.path.resolve(),
        host=args.host,
        port=args.port,
        detach=args.detach,
        log_file=log_file,
    )


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


def list_servers() -> int:
    """`md-viewer list`: a table of the running servers, one row each."""
    servers = live_servers(None)
    if not servers:
        return 0
    rows = [(short_path(Path(s.root)), str(s.port), str(s.pid), s.url) for s in servers]
    table = Table(box=box.SIMPLE_HEAD)
    table.add_column("Path", overflow="fold")  # the only column that gives up width on a narrow terminal
    for index, name in enumerate(("Port", "PID", "URL"), start=1):
        widest = max(len(name), *(len(row[index]) for row in rows))
        table.add_column(name, justify="left" if name == "URL" else "right", no_wrap=True, min_width=widest)
    for row in rows:
        table.add_row(*row)
    Console().print(table)
    return 0


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


def log_to_file(path: Path, max_bytes: int = LOG_MAX_BYTES) -> None:
    """Send every log record at INFO and up to `path`, rotated into `path` and `path.1`, uncaught errors included."""
    handler = logging.handlers.RotatingFileHandler(path, maxBytes=max_bytes, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    sys.excepthook = lambda *exc: logging.getLogger("md_viewer").critical("uncaught error", exc_info=exc)


def remove_logs(path: Path | None) -> None:
    if path is not None:
        for file in (path, path.with_name(path.name + ".1")):
            file.unlink(missing_ok=True)


def detach(target: Target) -> int:
    """`serve --detach`: reuse a live server on the same root, or start one in its own session and wait for it."""
    for server in live_servers(None):
        if Path(server.root) == target.root:
            print(target.url_line(server.port), flush=True)
            return 0
    child = subprocess.Popen(
        target.detached_argv(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    log = target.log_file or default_log_file(child.pid)
    deadline = time.monotonic() + DETACH_TIMEOUT
    while child.poll() is None and time.monotonic() < deadline:
        for server in live_servers(None):
            if server.pid == child.pid:
                print(target.url_line(server.port), flush=True)
                return 0
        time.sleep(0.1)
    if child.poll() is None:
        child.kill()
    print(f"failed to start, see {log}", file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    target = parse_args(argv)
    if isinstance(target, ListTarget):
        return list_servers()
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
    if target.detach:
        return detach(target)
    if target.log_file is not None:
        log_to_file(target.log_file)
    # Bind first so the printed URL has the real port when the OS picks one.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((target.host, target.port))
    port = sock.getsockname()[1]
    print(target.url_line(port), flush=True)
    if target.log_file is not None:
        logging.getLogger("md_viewer").info(target.url_line(port))
    server_id = register(target.root, target.host, port)

    # Unregister on lifespan shutdown: after Ctrl-C or SIGTERM, uvicorn re-raises the signal
    # once shutdown is done, so code after `run` never runs.
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        try:
            yield
        finally:
            unregister(server_id)
            remove_logs(target.log_file)

    app = create_app(target.root, server_id, target.restart_argv(port))
    app.router.lifespan_context = lifespan
    try:
        # With a log file, uvicorn leaves logging alone and its records reach the root logger's file.
        log_config = uvicorn.config.LOGGING_CONFIG if target.log_file is None else None
        uvicorn.Server(uvicorn.Config(app, log_level="info", log_config=log_config)).run(sockets=[sock])
    finally:
        unregister(server_id)
        remove_logs(target.log_file)
    return 0
