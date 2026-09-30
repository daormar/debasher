"""
"Talk to FIFOs" in a resident program (see api/resident_fifos.py), on plain
FIFOs: what is written is a whole DATA envelope or nothing, and a read takes
one line and nothing after it.
"""

import json
import os

import pytest

from api import resident_fifos
from api.resident_fifos import FifoError


@pytest.fixture
def fifo(tmp_path):
    path = tmp_path / "port"
    os.mkfifo(path)
    return path


def _reader(fifo):
    """A read end that holds the FIFO, as a node holds its input."""
    return os.open(fifo, os.O_RDONLY | os.O_NONBLOCK)


def _writer(fifo, reader):
    """A write end, as a node holds its output (a reader must exist)."""
    return os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)


def _drain(fd):
    data = b""
    while True:
        try:
            chunk = os.read(fd, 65536)
        except BlockingIOError:
            return data
        if not chunk:
            return data
        data += chunk


# --- writing ------------------------------------------------------------------


def test_a_payload_is_written_as_one_data_envelope_with_no_sequence_number():
    assert json.loads(resident_fifos.data_line({"n": 1})) == {"type": "DATA", "payload": {"n": 1}}
    assert resident_fifos.data_line("a1").endswith(b"\n")
    assert resident_fifos.data_line("a1").count(b"\n") == 1


def test_json_mode_keeps_the_type_of_the_value_and_text_mode_sends_a_string():
    assert resident_fifos.payload_of('[1,\n 2]', "json") == [1, 2]
    assert resident_fifos.payload_of("42", "json") == 42
    assert resident_fifos.payload_of("42", "text") == "42"
    assert resident_fifos.payload_of("two\nlines", "text") == "two\nlines"


def test_text_that_is_not_json_is_refused_in_json_mode():
    with pytest.raises(FifoError, match="Not JSON"):
        resident_fifos.payload_of("hello", "json")


def test_a_line_reaches_the_reader_whole(fifo):
    reader = _reader(fifo)
    try:
        resident_fifos.write_line(fifo, resident_fifos.data_line(5))
        assert _drain(reader) == b'{"type": "DATA", "payload": 5}\n'
    finally:
        os.close(reader)


def test_a_fifo_with_nothing_on_its_read_end_is_reported(fifo):
    with pytest.raises(FifoError, match="Nothing holds the read end"):
        resident_fifos.write_line(fifo, resident_fifos.data_line(1), timeout_secs=0.3)


def test_a_line_longer_than_what_is_written_at_once_is_refused_and_nothing_is_written(fifo):
    reader = _reader(fifo)
    try:
        pipe_buf = os.fpathconf(reader, "PC_PIPE_BUF")
        with pytest.raises(FifoError, match="at most"):
            resident_fifos.write_line(fifo, resident_fifos.data_line("x" * pipe_buf))
        assert _drain(reader) == b""
    finally:
        os.close(reader)


def test_a_full_pipe_is_reported_and_leaves_no_part_of_the_line(fifo):
    reader = _reader(fifo)
    filler = _writer(fifo, reader)
    try:
        # Full to the last byte: blocks of 100 first, then one at a time.
        filled = 0
        for size in (100, 1):
            while True:
                try:
                    filled += os.write(filler, b"x" * size)
                except BlockingIOError:
                    break
        with pytest.raises(FifoError, match="full"):
            resident_fifos.write_line(fifo, resident_fifos.data_line(1), timeout_secs=0.3)
        assert _drain(reader) == b"x" * filled
    finally:
        os.close(filler)
        os.close(reader)


def test_a_path_that_is_not_a_fifo_is_reported(tmp_path):
    with pytest.raises(FifoError, match="not found"):
        resident_fifos.write_line(tmp_path / "nope", b"{}\n")
    (tmp_path / "file").write_text("")
    with pytest.raises(FifoError, match="is not a FIFO"):
        resident_fifos.read_envelope(tmp_path / "file")


# --- reading ------------------------------------------------------------------


def test_a_read_skips_blank_lines_and_hello_and_takes_nothing_after_the_envelope(fifo):
    reader = _reader(fifo)
    writer = _writer(fifo, reader)
    try:
        os.write(
            writer,
            b'{"type": "HELLO", "payload": {}}\n\n'
            b'{"type": "DATA", "seq": 1, "payload": 6}\n'
            b'{"type": "BARRIER", "payload": {"epoch": 7, "halt": false}}\n',
        )

        first = resident_fifos.read_envelope(fifo)
        second = resident_fifos.read_envelope(fifo)

        assert (first.type, first.seq, first.payload) == ("DATA", 1, 6)
        assert (second.type, second.payload) == ("BARRIER", {"epoch": 7, "halt": False})
    finally:
        os.close(writer)
        os.close(reader)


def test_a_line_that_is_not_an_envelope_is_given_as_it_was_read(fifo):
    reader = _reader(fifo)
    writer = _writer(fifo, reader)
    try:
        os.write(writer, b'not json\n[1, 2]\n')

        assert resident_fifos.read_envelope(fifo).unparsable == "not json"
        assert resident_fifos.read_envelope(fifo).unparsable == "[1, 2]"
    finally:
        os.close(writer)
        os.close(reader)


def test_a_read_with_nothing_written_or_no_writer_times_out(fifo):
    reader = _reader(fifo)
    writer = _writer(fifo, reader)
    try:
        assert resident_fifos.read_envelope(fifo, timeout_secs=0.3) is None
        os.close(writer)
        writer = None
        assert resident_fifos.read_envelope(fifo, timeout_secs=0.3) is None
    finally:
        if writer is not None:
            os.close(writer)
        os.close(reader)


def test_a_line_that_its_writer_leaves_unfinished_is_reported(fifo, monkeypatch):
    monkeypatch.setattr(resident_fifos, "LINE_TIMEOUT_SECS", 0.3)
    reader = _reader(fifo)
    writer = _writer(fifo, reader)
    try:
        os.write(writer, b'{"type": "DATA", "pay')

        with pytest.raises(FifoError, match="A line was cut"):
            resident_fifos.read_envelope(fifo, timeout_secs=0.3)
    finally:
        os.close(writer)
        os.close(reader)
