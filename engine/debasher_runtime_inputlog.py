"""
DeBasher package
Copyright 2019-2026 Daniel Ortiz-Mart\'inez

This library is free software; you can redistribute it and/or
modify it under the terms of the GNU Lesser General Public License
as published by the Free Software Foundation; either version 3
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Lesser General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with this program; If not, see <http://www.gnu.org/licenses/>.
"""

# *- python -*

# import modules
import os
import json
from collections import namedtuple

from debasher_runtime_envelope import _make_envelope
from debasher_runtime_transport import _write_all


#####################
# _InputLog         #
#####################
#
# The input log of one FBPProcess: a durable, ordered history of everything
# that arrives at it, kept on disk in the node's own directory so that a
# relaunched node can be brought back to where it was. It is meant to be
# written when an envelope arrives, before it is handed to the thread that
# processes it, so a crash never leaves an envelope that was processed (or was
# waiting to be) missing from the log. This class knows nothing about threads,
# ports or barriers: it appends records, hands them back in order and forgets
# old ones.

LogRecord = namedtuple("LogRecord", ["pos", "port", "envelope"])


def _list_segment_files(directory):
    """Returns [(first position, path)] of the segment files of the input log
    in `directory`, oldest first."""
    try:
        names = os.listdir(directory)
    except FileNotFoundError:
        return []
    found = []
    for name in names:
        if not name.endswith(".log"):
            continue
        try:
            found.append((int(name[: -len(".log")]), os.path.join(directory, name)))
        except ValueError:
            continue
    found.sort()
    return found


def _find_last_complete_line(data):
    """The last line of the contents of a segment that ends in a newline,
    without it, or None if there is none: whatever follows it is a torn
    tail."""
    end = data.rfind(b"\n")
    if end < 0:
        return None
    start = data.rfind(b"\n", 0, end) + 1
    return data[start:end]


class LogCapReached(RuntimeError):
    """
    An append would take the input log over its size cap. `positions` are
    those of the records of the same call written before it.
    """

    def __init__(self, message, positions):
        super().__init__(message)
        self.positions = positions


