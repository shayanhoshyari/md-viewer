"""Running servers register in a shared folder; readers probe each entry's /_whoami and prune the dead ones."""

from __future__ import annotations

import http.client
import json
import os
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

PROBE_TIMEOUT = 0.3


def state_dir() -> Path:
    """The registry folder; `MD_VIEWER_STATE_DIR` overrides it."""
    override = os.environ.get("MD_VIEWER_STATE_DIR")
    if override is not None and override != "":
        return Path(override)
    base = os.environ.get("XDG_STATE_HOME") or str(Path.home() / ".local" / "state")
    return Path(base) / "md-viewer" / "servers"


@dataclass(frozen=True)
class Server:
    id: str
    port: int
    root: str

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/"


def register(root: Path, host: str, port: int) -> str:
    """Write this server's entry and return its id."""
    folder = state_dir()
    folder.mkdir(parents=True, exist_ok=True)
    server_id = uuid.uuid4().hex
    entry = {
        "id": server_id,
        "pid": os.getpid(),
        "host": host,
        "port": port,
        "root": str(root),
        "started": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    fd, temp = tempfile.mkstemp(dir=folder, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(entry, file)
        os.replace(temp, folder / f"{server_id}.json")
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise
    return server_id


def unregister(server_id: str) -> None:
    (state_dir() / f"{server_id}.json").unlink(missing_ok=True)


def probe(port: int, server_id: str) -> Literal["alive", "dead", "busy"]:
    """Whether the md-viewer with this id answers on this port."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=PROBE_TIMEOUT)
    try:
        conn.request("GET", "/_whoami")
        response = conn.getresponse()
        body = json.loads(response.read())
    except TimeoutError:
        return "busy"
    except (OSError, ValueError, http.client.HTTPException):
        return "dead"
    finally:
        conn.close()
    return "alive" if isinstance(body, dict) and body.get("id") == server_id else "dead"


def read_entry(path: Path) -> Server | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Server(id=str(data["id"]), port=int(data["port"]), root=str(data["root"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def live_servers(self_id: str | None) -> list[Server]:
    """Every registered server that answers, this one included without a probe; dead entries are deleted."""
    folder = state_dir()
    try:
        paths = sorted(folder.glob("*.json"))
    except OSError:
        return []
    found: list[tuple[Path, Server]] = []
    for path in paths:
        entry = read_entry(path)
        if entry is None:
            path.unlink(missing_ok=True)
        else:
            found.append((path, entry))
    others = [(path, entry) for path, entry in found if entry.id != self_id]
    with ThreadPoolExecutor(max_workers=max(1, min(32, len(others)))) as pool:
        states = list(pool.map(lambda item: probe(item[1].port, item[1].id), others))
    alive = [entry for path, entry in found if entry.id == self_id]
    for (path, entry), state in zip(others, states, strict=True):
        if state == "alive":
            alive.append(entry)
        elif state == "dead":
            path.unlink(missing_ok=True)
    return sorted(alive, key=lambda s: s.root)
