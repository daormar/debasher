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
        proc.capture_state()
    with pytest.raises(NotImplementedError):
        proc.restore_state({})
    with pytest.raises(NotImplementedError):
        proc.initialize_runtime()
