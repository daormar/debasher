import errno
import json
import os
import random
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

import debasher_runtime_inputlog as inputlog
import debasher_runtime_lib as lib

ENGINE_DIR = str(Path(__file__).resolve().parents[2] / "engine")

# Large enough never to matter, for the tests that are about something else.
BIG = 10**9


def _data(payload):
    return lib.encode_data(payload)


def _new_log(tmp_path, max_bytes=BIG, segment_bytes=BIG, processed_upto=0):
    log = lib._InputLog(str(tmp_path / "log"), max_bytes, segment_bytes)
    log.recover(processed_upto)
    return log


def _replay(tmp_path, after=0):
    """Reads the log the way a newly started incarnation would."""
    return list(lib._InputLog(str(tmp_path / "log"), BIG, BIG).replay(after))


def _positions(tmp_path, after=0):
    return [record.pos for record in _replay(tmp_path, after)]


def _segments(tmp_path):
    names = [n for n in os.listdir(tmp_path / "log") if n.endswith(".log")]
    return sorted(names, key=lambda n: int(n[: -len(".log")]))


def _fill(log, count, port="inf", pad=0):
    for _ in range(count):
        log.append(port, _data({"i": log.next_pos, "pad": "x" * pad}))


# --- what a record is ----------------------------------------------------


def test_positions_start_at_one_and_run_across_all_ports(tmp_path):
    log = _new_log(tmp_path)
    assert log.append("a", _data("first")) == 1
    assert log.append("b", _data("second")) == 2
    assert log.append("a", _data("third")) == 3

    records = _replay(tmp_path)
    assert [(r.pos, r.port, r.envelope.payload) for r in records] == [
        (1, "a", "first"),
        (2, "b", "second"),
        (3, "a", "third"),
    ]
    assert all(r.envelope.type == "DATA" for r in records)


def test_every_item_type_is_logged_with_its_own_type(tmp_path):
    log = _new_log(tmp_path)
    log.append("inf", _data("d"))
    log.append("inf", lib.encode_barrier(4, halt=True))
    log.append("trig", lib.encode_interact("shutdown"))
    log.append("inf", lib.encode_close())

    assert [(r.port, r.envelope.type) for r in _replay(tmp_path)] == [
        ("inf", "DATA"),
        ("inf", "BARRIER"),
        ("trig", "INTERACT"),
        ("inf", "CLOSE"),
    ]


def test_a_record_is_one_json_line_holding_the_envelope_exactly_as_it_arrived(tmp_path):
    # Odd spacing on purpose: the log must not re-encode what it is given.
    raw = '{"type":  "DATA",  "payload": [1,   2]}'
    log = _new_log(tmp_path)
    log.append("inf", raw)

    data = (tmp_path / "log" / "1.log").read_bytes()
    assert data.endswith(b"\n") and data.count(b"\n") == 1
    assert json.loads(data) == {
        "pos": 1,
        "port": "inf",
        "env": {"type": "DATA", "payload": [1, 2]},
    }
    assert data == f'{{"pos": 1, "port": "inf", "env": {raw}}}\n'.encode()


def test_a_port_name_with_odd_characters_is_a_valid_json_string(tmp_path):
    log = _new_log(tmp_path)
    log.append('we "ird"\tport', _data(1))
    assert [r.port for r in _replay(tmp_path)] == ['we "ird"\tport']


def test_an_envelope_with_raw_non_ascii_text_round_trips(tmp_path):
    raw = '{"type": "DATA", "payload": "café \U0001F600"}'
    log = _new_log(tmp_path)
    log.append("inf", raw)
    assert _replay(tmp_path)[0].envelope.payload == "café \U0001F600"


def test_a_line_with_a_newline_is_refused_and_takes_no_position(tmp_path):
    log = _new_log(tmp_path)
    with pytest.raises(ValueError):
        log.append("inf", '{"type": "DATA",\n "payload": 1}')
    assert log.next_pos == 1
    assert log.append("inf", _data(1)) == 1


