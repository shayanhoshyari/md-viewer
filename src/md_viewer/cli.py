"""`md-serve [PATH] [--host H] [--port N]`: bind a socket, print the URL line, run uvicorn."""

from __future__ import annotations

import argparse
import socket
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI

from md_viewer.app import create_app
from md_viewer.registry import register, unregister


@dataclass(frozen=True)
class Target:
    """What to serve, from the command line, before any socket is bound."""

    root: Path
    host: str
    port: int
    page_path: str

    def url_line(self, port: int) -> str:
        return f"serving {self.root} at http://{self.host}:{port}/{self.page_path}"


def parse_args(argv: list[str] | None = None) -> Target:
    """Turn argv into a Target; a missing path exits with a usage error."""
    parser = argparse.ArgumentParser(prog="md-serve", description="Serve a Markdown and source browser.")
    parser.add_argument("path", nargs="?", default=Path.cwd(), type=Path, help="folder or file to serve")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=0, type=int, help="default: a free port")
    args = parser.parse_args(argv)

    target = args.path.resolve()
    if not target.exists():
        parser.error(f"{args.path} does not exist")
    root = target if target.is_dir() else target.parent
    page_path = "" if target == root else quote(target.name)
    return Target(root=root, host=args.host, port=args.port, page_path=page_path)


def main(argv: list[str] | None = None) -> int:
    target = parse_args(argv)
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
