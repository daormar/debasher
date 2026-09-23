import logging
import sys

import pytest

import debasher_runtime_lib as lib


# --- _parse_opts ------------------------------------------------------


def test_parse_opts_skips_up_to_and_including_the_double_dash_marker():
    argv = ["-c", "--", "-inf", "/tmp/a", "-outf", "/tmp/b"]
    assert lib._parse_opts(argv) == {"inf": "/tmp/a", "outf": "/tmp/b"}


def test_parse_opts_skips_only_element_0_when_no_marker_is_present():
    argv = ["fakescript", "-inf", "/tmp/a"]
    assert lib._parse_opts(argv) == {"inf": "/tmp/a"}


def test_parse_opts_strips_one_or_two_leading_dashes_to_the_same_key():
    argv = ["-c", "--", "-inf", "/tmp/a", "--log-level", "DEBUG"]
    assert lib._parse_opts(argv) == {"inf": "/tmp/a", "log-level": "DEBUG"}


def test_parse_opts_rejects_a_value_where_a_name_was_expected():
    with pytest.raises(ValueError):
        lib._parse_opts(["-c", "--", "not-a-name", "x"])


def test_parse_opts_rejects_a_trailing_name_with_no_value():
    with pytest.raises(ValueError):
        lib._parse_opts(["-c", "--", "-inf"])


# --- FBPProcess: port declaration -------------------------------------


class _Worker(lib.FBPProcess):
    INPUT_PORTS = ["inf"]
    OUTPUT_PORTS = ["outf"]


def test_fbpprocess_accepts_opts_covering_every_declared_port():
    proc = _Worker(opts={"inf": "/tmp/a", "outf": "/tmp/b"})
    assert proc.opts == {"inf": "/tmp/a", "outf": "/tmp/b"}


def test_fbpprocess_keeps_undeclared_opts_available_with_no_special_handling():
    proc = _Worker(opts={"inf": "/tmp/a", "outf": "/tmp/b", "threshold": "5"})
    assert proc.opts["threshold"] == "5"


def test_fbpprocess_rejects_a_missing_declared_port():
    with pytest.raises(ValueError, match="outf"):
        _Worker(opts={"inf": "/tmp/a"})


def test_fbpprocess_parses_real_argv_when_opts_is_not_given():
    argv = ["-c", "--", "-inf", "/tmp/a", "-outf", "/tmp/b"]
    proc = _Worker(argv=argv)
    assert proc.opts == {"inf": "/tmp/a", "outf": "/tmp/b"}


# --- FBPProcess: logging ------------------------------------------------


class _NoPortsProcess(lib.FBPProcess):
    pass


def test_fbpprocess_default_log_level_is_info():
    proc = _NoPortsProcess(opts={})
    assert proc.log.level == logging.INFO


def test_fbpprocess_log_level_configurable_via_opts_case_insensitively():
    proc = _NoPortsProcess(opts={"log-level": "debug"})
    assert proc.log.level == logging.DEBUG


def _own_stderr_handlers(logger):
    # pytest's own logging capture plugin attaches its own handler(s) to
    # every logger it sees mid-test, so counting proc.log.handlers as a
    # whole is too fragile here; identify the one FBPProcess itself adds
    # by its (real) stream instead, ignoring whatever else pytest added.
    return [h for h in logger.handlers if getattr(h, "stream", None) is sys.stderr]


def test_fbpprocess_log_writes_to_stderr_with_a_handler():
    proc = _NoPortsProcess(opts={})
    own = _own_stderr_handlers(proc.log)
    assert len(own) == 1
    assert isinstance(own[0], logging.StreamHandler)


def test_fbpprocess_does_not_duplicate_handlers_across_instances_of_the_same_class():
    first = _NoPortsProcess(opts={})
    before = len(_own_stderr_handlers(first.log))
    second = _NoPortsProcess(opts={})
    assert first.log is second.log
    assert len(_own_stderr_handlers(second.log)) == before


# --- FBPProcess: extension points must be overridden --------------------


def test_fbpprocess_extension_points_are_not_implemented_by_default():
    proc = _NoPortsProcess(opts={})
    with pytest.raises(NotImplementedError):
        proc.process_data("some_port", {"x": 1})
    with pytest.raises(NotImplementedError):
        proc.capture_node_state()
    with pytest.raises(NotImplementedError):
        proc.restore_node_state({})
    with pytest.raises(NotImplementedError):
        proc.initialize_runtime()


def test_a_module_that_still_defines_the_old_hooks_fails_at_its_first_round():
    # capture_state and restore_state became capture_node_state and restore_node_state:
    # a module written for the old names has to fail loudly, not run without any state saved.
    class _OldHooks(lib.FBPProcess):
        def capture_state(self):
            return {}

        def restore_state(self, state):
            pass

    proc = _OldHooks(opts={})
    with pytest.raises(NotImplementedError):
        proc._on_interact({"command": "start_snapshot", "args": {}})


# --- FBPProcess: limits from the computational specifications ---------


class _Limited(_Worker):
    OUT_BACKLOG_FAIL_BYTES = 5 * 1024 * 1024


def _limited_opts():
    return {port: "/dev/null" for port in _Limited.INPUT_PORTS + _Limited.OUTPUT_PORTS}


@pytest.mark.parametrize(
    "comp_specs",
    [
        "cpus=1; mem=32; time=00:01:00; input_log_max_mb=2; out_backlog_max_mb=0.5; "
        "out_backlog_fail_mb=16; gil_switch_interval_ms=2",
        "cpus=1 mem=32 time=00:01:00 input_log_max_mb=2 out_backlog_max_mb=0.5 "
        "out_backlog_fail_mb=16 gil_switch_interval_ms=2",
    ],
)
def test_the_computational_specs_set_the_limits_of_the_node(monkeypatch, comp_specs):
    monkeypatch.setenv("DEBASHER_PROCESS_COMP_SPECS", comp_specs)
    node = _Limited(opts=_limited_opts())
    assert node.INPUT_LOG_MAX_BYTES == 2 * 1024 * 1024
    assert node.OUT_BACKLOG_MAX_BYTES == 512 * 1024
    assert node.OUT_BACKLOG_FAIL_BYTES == 16 * 1024 * 1024
    assert node.GIL_SWITCH_INTERVAL_SECS == pytest.approx(0.002)


def test_without_computational_specs_the_class_decides(monkeypatch):
    monkeypatch.setenv("DEBASHER_PROCESS_COMP_SPECS", "cpus=1; mem=32; time=00:01:00")
    node = _Limited(opts=_limited_opts())
    assert node.OUT_BACKLOG_FAIL_BYTES == 5 * 1024 * 1024
    assert node.INPUT_LOG_MAX_BYTES == lib.FBPProcess.INPUT_LOG_MAX_BYTES
    # The class itself is left as it was.
    monkeypatch.setenv("DEBASHER_PROCESS_COMP_SPECS", "out_backlog_fail_mb=1")
    _Limited(opts=_limited_opts())
    assert _Limited.OUT_BACKLOG_FAIL_BYTES == 5 * 1024 * 1024


@pytest.mark.parametrize("value", ["0", "-1", "abc", "", "inf", "nan"])
def test_a_limit_that_is_not_a_positive_number_is_refused(monkeypatch, value):
    monkeypatch.setenv("DEBASHER_PROCESS_COMP_SPECS", f"cpus=1; out_backlog_fail_mb={value}")
    with pytest.raises(ValueError, match="out_backlog_fail_mb"):
        _Limited(opts=_limited_opts())