def test_a_record_is_in_the_file_before_append_returns(tmp_path):
    # Nothing is buffered in this process: what a second reader sees on disk
    # right after append() is what would survive the death of the process.
    log = _new_log(tmp_path)
    log.append("inf", _data("kept"))
    data = (tmp_path / "log" / "1.log").read_bytes()
    assert b'"kept"' in data and data.endswith(b"\n")


# --- segments ------------------------------------------------------------


def test_nothing_exists_on_disk_until_the_first_append(tmp_path):
    _new_log(tmp_path)
    assert not (tmp_path / "log").exists()


def test_a_segment_is_named_after_its_first_position_and_closes_at_the_size_limit(tmp_path):
    log = _new_log(tmp_path, segment_bytes=1000)
    _fill(log, 30, pad=100)

    names = _segments(tmp_path)
    assert len(names) > 3
    firsts = [int(n[: -len(".log")]) for n in names]
    assert firsts[0] == 1
    assert _positions(tmp_path) == list(range(1, 31))

    for name, first in zip(names, firsts):
        lines = (tmp_path / "log" / name).read_bytes().splitlines(keepends=True)
        assert json.loads(lines[0])["pos"] == first
        size = sum(len(line) for line in lines)
        if name != names[-1]:
            # Closed as soon as it reached the limit: over it by one record at most.
            assert size >= 1000
            assert size - len(lines[-1]) < 1000


def test_every_incarnation_starts_a_new_segment(tmp_path):
    first = _new_log(tmp_path)
    _fill(first, 2)
    first.close()

    second = _new_log(tmp_path)
    assert second.next_pos == 3
    _fill(second, 2)

    assert _segments(tmp_path) == ["1.log", "3.log"]
    assert _positions(tmp_path) == [1, 2, 3, 4]


# --- recovery and torn tails ---------------------------------------------


def test_recover_continues_after_the_last_complete_record(tmp_path):
    log = _new_log(tmp_path, segment_bytes=300)
    _fill(log, 7, pad=60)
    log.close()

    assert _new_log(tmp_path).next_pos == 8


def test_recover_never_numbers_at_or_below_the_position_a_checkpoint_reflects(tmp_path):
    empty = _new_log(tmp_path, processed_upto=50)
    assert empty.next_pos == 51
    _fill(empty, 1)
    assert _segments(tmp_path) == ["51.log"]
    empty.close()

    # A log that holds less than the checkpoint reflects: numbering goes on after the checkpoint.
    behind = _new_log(tmp_path, processed_upto=80)
    assert behind.next_pos == 81
    # A log that holds more: numbering goes on after the log.
    assert _new_log(tmp_path, processed_upto=10).next_pos == 52


def test_recover_can_only_run_once_and_before_any_append(tmp_path):
    log = _new_log(tmp_path)
    _fill(log, 1)
    with pytest.raises(RuntimeError, match="once"):
        log.recover()

    fresh = lib._InputLog(str(tmp_path / "log"), BIG, BIG)
    fresh.recover()
    fresh.close()
    # Nothing was appended, so nothing is on disk to protect, but a second call is still a mistake.
    _fill(fresh, 1)
    with pytest.raises(RuntimeError, match="once"):
        fresh.recover()


def test_a_torn_tail_is_ignored_and_never_appended_to(tmp_path):
    log = _new_log(tmp_path)
    _fill(log, 3)
    log.close()
    fragment = b'{"pos": 4, "port": "inf", "env": {"type": "DA'
    with open(tmp_path / "log" / "1.log", "ab") as f:
        f.write(fragment)
    torn_file = (tmp_path / "log" / "1.log").read_bytes()

    assert _positions(tmp_path) == [1, 2, 3]

    second = _new_log(tmp_path)
    assert second.next_pos == 4
    _fill(second, 2)

    assert _segments(tmp_path) == ["1.log", "4.log"]
    assert (tmp_path / "log" / "1.log").read_bytes() == torn_file
    assert _positions(tmp_path) == [1, 2, 3, 4, 5]


