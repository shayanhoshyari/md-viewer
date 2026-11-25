"""`md-viewer.toml`: what the file tree, listings, `notes` and `links` leave out, and the walk that applies it."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

CONFIG_NAME = "md-viewer.toml"
LISTS = ("tree", "check")


class ConfigError(Exception):
    """A `md-viewer.toml` that can't be used; the message names the file."""


@dataclass(frozen=True)
class Ignore:
    """One `ignore` list: names match at any depth, paths are relative to `base`, the toml's folder."""

    base: Path
    names: frozenset[str] = frozenset()
    paths: frozenset[str] = frozenset()

    def __call__(self, path: Path) -> bool:
        if path.name in self.names:
            return True
        if not self.paths:
            return False
        try:
            return path.relative_to(self.base).as_posix() in self.paths
        except ValueError:
            return False


@dataclass(frozen=True)
class Config:
    tree: Ignore
    check: Ignore


def parse_config(text: str, base: Path, source: str) -> Config:
    """The config in `text`, a toml from `source` (named in errors), with paths relative to `base`."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{source}: {exc}") from None
    unknown = sorted(set(data) - set(LISTS))
    if unknown:
        raise ConfigError(f"{source}: unknown key {unknown[0]!r}; expected [tree] and [check]")
    lists: dict[str, Ignore] = {}
    for name in LISTS:
        table = data.get(name, {})
        if not isinstance(table, dict) or set(table) - {"ignore"}:
            raise ConfigError(f"{source}: [{name}] holds only `ignore`")
        entries = table.get("ignore", [])
        if not isinstance(entries, list) or not all(isinstance(e, str) for e in entries):
            raise ConfigError(f"{source}: [{name}] ignore is not a list of strings")
        names: set[str] = set()
        paths: set[str] = set()
        for entry in entries:
            cleaned = entry.strip("/")
            if not cleaned or ".." in cleaned.split("/") or "." in cleaned.split("/"):
                raise ConfigError(f"{source}: [{name}] ignore has a bad entry {entry!r}")
            (paths if "/" in cleaned else names).add(cleaned)
        lists[name] = Ignore(base, frozenset(names), frozenset(paths))
    return Config(**lists)


def find_config(start: Path) -> Config:
    """The first `md-viewer.toml` in `start` or a folder above it, else the packaged default."""
    start = start.resolve()
    for folder in (start, *start.parents):
        candidate = folder / CONFIG_NAME
        if candidate.is_file():
            return parse_config(candidate.read_text(encoding="utf-8"), folder, str(candidate))
    default = files("md_viewer").joinpath("default.toml").read_text(encoding="utf-8")
    return parse_config(default, start, "md_viewer/default.toml")


def walk(folder: Path, ignored: Ignore) -> list[Path]:
    """Every file under `folder`, sorted, skipping symlinks and what `ignored` matches."""
    found: list[Path] = []

    def visit(dir_path: Path) -> None:
        try:
            entries = list(os.scandir(dir_path))
        except OSError:
            return
        for entry in entries:
            path = Path(entry.path)
            if entry.is_symlink() or ignored(path):
                continue
            if entry.is_dir():
                visit(path)
            elif entry.is_file():
                found.append(path)

    visit(folder)
    return sorted(found)


def listing(folder: Path, ignored: Ignore) -> list[Path]:
    """The entries of `folder` itself, sorted, skipping symlinks and what `ignored` matches."""
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return []
    return sorted(Path(e.path) for e in entries if not e.is_symlink() and not ignored(Path(e.path)))