class _InputLog:
    """
    One log per node: a directory of segment files. A segment is named after
    the position of its first record (<first pos>.log) and holds one record
    per line:

        {"pos": 17, "port": "inf", "env": <the envelope line as it arrived>}

    The envelope is embedded exactly as it arrived (it is already one JSON
    value, so nothing has to be encoded again while a lock is held), which
    also makes every line valid JSON. A position is a counter of the node,
    from 1, across all its input ports.

    A record is complete only if its line ends in a newline. A process killed
    in the middle of a write can leave an unterminated fragment at the end of
    a file (a torn tail): it is ignored, and never appended to, because every
    incarnation of the node starts a new segment.

    Not thread-safe: whoever shares one instance among threads has to
    serialize append() and prune(). recover() and replay() are meant to run at
    startup, before anything else uses the log.
    """

    def __init__(self, directory, max_bytes, segment_bytes):
        """
        `max_bytes` caps the total size of all the segments; `segment_bytes`
        is the size at which the segment being written is closed and a new
        one started (a segment can exceed it by the records of one call of
        append_many).
        """
        self._dir = directory
        self._max_bytes = max_bytes
        self._segment_bytes = segment_bytes

        # [first position, size in bytes] of every segment on disk, oldest
        # first. Once anything has been appended, the last one is the
        # segment being written.
        self._segments = []
        self._total_bytes = 0
        self._next_pos = 1

        self._fd = None
        self._active_bytes = 0
        self._port_json = {}
        # Set by a failed write, see append().
        self._failure = None

    @property
    def next_pos(self):
        """The position that the next appended record will get."""
        return self._next_pos

    @property
    def total_bytes(self):
        """Size of all the segments on disk: what the size cap is checked against."""
        return self._total_bytes

    def close(self):
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def _get_segment_path(self, first_pos):
        return os.path.join(self._dir, f"{first_pos}.log")

    def _list_segments(self):
        """Returns [(first position, path)] of the segment files, oldest first."""
        return _list_segment_files(self._dir)

    @staticmethod
    def _parse_record(raw, where):
        """Returns (pos, port, Envelope) for one complete line, without its newline."""
        try:
            obj = json.loads(raw)
        except ValueError as exc:
            raise ValueError(f"input log record at {where} is not valid JSON: {exc}") from None
        pos = obj.get("pos") if isinstance(obj, dict) else None
        if (
            not isinstance(pos, int)
            or isinstance(pos, bool)
            or not isinstance(obj.get("port"), str)
            or "env" not in obj
        ):
            raise ValueError(f"input log record at {where} lacks pos, port or env: {raw[:80]!r}")
        return pos, obj["port"], _make_envelope(obj["env"], where)

    def recover(self, must_reach=0):
        """
        Reads what earlier incarnations left in the directory and prepares
        this one to append after it. Raises ValueError if the log ends below
        `must_reach`, the position that the node's latest checkpoint
        reflects (0 if there is none): the log was lost or cut.

        A segment with no complete record (an empty file, or only a torn
        fragment) is deleted. The next record takes the position that
        fragment would have had, so a new segment would get the same name,
        and the fragment holds nothing that anyone can use.
        """
        if self._segments or self._fd is not None:
            raise RuntimeError("recover() has to run once, before any append")

        segments = self._list_segments()
        last_pos = 0
        while segments:
            first_pos, path = segments[-1]
            with open(path, "rb") as f:
                data = f.read()
            line = _find_last_complete_line(data)
            if line is None:
                os.remove(path)
                segments.pop()
                continue
            last_pos = self._parse_record(line, f"{path}, last record")[0]
            if last_pos < first_pos:
                raise ValueError(f"{path} is named for position {first_pos} but ends at {last_pos}")
            break

        if last_pos < must_reach:
            raise ValueError(
                f"the input log in {self._dir} ends at position {last_pos}, below position "
                f"{must_reach} of the latest checkpoint: it was lost or cut, so what the node "
                "processed after that checkpoint is gone (debasher_reset_resident starts the "
                "program afresh)"
            )

        self._segments = [[first_pos, os.path.getsize(path)] for first_pos, path in segments]
        self._total_bytes = sum(size for _, size in self._segments)
        self._next_pos = last_pos + 1

    def append(self, port, line):
        """
        Appends one record, see append_many, and returns its position.
        """
        return self.append_many([(port, line)])[0]

    def append_many(self, records):
        """
        Appends a record for each (port, line) of `records`, in order: `line`
        is an envelope exactly as it arrived on `port` (one JSON value, with no
        newline in it). The records go to the operating system in one write,
        with no buffering in this process, before this returns their
        positions, which are consecutive. They all go to the same segment, so
        a segment can pass INPUT_LOG_SEGMENT_BYTES by the size of one call.

        Raises LogCapReached if a record would take the log over its size cap,
        after writing the records before it, whose positions it carries; the
        OSError of a write that fails; and RuntimeError on every call after
        it.
        """
        # A failed write may have left a fragment at the end of the segment.
        # Appending behind it would bury it in the middle of the file, where
        # replay rejects it, instead of leaving it as the torn tail.
        if self._failure is not None:
            raise RuntimeError(
                "the input log accepts no more records after a failed write"
            ) from self._failure

        # The record is built by concatenation: the envelope is already JSON,
        # so nothing is decoded or encoded again while the caller holds its
        # lock. The port is encoded once and kept.
        first_pos = self._next_pos
        chunks = []
        for offset, (port, line) in enumerate(records):
            if "\n" in line:
                raise ValueError("an envelope line must not contain a newline")
            port_json = self._port_json.get(port)
            if port_json is None:
                port_json = self._port_json[port] = json.dumps(port)
            chunks.append(f'{{"pos": {first_pos + offset}, "port": {port_json}, "env": {line}}}\n')
        encoded = [chunk.encode("utf-8") for chunk in chunks]

        # The cap is counted record by record before anything is written: the
        # records that fit are written, and their positions travel in
        # LogCapReached, since the caller queues them.
        fitting = 0
        total = self._total_bytes
        for record in encoded:
            if total + len(record) > self._max_bytes:
                break
            total += len(record)
            fitting += 1
        positions = self._write_records(first_pos, encoded[:fitting])
        if fitting < len(encoded):
            raise LogCapReached(
                f"the input log in {self._dir} would exceed {self._max_bytes} bytes: pruning "
                "has not kept up, a real problem to fix, not something to silently discard "
                "history over",
                positions,
            )
        return positions

    def _write_records(self, first_pos, encoded):
        """
        Writes the already encoded records `encoded`, numbered from
        `first_pos`, in one write, and returns their positions.
        """
        if not encoded:
            return []
        data = b"".join(encoded)

        try:
            if self._fd is not None and self._active_bytes >= self._segment_bytes:
                os.close(self._fd)
                self._fd = None
            if self._fd is None:
                os.makedirs(self._dir, exist_ok=True)
                # O_EXCL: a new segment must never land on an existing file.
                self._fd = os.open(
                    self._get_segment_path(first_pos),
                    os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL,
                    0o644,
                )
                self._segments.append([first_pos, 0])
                self._active_bytes = 0
            _write_all(self._fd, data)
        except BaseException as exc:
            self._failure = exc
            raise

        self._segments[-1][1] += len(data)
        self._active_bytes += len(data)
        self._total_bytes += len(data)
        self._next_pos = first_pos + len(encoded)
        return list(range(first_pos, self._next_pos))

    def replay(self, after=0):
        """
        Yields, in order, a LogRecord(pos, port, envelope) for every record
        with a position above `after` (0 to replay everything), reading only
        from disk. Raises ValueError, while yielding, if the log cannot be
        trusted to hold every record above `after`: it starts above
        after + 1, positions are missing or out of order, a segment does not
        start at the position it is named for, or a line that ends in a
        newline does not parse.
        """
        segments = self._list_segments()
        if not segments:
            return

        last_pos = None
        for first_pos, path in segments[self._start_segment(segments, after):]:
            with open(path, "rb") as f:
                for lineno, raw in enumerate(f, 1):
                    if not raw.endswith(b"\n"):
                        # A torn tail: nothing follows it in the file.
                        break
                    where = f"{path}, line {lineno}"
                    pos, port, envelope = self._parse_record(raw[:-1], where)
                    if lineno == 1 and pos != first_pos:
                        raise ValueError(
                            f"{path} is named for position {first_pos} but starts at {pos}"
                        )
                    self._check_position(pos, last_pos, after, where)
                    last_pos = pos
                    if pos > after:
                        yield LogRecord(pos, port, envelope)

    def _start_segment(self, segments, after):
        """
        The index in `segments` of the last segment that can hold position
        after + 1. Raises ValueError if the first segment starts above it.
        """
        start = 0
        for i, (first_pos, _) in enumerate(segments):
            if first_pos <= after + 1:
                start = i
        if segments[start][0] > after + 1:
            raise ValueError(
                f"the input log in {self._dir} starts at position {segments[0][0]}, "
                f"but replaying after position {after} needs it from {after + 1}"
            )
        return start

    def _check_position(self, pos, last_pos, after, where):
        """
        Raises ValueError unless `pos`, read at `where`, follows `last_pos`,
        the position read before it (None for the first one), as a replay
        after `after` needs.
        """
        if last_pos is None:
            if pos > after + 1:
                raise ValueError(
                    f"the input log starts at position {pos}, but replaying after "
                    f"position {after} needs it from {after + 1}"
                )
            return
        if pos <= last_pos:
            raise ValueError(f"position {pos} at {where} does not come after {last_pos}")
        # Positions missing at or below `after` are not needed.
        if pos != last_pos + 1 and pos > after + 1:
            raise ValueError(f"positions {last_pos + 1} to {pos - 1} are missing before {where}")

    def prune(self, upto):
        """
        Deletes every segment, other than the last one, whose records are all
        at or below `upto`: the position that the oldest checkpoint still
        kept reflects, so nothing that a recovery from any kept checkpoint
        needs goes away. A segment holds only positions below the first
        position of the next one, which is how it is known to be finished
        without reading it. The last segment is never deleted: it is the one
        being written, or the newest one an earlier incarnation left.
        """
        while len(self._segments) > 1 and self._segments[1][0] - 1 <= upto:
            first_pos, size = self._segments.pop(0)
            self._total_bytes -= size
            try:
                os.remove(self._get_segment_path(first_pos))
            except FileNotFoundError:
                pass