def test_a_segment_with_only_a_torn_fragment_is_deleted_and_its_name_can_be_reused(tmp_path):
    log = _new_log(tmp_path)
    _fill(log, 2)
    log.close()
    (tmp_path / "log" / "3.log").write_bytes(b'{"pos": 3, "port": "in')

    second = _new_log(tmp_path)
    assert not (tmp_path / "log" / "3.log").exists()
    assert second.next_pos == 3
    _fill(second, 2)

    assert _segments(tmp_path) == ["1.log", "3.log"]
    assert _positions(tmp_path) == [1, 2, 3, 4]


def test_an_empty_segment_file_is_deleted_at_recover(tmp_path):
    log = _new_log(tmp_path)
    _fill(log, 2)
    log.close()
    (tmp_path / "log" / "3.log").write_bytes(b"")

    second = _new_log(tmp_path)
    assert _segments(tmp_path) == ["1.log"]
    assert second.next_pos == 3


def test_torn_tails_in_several_earlier_segments_are_all_tolerated(tmp_path):
    for expected_first in (1, 3, 5):
        log = _new_log(tmp_path)
        assert log.next_pos == expected_first
        _fill(log, 2)
        log.close()
        with open(tmp_path / "log" / f"{expected_first}.log", "ab") as f:
            f.write(b'{"pos": ')

    assert _positions(tmp_path) == [1, 2, 3, 4, 5, 6]
    assert _new_log(tmp_path).next_pos == 7


# --- replay --------------------------------------------------------------


def test_replay_yields_only_the_records_above_the_given_position(tmp_path):
    log = _new_log(tmp_path, segment_bytes=300)
    _fill(log, 12, pad=60)
    for after in range(0, 14):
        assert _positions(tmp_path, after) == list(range(after + 1, 13))


def test_replay_starts_at_the_last_segment_that_can_hold_the_next_position(tmp_path):
    log = _new_log(tmp_path, segment_bytes=300)
    _fill(log, 12, pad=60)
    names = _segments(tmp_path)
    assert names[0] == "1.log" and len(names) >= 4

    # With the earliest segments gone, replaying after a later position must not need them.
    for name in names[:2]:
        os.remove(tmp_path / "log" / name)
    second_kept = int(names[2][: -len(".log")])
    assert _positions(tmp_path, second_kept - 1) == list(range(second_kept, 13))


def test_replay_fails_if_the_log_starts_above_what_is_needed(tmp_path):
    log = _new_log(tmp_path, segment_bytes=300)
    _fill(log, 12, pad=60)
    os.remove(tmp_path / "log" / "1.log")
    with pytest.raises(ValueError, match="starts at position"):
        _replay(tmp_path, 0)


def test_replay_fails_if_a_segment_in_the_middle_is_missing(tmp_path):
    log = _new_log(tmp_path, segment_bytes=300)
    _fill(log, 12, pad=60)
    names = _segments(tmp_path)
    os.remove(tmp_path / "log" / names[1])
    with pytest.raises(ValueError, match="missing"):
        _replay(tmp_path, 0)


def test_positions_missing_at_or_below_the_given_position_are_not_needed(tmp_path):
    log = _new_log(tmp_path, segment_bytes=300)
    _fill(log, 12, pad=60)
    names = _segments(tmp_path)
    missing_last = int(names[2][: -len(".log")]) - 1
    os.remove(tmp_path / "log" / names[1])
    assert _positions(tmp_path, missing_last) == list(range(missing_last + 1, 13))


