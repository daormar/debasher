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

from debasher_runtime_envelope import _envelope_from_obj
from debasher_runtime_transport import _write_all


#####################
# _InputLog         #
#####################
#
# The input log of one FBPProcess: a durable, ordered history of everything
# that arrives at it, kept on disk in the node's own directory so that a
# relaunched node can be brought back to where it was. It is meant to be
# written when an item arrives, before the item is handed to the thread that
# processes it, so a crash never leaves an item that was processed (or was
# waiting to be) missing from the log. This class knows nothing about threads,
# ports or barriers: it appends records, hands them back in order and forgets
# old ones.

LogRecord = namedtuple("LogRecord", ["pos", "port", "envelope"])


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
        one started (a segment can exceed it by one record).
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

    def _segment_path(self, first_pos):
        return os.path.join(self._dir, f"{first_pos}.log")

    def _list_segments(self):
        """Returns [(first position, path)] of the segment files, oldest first."""
        try:
            names = os.listdir(self._dir)
        except FileNotFoundError:
            return []
        found = []
        for name in names:
            if not name.endswith(".log"):
                continue
            try:
                found.append((int(name[: -len(".log")]), os.path.join(self._dir, name)))
            except ValueError:
                continue
        found.sort()
        return found

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
        return pos, obj["port"], _envelope_from_obj(obj["env"], where)

    def recover(self, capture_pos=0):
        """
        Reads what earlier incarnations left in the directory and prepares
        this one to append after it. `capture_pos` is the position that the
        node's latest checkpoint already reflects (0 if there is none): the
        next position is never at or below it, even if the log holds less, so
        the numbering stays consistent with the checkpoint.

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
            end = data.rfind(b"\n")
            if end < 0:
                os.remove(path)
                segments.pop()
                continue
            start = data.rfind(b"\n", 0, end) + 1
            last_pos = self._parse_record(data[start:end], f"{path}, last record")[0]
            if last_pos < first_pos:
                raise ValueError(f"{path} is named for position {first_pos} but ends at {last_pos}")
            break

        self._segments = [[first_pos, os.path.getsize(path)] for first_pos, path in segments]
        self._total_bytes = sum(size for _, size in self._segments)
        self._next_pos = max(last_pos, capture_pos) + 1

    def append(self, port, line):
        """
        Appends a record for the envelope `line` (the text exactly as it
        arrived: one JSON value, with no newline in it) received on `port`, and
        returns the position it was given. The record is handed to the
        operating system before this returns, with one write and no buffering
        in this process, so it survives the death of the process.

        Raises RuntimeError, before writing anything, if the record would take
        the log over its size cap: it means that nothing is being pruned, a
        real problem to fix rather than a reason to drop history that a
        recovery may need. A failed write is different: it may have left a
        fragment, so from then on every append raises, until the process
        restarts. Otherwise another thread could append behind the fragment
        and bury it in the middle of the file, where replay rejects it,
        instead of leaving it as the torn tail of its segment.
        """
        if self._failure is not None:
            raise RuntimeError(
                "the input log accepts no more records after a failed write"
            ) from self._failure
        if "\n" in line:
            raise ValueError("an envelope line must not contain a newline")

        pos = self._next_pos
        port_json = self._port_json.get(port)
        if port_json is None:
            port_json = self._port_json[port] = json.dumps(port)
        data = f'{{"pos": {pos}, "port": {port_json}, "env": {line}}}\n'.encode("utf-8")

        if self._total_bytes + len(data) > self._max_bytes:
            raise RuntimeError(
                f"the input log in {self._dir} would exceed {self._max_bytes} bytes with no "
                "pruning having kept up: an epoch is not closing (no periodic or triggered "
                "snapshot), a real problem to fix, not something to silently discard history over"
            )

        try:
            if self._fd is not None and self._active_bytes >= self._segment_bytes:
                os.close(self._fd)
                self._fd = None
            if self._fd is None:
                os.makedirs(self._dir, exist_ok=True)
                # O_EXCL: a new segment must never land on an existing file.
                self._fd = os.open(
                    self._segment_path(pos),
                    os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_EXCL,
                    0o644,
                )
                self._segments.append([pos, 0])
                self._active_bytes = 0
            _write_all(self._fd, data)
        except BaseException as exc:
            self._failure = exc
            raise

        self._segments[-1][1] += len(data)
        self._active_bytes += len(data)
        self._total_bytes += len(data)
        self._next_pos = pos + 1
        return pos

    def replay(self, after=0):
        """
        Yields, in order, a LogRecord(pos, port, envelope) for every record
        with a position above `after`: the position that the latest
        checkpoint reflects, or 0 to replay everything. It starts at the last
        segment that can hold position after + 1 and reads only from disk.

        Raises ValueError, while yielding, if the log cannot be trusted to
        hold every record above `after`: it starts above after + 1, positions
        are missing or out of order, a segment does not start at the position
        it is named for, or a line that ends in a newline does not parse. A
        log with no records is not an error, and neither is one that ends
        below `after` (everything in it is already reflected in the checkpoint).
        """
        segments = self._list_segments()
        if not segments:
            return

        start = 0
        for i, (first_pos, _) in enumerate(segments):
            if first_pos <= after + 1:
                start = i
        if segments[start][0] > after + 1:
            raise ValueError(
                f"the input log in {self._dir} starts at position {segments[0][0]}, "
                f"but replaying after position {after} needs it from {after + 1}"
            )

        last_pos = None
        for first_pos, path in segments[start:]:
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
                    if last_pos is None:
                        if pos > after + 1:
                            raise ValueError(
                                f"the input log starts at position {pos}, but replaying after "
                                f"position {after} needs it from {after + 1}"
                            )
                    else:
                        if pos <= last_pos:
                            raise ValueError(
                                f"position {pos} at {where} does not come after {last_pos}"
                            )
                        # Positions missing at or below `after` are not needed.
                        if pos != last_pos + 1 and pos > after + 1:
                            raise ValueError(
                                f"positions {last_pos + 1} to {pos - 1} are missing before {where}"
                            )
                    last_pos = pos
                    if pos > after:
                        yield LogRecord(pos, port, envelope)

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
                os.remove(self._segment_path(first_pos))
            except FileNotFoundError:
                pass
