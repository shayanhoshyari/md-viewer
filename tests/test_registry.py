"""The server registry: entries, probes in parallel, pruning, and the /_servers route."""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from md_viewer import registry
from md_viewer.app import create_app


@pytest.fixture(autouse=True)
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "state"
    monkeypatch.setenv("MD_VIEWER_STATE_DIR", str(folder))
    return folder


def stub(answer_id: str, delay: float = 0.0) -> ThreadingHTTPServer:
    """A server that answers /_whoami with `answer_id`, after `delay` seconds."""

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            time.sleep(delay)
            body = json.dumps({"id": answer_id}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


@pytest.fixture
def stubs() -> Iterator[list[ThreadingHTTPServer]]:
    made: list[ThreadingHTTPServer] = []
    yield made
    for server in made:
        server.shutdown()
        server.server_close()


def entry(state: Path, server_id: str, port: int, root: str) -> Path:
    state.mkdir(parents=True, exist_ok=True)
    path = state / f"{server_id}.json"
    path.write_text(json.dumps({"id": server_id, "pid": 1, "host": "127.0.0.1", "port": port, "root": root}))
    return path


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_register_and_unregister(state: Path, tmp_path: Path) -> None:
    server_id = registry.register(tmp_path, "127.0.0.1", 8123)
    data = json.loads((state / f"{server_id}.json").read_text())
    assert data["port"] == 8123 and data["root"] == str(tmp_path) and data["id"] == server_id
    assert [p.name for p in state.iterdir()] == [f"{server_id}.json"]
    registry.unregister(server_id)
    assert list(state.iterdir()) == []


def test_live_entry_is_kept(state: Path, stubs: list[ThreadingHTTPServer]) -> None:
    stubs.append(stub("live"))
    entry(state, "live", stubs[0].server_address[1], "/a")
    assert [s.root for s in registry.live_servers("self")] == ["/a"]


def test_dead_port_is_pruned(state: Path) -> None:
    path = entry(state, "dead", free_port(), "/dead")
    assert registry.live_servers("self") == []
    assert not path.exists()


def test_wrong_id_is_pruned(state: Path, stubs: list[ThreadingHTTPServer]) -> None:
    stubs.append(stub("someone-else"))
    path = entry(state, "mine", stubs[0].server_address[1], "/a")
    assert registry.live_servers("self") == []
    assert not path.exists()


def test_corrupt_entry_is_pruned(state: Path) -> None:
    state.mkdir()
    (state / "bad.json").write_text("{not json")
    assert registry.live_servers("self") == []
    assert list(state.iterdir()) == []


def test_silent_server_is_hidden_but_kept(state: Path) -> None:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen()  # accepts connections, never answers
        path = entry(state, "busy", sock.getsockname()[1], "/busy")
        assert registry.live_servers("self") == []
        assert path.exists()


def test_probes_run_in_parallel(state: Path, stubs: list[ThreadingHTTPServer]) -> None:
    for n in range(5):
        stubs.append(stub(f"slow{n}", delay=0.2))
        entry(state, f"slow{n}", stubs[-1].server_address[1], f"/slow{n}")
    start = time.monotonic()
    assert len(registry.live_servers("self")) == 5
    assert time.monotonic() - start < 0.6


def test_own_entry_is_not_probed(state: Path) -> None:
    entry(state, "self", free_port(), "/me")
    assert [s.id for s in registry.live_servers("self")] == ["self"]


def test_servers_route(state: Path, tmp_path: Path, stubs: list[ThreadingHTTPServer]) -> None:
    stubs.append(stub("other"))
    entry(state, "other", stubs[0].server_address[1], "/other")
    entry(state, "self", 1, str(tmp_path))
    client = TestClient(create_app(tmp_path, "self"))
    assert client.get("/_whoami").json() == {"id": "self", "root": str(tmp_path)}
    listed = client.get("/_servers").json()
    port = stubs[0].server_address[1]
    assert {"root": "/other", "label": "/other", "url": f"http://127.0.0.1:{port}/", "current": False} in listed
    assert {"root": str(tmp_path), "label": str(tmp_path), "url": "/", "current": True} in listed
    assert len(listed) == 2


def test_servers_route_without_id(tmp_path: Path) -> None:
    listed = TestClient(create_app(tmp_path)).get("/_servers").json()
    assert listed == [{"root": str(tmp_path), "label": str(tmp_path), "url": "/", "current": True}]