def test_replay_fails_on_a_terminated_line_that_is_not_valid_json(tmp_path):
    log = _new_log(tmp_path)
    _fill(log, 3)
    path = tmp_path / "log" / "1.log"
    lines = path.read_bytes().splitlines(keepends=True)
    lines[1] = b'{"pos": 2, "port": "inf", "env": {"type": "DA\n'
    path.write_bytes(b"".join(lines))
    with pytest.raises(ValueError, match="not valid JSON"):
        _replay(tmp_path)


def test_replay_fails_on_a_record_that_lacks_a_required_field(tmp_path):
    log = _new_log(tmp_path)
    _fill(log, 2)
    with open(tmp_path / "log" / "1.log", "ab") as f:
        f.write(b'{"pos": 3, "port": "inf"}\n')
    with pytest.raises(ValueError, match="lacks pos, port or env"):
        _replay(tmp_path)


def test_replay_fails_on_a_record_whose_envelope_is_not_valid(tmp_path):
    log = _new_log(tmp_path)
    _fill(log, 1)
    with open(tmp_path / "log" / "1.log", "ab") as f:
        f.write(b'{"pos": 2, "port": "inf", "env": {"type": "BOGUS", "payload": 1}}\n')
    with pytest.raises(ValueError, match="unknown envelope type"):
        _replay(tmp_path)


def test_replay_fails_on_a_repeated_position(tmp_path):
    log = _new_log(tmp_path)
    _fill(log, 3)
    path = tmp_path / "log" / "1.log"
    lines = path.read_bytes().splitlines(keepends=True)
    path.write_bytes(b"".join([lines[0], lines[1], lines[1], lines[2]]))
    with pytest.raises(ValueError, match="does not come after"):
        _replay(tmp_path)


def test_replay_fails_if_a_segment_is_not_named_for_its_first_position(tmp_path):
    log = _new_log(tmp_path, segment_bytes=300)
    _fill(log, 12, pad=60)
    names = _segments(tmp_path)
    os.rename(tmp_path / "log" / names[1], tmp_path / "log" / "99.log")
    with pytest.raises(ValueError, match="is named for position 99"):
        _replay(tmp_path, 98)


def test_a_log_with_no_records_is_not_an_error(tmp_path):
    assert _replay(tmp_path, 0) == []
    assert _replay(tmp_path, 40) == []
    os.makedirs(tmp_path / "log")
    assert _replay(tmp_path, 0) == []


def test_a_log_that_ends_below_the_given_position_is_not_an_error(tmp_path):
    log = _new_log(tmp_path)
    _fill(log, 3)
    log.close()

    assert _positions(tmp_path, 10) == []

    later = _new_log(tmp_path, processed_upto=10)
    assert later.next_pos == 11
    _fill(later, 2)
    assert _positions(tmp_path, 10) == [11, 12]


def test_replay_only_reads_and_never_writes(tmp_path):
    log = _new_log(tmp_path)
    _fill(log, 3)
    log.close()
    before = {n: (tmp_path / "log" / n).read_bytes() for n in os.listdir(tmp_path / "log")}
    _replay(tmp_path, 1)
    after = {n: (tmp_path / "log" / n).read_bytes() for n in os.listdir(tmp_path / "log")}
    assert before == after


# --- pruning -------------------------------------------------------------


def _four_segments(tmp_path):
    # Three records of about 150 bytes fill a segment of 400, so the segments are 1, 4, 7, 10.
    log = _new_log(tmp_path, segment_bytes=400)
    _fill(log, 12, pad=60)
    assert _segments(tmp_path) == ["1.log", "4.log", "7.log", "10.log"]
    return log


def test_prune_deletes_only_whole_segments_at_or_below_the_position(tmp_path):
    log = _four_segments(tmp_path)

    log.prune(5)
    assert _segments(tmp_path) == ["4.log", "7.log", "10.log"]

    log.prune(6)
    assert _segments(tmp_path) == ["7.log", "10.log"]

    log.prune(8)
    assert _segments(tmp_path) == ["7.log", "10.log"]


