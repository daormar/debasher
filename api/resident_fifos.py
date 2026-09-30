"""
"Talk to FIFOs" in a resident program (see "Observing and talking to a live
program" in doc/design_doc_webui.md): what the backend writes into an
external input and reads from a business output with no reader. Every line
on a channel of a resident program is an envelope, a JSON object of one
line, and a node reads a line that does not parse as the fragment of a
writer that died in the middle of a message: a second one in a row, or one
not followed by a HELLO, kills its reader thread, and with it the node. So
nothing here ever leaves part of a line in a FIFO, whether written or read.
"""

import errno
import json
import os
import select
import stat
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# How long a write waits for a reader, or for room in the pipe.
WRITE_TIMEOUT_SECS = 8
# How long a read waits for the first byte of a line. Short, since the
# frontend reads again at once, and a read still waiting when the dialog
# closes may take a message that nobody sees.
READ_TIMEOUT_SECS = 2
# How long a read waits for the rest of a line it has started: the writer
# writes a line whole, so this only runs out when the writer died in the
# middle of it.
LINE_TIMEOUT_SECS = 30
# The pause between two attempts to open a FIFO with no reader, or to write
# into a full pipe, and between two looks at a FIFO with no writer.
_RETRY_SECS = 0.1


class FifoError(Exception):
    """Why a write or a read could not be done: shown to the user."""


def _check_fifo(path: Path) -> None:
    try:
        mode = path.stat().st_mode
    except FileNotFoundError:
        raise FifoError(f"FIFO not found: {path} (has its node started yet?)") from None
    if not stat.S_ISFIFO(mode):
        raise FifoError(f"{path} is not a FIFO.")


def data_line(payload: Any) -> bytes:
    """A DATA envelope with no sequence number, since what comes from
    outside the program is not numbered, as one line."""
    return (json.dumps({"type": "DATA", "payload": payload}, ensure_ascii=False) + "\n").encode("utf-8")


def payload_of(text: str, mode: str) -> Any:
    """The payload the user gave: in JSON mode, any JSON value, over several
    lines if need be; in text mode, the text as a JSON string."""
    if mode == "text":
        return text
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise FifoError(f"Not JSON, nothing was written: {exc}") from None


def write_line(path: Path, line: bytes, timeout_secs: float = WRITE_TIMEOUT_SECS) -> None:
    """
    Writes `line` into the FIFO at `path` with a single write(), which POSIX
    makes atomic for at most PIPE_BUF bytes: with O_NONBLOCK it either writes
    the whole line or nothing, so a line is never left in part, not even by
    a write that gives up, and never interleaves with another writer's line.
    A longer line is refused. The FIFO is opened without blocking, which
    fails while nothing holds its read end, and the open and the write are
    tried again until `timeout_secs`.
    """
    _check_fifo(path)
    deadline = time.monotonic() + timeout_secs
    fd = None
    while fd is None:
        try:
            fd = os.open(path, os.O_WRONLY | os.O_NONBLOCK)
        except OSError as exc:
            if exc.errno != errno.ENXIO:
                raise FifoError(f"Cannot open {path}: {exc.strerror}") from None
            if time.monotonic() >= deadline:
                raise FifoError(
                    "Nothing holds the read end of the FIFO: its node is down, "
                    "and no Supervisor holds it."
                ) from None
            time.sleep(_RETRY_SECS)
    try:
        pipe_buf = os.fpathconf(fd, "PC_PIPE_BUF")
        if len(line) > pipe_buf:
            raise FifoError(
                f"The message takes {len(line)} bytes as a line, and at most {pipe_buf} "
                "can be written at once without the risk of leaving part of it."
            )
        while True:
            try:
                os.write(fd, line)
                return
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise FifoError("The FIFO is full: its node is not reading it.") from None
                time.sleep(_RETRY_SECS)
    finally:
        os.close(fd)


def _read_line(fd: int, first_byte_deadline: float) -> bytes | None:
    """
    One line from `fd`, read one byte at a time, so that nothing after it is
    taken from the FIFO. None if no line starts before `first_byte_deadline`.
    A line started is read to its end, within LINE_TIMEOUT_SECS.
    """
    line = bytearray()
    deadline = first_byte_deadline
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            if line:
                raise FifoError(
                    f"A line was cut: its writer stopped in the middle of it ({bytes(line[:60])!r})."
                )
            return None
        readable, _, _ = select.select([fd], [], [], remaining)
        if not readable:
            continue
        try:
            byte = os.read(fd, 1)
        except BlockingIOError:
            continue
        if not byte:
            # No writer holds the FIFO (its node is down): nothing to read
            # for now.
            time.sleep(_RETRY_SECS)
            continue
        if not line:
            deadline = time.monotonic() + LINE_TIMEOUT_SECS
        if byte == b"\n":
            return bytes(line)
        line += byte


@dataclass
class ReadEnvelope:
    """What a read found: an envelope, or a line that is not one."""

    type: str | None = None
    seq: int | None = None
    payload: Any = None
    # A line that does not parse as an envelope, as it was read.
    unparsable: str | None = None


def read_envelope(path: Path, timeout_secs: float = READ_TIMEOUT_SECS) -> ReadEnvelope | None:
    """
    The first envelope in the FIFO at `path` other than a HELLO, skipping
    blank lines and the HELLO with which every incarnation of a writer
    starts, or None if none arrives within `timeout_secs`. It takes what it
    reads from the channel, as any reader does.
    """
    _check_fifo(path)
    deadline = time.monotonic() + timeout_secs
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
    try:
        while True:
            raw = _read_line(fd, deadline)
            if raw is None:
                return None
            text = raw.decode("utf-8", errors="replace")
            if not text.strip():
                continue
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                return ReadEnvelope(unparsable=text)
            if not isinstance(obj, dict) or not isinstance(obj.get("type"), str):
                return ReadEnvelope(unparsable=text)
            if obj["type"] == "HELLO":
                continue
            return ReadEnvelope(type=obj["type"], seq=obj.get("seq"), payload=obj.get("payload"))
    finally:
        os.close(fd)
