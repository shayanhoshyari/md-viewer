"""Notes: HTML comments ending a line of a markdown file, and the only edits the viewer may make to it."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

# `<!-- note: text -->` or `<!-- note "quote": text -->`, ending its line. Before it: whitespace only
# (a note line, `lead` is its indent) or text ending in `|` (a note on a table row).
NOTE_RE = re.compile(
    r'^(?P<lead>[ \t]*|.*\|[ \t]*)<!-- note(?: "(?P<quote>(?:[^"\\]|\\.)*)")?:[ \t]*(?P<text>.*?)[ \t]*-->[ \t]*$'
)


@dataclass(frozen=True)
class Note:
    lead: str
    quote: str
    text: str

    @property
    def on_row(self) -> bool:
        return bool(self.lead.strip())


@dataclass(frozen=True)
class Target:
    """Where one block's note goes, as 0-based file lines.

    A row's note ends the row's line `index`. Any other block's new note line is inserted before line
    `index`, with `indent`. `note` is the line of the block's (first) note, if it has one.
    """

    index: int
    indent: str
    row: bool = False
    note: int | None = None


class NoteError(ValueError):
    """A request the file can't satisfy; the message is shown to the user."""


def parse_note(line: str) -> Note | None:
    match = NOTE_RE.match(line)
    if not match:
        return None
    quote = re.sub(r"\\(.)", r"\1", match["quote"] or "")
    return Note(match["lead"], quote, match["text"].replace("\\|", "|"))


def clean(text: str) -> str:
    """One line that can't close the comment early."""
    text = " ".join(text.split())
    while "-->" in text:
        text = text.replace("-->", "-- >")
    return text


def format_note(text: str, quote: str = "", lead: str = "") -> str:
    """The note as it ends a line: `lead` is a note line's indent, or a row's line plus one space."""
    text = clean(text).replace("|", "\\|")
    quote = clean(quote).replace("\\", "\\\\").replace('"', '\\"').replace("|", "\\|")
    head = f'note "{quote}"' if quote else "note"
    return f"{lead}<!-- {head}: {text} -->"


def version(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def split_lines(text: str) -> tuple[list[str], str]:
    """The lines and the newline they use; a final newline leaves a last empty element."""
    newline = "\r\n" if "\r\n" in text else "\n"
    return text.split(newline), newline


def row_without_note(lead: str) -> str:
    """A row's line once its note and the one space before it are gone."""
    return lead[:-1] if lead.endswith(" ") else lead


def without_notes(text: str) -> list[str]:
    kept: list[str] = []
    for line in split_lines(text)[0]:
        note = parse_note(line)
        if note is None:
            kept.append(line)
        elif note.on_row:
            kept.append(row_without_note(note.lead))
    return kept


def set_note(text: str, target: Target, note_text: str, quote: str = "") -> str:
    """Write the block's note: replace the one it has, else add one."""
    if not note_text.strip():
        raise NoteError("a note needs text")
    lines, newline = split_lines(text)
    if target.note is not None:
        old = note_at(lines, target.note)
        lines[target.note] = format_note(note_text, quote, old.lead)
    elif target.row:
        lines[target.index] = format_note(note_text, quote, lines[target.index] + " ")
    else:
        lines.insert(target.index, format_note(note_text, quote, target.indent))
    return checked(text, newline.join(lines))


def delete_note(text: str, target: Target) -> str:
    lines, newline = split_lines(text)
    if target.note is None:
        raise NoteError("this block has no note")
    old = note_at(lines, target.note)
    if old.on_row:
        lines[target.note] = row_without_note(old.lead)
    else:
        del lines[target.note]
    return checked(text, newline.join(lines))


def note_at(lines: list[str], index: int) -> Note:
    note = parse_note(lines[index]) if 0 <= index < len(lines) else None
    if note is None:
        raise NoteError(f"line {index + 1} is not a note")
    return note


def checked(old: str, new: str) -> str:
    """The new text, after making sure only notes differ from the old."""
    if without_notes(old) != without_notes(new):
        raise NoteError("the edit would change more than notes")
    return new