#####################
# _InputLogReader   #
#####################
#
# The input log as a tool outside the node reads it (debasher_inspect_resident),
# while the node may be appending to it and pruning it: it changes nothing, and
# applies the rules with which a node reads its own log when it recovers.

# A line of a segment that ends in a newline but is not a record: what would
# stop the recovery of the node, and what a reader shows in its place.
BadLine = namedtuple("BadLine", ["path", "lineno", "error"])


def _read_segment(path):
    """The contents of a segment, or None if it is gone: pruned by the node
    after the segments were listed."""
    try:
        with open(path, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return None


class _InputLogReader:
    """
    Reads the input log in `directory` without changing it. A record counts
    only if its line ends in a newline, so a torn tail, left by a crash or
    by a write in progress, is never seen, and a segment that is gone when it
    is opened, pruned after the segments were listed, is skipped.
    """

    def __init__(self, directory):
        self._dir = directory

    def list_segments(self):
        """[(first position, size in bytes)] of the segments on disk, oldest
        first; one that is gone when its size is read is left out."""
        found = []
        for first_pos, path in _list_segment_files(self._dir):
            try:
                found.append((first_pos, os.path.getsize(path)))
            except FileNotFoundError:
                continue
        return found

    def read_first_pos(self):
        """The position of the first complete record, or None if there is
        none. Raises ValueError if that line is not a record."""
        for first_pos, path in _list_segment_files(self._dir):
            data = _read_segment(path)
            if data is None:
                continue
            end = data.find(b"\n")
            if end < 0:
                continue
            return _InputLog._parse_record(data[:end], f"{path}, line 1")[0]
        return None

    def read_last_pos(self):
        """The position of the last complete record, read from the newest
        segment that has one, as recovery reads it, or None if there is none.
        Raises ValueError if that line is not a record."""
        for first_pos, path in reversed(_list_segment_files(self._dir)):
            data = _read_segment(path)
            if data is None:
                continue
            line = _find_last_complete_line(data)
            if line is None:
                continue
            return _InputLog._parse_record(line, f"{path}, last record")[0]
        return None

    def read_records_backwards(self):
        """
        Yields every complete record, from the newest to the oldest, as a
        LogRecord(pos, port, envelope), or, for a line that ends in a newline
        and does not parse, a BadLine(path, lineno, error) in its place.
        """
        for first_pos, path in reversed(_list_segment_files(self._dir)):
            data = _read_segment(path)
            if data is None:
                continue
            lines = data.split(b"\n")
            # The last element follows the last newline: empty, or a torn
            # tail.
            for lineno in range(len(lines) - 1, 0, -1):
                raw = lines[lineno - 1]
                try:
                    pos, port, envelope = _InputLog._parse_record(raw, f"{path}, line {lineno}")
                except ValueError as exc:
                    yield BadLine(path, lineno, str(exc))
                    continue
                yield LogRecord(pos, port, envelope)