def test_prune_never_deletes_the_last_segment(tmp_path):
    log = _four_segments(tmp_path)
    log.prune(10**9)
    assert _segments(tmp_path) == ["10.log"]
    # Still the segment being written: appending goes on in it.
    _fill(log, 1)
    assert _positions(tmp_path, 9) == [10, 11, 12, 13]


def test_prune_never_deletes_the_newest_segment_of_an_earlier_incarnation(tmp_path):
    log = _new_log(tmp_path, segment_bytes=400)
    _fill(log, 6, pad=60)
    log.close()

    second = _new_log(tmp_path)
    second.prune(10**9)
    assert _segments(tmp_path) == ["4.log"]


def test_prune_never_loses_a_record_above_the_position(tmp_path):
    rng = random.Random(7)
    log = _new_log(tmp_path, segment_bytes=500)
    for _ in range(60):
        log.append("inf", _data({"i": log.next_pos, "pad": "x" * rng.randrange(0, 300)}))
    for upto in (0, 1, 5, 17, 30, 44, 59, 60, 61, 500):
        before = _positions(tmp_path, upto)
        log.prune(upto)
        assert _positions(tmp_path, upto) == before


def test_total_bytes_follows_the_files_on_disk(tmp_path):
    def on_disk():
        return sum((tmp_path / "log" / n).stat().st_size for n in os.listdir(tmp_path / "log"))

    log = _four_segments(tmp_path)
    assert log.total_bytes == on_disk()
    log.prune(6)
    assert log.total_bytes == on_disk()
    log.close()

    again = _new_log(tmp_path)
    assert again.total_bytes == on_disk()
    _fill(again, 4, pad=60)
    assert again.total_bytes == on_disk()


# --- size cap ------------------------------------------------------------


def _snapshot(tmp_path):
    return {n: (tmp_path / "log" / n).read_bytes() for n in os.listdir(tmp_path / "log")}


def test_the_cap_refuses_a_record_before_writing_anything(tmp_path):
    log = _new_log(tmp_path, max_bytes=600, segment_bytes=200)
    while True:
        total, next_pos, files = log.total_bytes, log.next_pos, _snapshot(tmp_path) if (tmp_path / "log").exists() else {}
        try:
            log.append("inf", _data({"pad": "x" * 40}))
        except RuntimeError as exc:
            assert "exceed" in str(exc)
            break

    # The refused record left no trace and took no position.
    assert log.total_bytes == total <= 600
    assert log.next_pos == next_pos
    assert _snapshot(tmp_path) == files
    assert _positions(tmp_path) == list(range(1, next_pos))

    # It was not a failed write, so the log is not poisoned: once pruning makes room, it goes on.
    log.prune(next_pos - 1)
    assert log.append("inf", _data("again")) == next_pos


def test_pruning_makes_room_under_the_cap_again(tmp_path):
    log = _new_log(tmp_path, max_bytes=800, segment_bytes=200)
    with pytest.raises(RuntimeError, match="exceed"):
        _fill(log, 100, pad=40)
    full_at = log.next_pos

    log.prune(full_at - 3)
    _fill(log, 2, pad=40)
    assert log.next_pos == full_at + 2


# --- a failed write ------------------------------------------------------


