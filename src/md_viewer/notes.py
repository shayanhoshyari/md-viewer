"""Notes: one-line HTML comments in a markdown file, and the only edits the viewer may make to it."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

# `<!-- note: text -->` or `<!-- note "quote": text -->`, alone on its line, indented or not.
NOTE_RE = re.compile(r'^([ \t]*)<!-- note(?: "((?:[^"\\]|\\.)*)")?:[ \t]*(.*?)[ \t]*-->[ \t]*$')


@dataclass(frozen=True)
class Note:
    indent: str
    quote: str
    text: str


@dataclass(frozen=True)
class Target:
    """Where a new note on one block goes: before file line `index` (0-based), with `indent`."""

    index: int
    indent: str


class NoteError(ValueError):
    """A request the file can't satisfy; the message is shown to the user."""


def parse_note(line: str) -> Note | None:
    match = NOTE_RE.match(line)
    if not match:
        return None
    indent, quote, text = match.groups()
    return Note(indent, re.sub(r"\\(.)", r"\1", quote or ""), text)


def clean(text: str) -> str:
    """One line that can't close the comment early."""
    text = " ".join(text.split())
    while "-->" in text:
        text = text.replace("-->", "-- >")
    return text


def format_note(text: str, quote: str = "", indent: str = "") -> str:
    text = clean(text)
    quote = clean(quote).replace("\\", "\\\\").replace('"', '\\"')
    head = f'note "{quote}"' if quote else "note"
    return f"{indent}<!-- {head}: {text} -->"


def version(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def split_lines(text: str) -> tuple[list[str], str]:
    """The lines and the newline they use; a final newline leaves a last empty element."""
    newline = "\r\n" if "\r\n" in text else "\n"
    return text.split(newline), newline


def without_notes(text: str) -> list[str]:
    return [line for line in split_lines(text)[0] if not NOTE_RE.match(line)]


def add_note(text: str, target: Target, note_text: str, quote: str = "") -> str:
    lines, newline = split_lines(text)
    lines.insert(target.index, format_note(note_text, quote, target.indent))
    return checked(text, newline.join(lines))


def edit_note(text: str, line: int, note_text: str, quote: str | None = None) -> str:
    """Replace the note on 1-based `line`; `quote=None` keeps its quote."""
    lines, newline = split_lines(text)
    old = note_at(lines, line)
    lines[line - 1] = format_note(note_text, old.quote if quote is None else quote, old.indent)
    return checked(text, newline.join(lines))


def delete_note(text: str, line: int) -> str:
    lines, newline = split_lines(text)
    note_at(lines, line)
    del lines[line - 1]
    return checked(text, newline.join(lines))


def note_at(lines: list[str], line: int) -> Note:
    note = parse_note(lines[line - 1]) if 1 <= line <= len(lines) else None
    if note is None:
        raise NoteError(f"line {line} is not a note")
    return note


def checked(old: str, new: str) -> str:
    """The new text, after making sure only note lines differ from the old."""
    if without_notes(old) != without_notes(new):
        raise NoteError("the edit would change more than note lines")
    return new