def test_a_failed_write_refuses_every_later_append_and_leaves_a_torn_tail(tmp_path, monkeypatch):
    log = _new_log(tmp_path)
    _fill(log, 3)

    real_write_all = inputlog._write_all

    def failing_write_all(fd, data):
        os.write(fd, data[: len(data) // 2])
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(inputlog, "_write_all", failing_write_all)
    with pytest.raises(OSError):
        log.append("inf", _data("lost"))

    # Whatever the cause was, it is gone now: the log still refuses, so nothing can
    # land behind the fragment.
    monkeypatch.setattr(inputlog, "_write_all", real_write_all)
    with pytest.raises(RuntimeError, match="no more records"):
        log.append("inf", _data("refused"))
    assert not (tmp_path / "log" / "1.log").read_bytes().endswith(b"\n")

    # The next incarnation sees the fragment as a torn tail and goes on after the last good record.
    assert _positions(tmp_path) == [1, 2, 3]
    second = _new_log(tmp_path)
    assert second.next_pos == 4
    _fill(second, 2)
    assert _positions(tmp_path) == [1, 2, 3, 4, 5]


def test_a_failure_to_create_a_segment_also_refuses_later_appends(tmp_path, monkeypatch):
    log = _new_log(tmp_path)

    real_open = os.open

    def failing_open(path, *args, **kwargs):
        if str(path).endswith(".log"):
            raise OSError(errno.EACCES, "Permission denied")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(os, "open", failing_open)
    with pytest.raises(OSError):
        log.append("inf", _data(1))
    monkeypatch.setattr(os, "open", real_open)
    with pytest.raises(RuntimeError, match="no more records"):
        log.append("inf", _data(2))


# --- a real kill -9 ------------------------------------------------------

# One incarnation of a node: it recovers the log, says that it is about to
# write, then appends records of different sizes as fast as it can (up to a
# bounded amount, so the test does not fill the disk) and reports each position
# to a progress file only after append() has returned, which is the point at
# which a reader thread would hand the item to the thread that processes it.
_APPENDER = textwrap.dedent(
    """
    import os, random, sys, time
    sys.path.insert(0, sys.argv[1])
    import debasher_runtime_lib as lib

    directory, progress, seed, ready = sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5]
    rng = random.Random(seed)
    log = lib._InputLog(directory, 10**9, 20000)
    log.recover()
    pfd = os.open(progress, os.O_WRONLY | os.O_CREAT, 0o644)
    open(ready, "w").close()
    budget = log.total_bytes + 10_000_000
    while log.total_bytes < budget:
        size = rng.choice([100, 4000, 5000, 5000, 6000])
        pos = log.append("inf", lib.encode_data({"i": log.next_pos, "pad": "x" * size}))
        os.pwrite(pfd, b"%020d" % pos, 0)
    time.sleep(60)
    """
)


def test_kill_9_never_loses_a_record_that_append_had_returned_for(tmp_path):
    directory = str(tmp_path / "log")
    progress = str(tmp_path / "progress")
    rng = random.Random(20260920)

    for incarnation in range(12):
        ready = tmp_path / f"ready-{incarnation}"
        child = subprocess.Popen(
            [sys.executable, "-c", _APPENDER, ENGINE_DIR, directory, progress, str(incarnation), str(ready)]
        )
        deadline = time.monotonic() + 10
        while not ready.exists():
            assert child.poll() is None and time.monotonic() < deadline, "the appender did not start"
            time.sleep(0.001)
        # The kill always lands while the appender is writing, since its work takes longer than this.
        time.sleep(rng.uniform(0.0, 0.04))
        os.kill(child.pid, signal.SIGKILL)
        child.wait()
        assert child.returncode == -signal.SIGKILL

        acknowledged = int(Path(progress).read_bytes() or b"0")

        records = list(lib._InputLog(directory, BIG, BIG).replay(0))
        # Every position from 1 on, in order, across all the incarnations so far.
        assert [r.pos for r in records] == list(range(1, len(records) + 1))
        assert all(r.envelope.payload["i"] == r.pos for r in records)
        # Nothing that had been acknowledged is missing.
        assert len(records) >= acknowledged

    torn_tails = sum(
        1 for name in os.listdir(directory) if not Path(directory, name).read_bytes().endswith(b"\n")
    )
    print(f"kill -9 rounds that left a torn tail: {torn_tails} of 12")

    # The next incarnation carries on numbering after the last complete record.
    final = lib._InputLog(directory, BIG, BIG)
    final.recover()
    assert final.next_pos == len(records) + 1
