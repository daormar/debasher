import json

import pytest

import debasher_runtime_lib as lib


def test_encode_data_wraps_payload_as_is():
    line = lib.encode_data({"a": 1})
    assert json.loads(line) == {"type": "DATA", "payload": {"a": 1}}


def test_encode_data_accepts_any_json_value():
    for payload in [42, "hello", [1, 2, 3], None, True]:
        line = lib.encode_data(payload)
        assert json.loads(line) == {"type": "DATA", "payload": payload}


def test_encode_data_with_a_seq_adds_it_as_a_sibling_of_type_and_payload():
    line = lib.encode_data({"a": 1}, seq=5)
    assert json.loads(line) == {"type": "DATA", "seq": 5, "payload": {"a": 1}}


def test_encode_data_with_no_seq_leaves_the_key_out():
    # Not the same as seq=0: a message that is not numbered at all (from a
    # plain _PortWorker, or from outside the program) carries no "seq" key,
    # so the receiver can tell it apart from one that is (decision 6, G5).
    line = lib.encode_data(1)
    assert "seq" not in json.loads(line)


def test_encode_barrier_default_halt_is_false():
    line = lib.encode_barrier(epoch=3)
    assert json.loads(line) == {
        "type": "BARRIER",
        "payload": {"epoch": 3, "halt": False},
    }


def test_encode_barrier_can_set_halt():
    line = lib.encode_barrier(epoch=7, halt=True)
    assert json.loads(line) == {
        "type": "BARRIER",
        "payload": {"epoch": 7, "halt": True},
    }


def test_encode_interact_default_args_is_empty_dict():
    line = lib.encode_interact("start_snapshot")
    assert json.loads(line) == {
        "type": "INTERACT",
        "payload": {"command": "start_snapshot", "args": {}},
    }


def test_encode_interact_with_args():
    line = lib.encode_interact("checkpoint_saved", {"epoch": 2, "path": "/x"})
    assert json.loads(line) == {
        "type": "INTERACT",
        "payload": {"command": "checkpoint_saved", "args": {"epoch": 2, "path": "/x"}},
    }


def test_encode_close_has_an_empty_payload():
    line = lib.encode_close()
    assert json.loads(line) == {"type": "CLOSE", "payload": {}}


def test_encode_hello_has_an_empty_payload():
    line = lib.encode_hello()
    assert json.loads(line) == {"type": "HELLO", "payload": {}}


def test_encode_never_adds_a_trailing_newline():
    assert not lib.encode_data(1).endswith("\n")
    assert not lib.encode_barrier(1).endswith("\n")
    assert not lib.encode_interact("x").endswith("\n")
    assert not lib.encode_close().endswith("\n")
    assert not lib.encode_hello().endswith("\n")


def test_decode_envelope_round_trips_data():
    envelope = lib.decode_envelope(lib.encode_data({"x": 1}))
    assert envelope == lib.Envelope(type="DATA", payload={"x": 1})


def test_decode_envelope_round_trips_a_numbered_data():
    envelope = lib.decode_envelope(lib.encode_data({"x": 1}, seq=5))
    assert envelope == lib.Envelope(type="DATA", payload={"x": 1}, seq=5)
    assert envelope.seq == 5


def test_decode_envelope_defaults_seq_to_none_when_the_line_carries_none():
    envelope = lib.decode_envelope(lib.encode_data(1))
    assert envelope.seq is None


def test_decode_envelope_round_trips_barrier():
    envelope = lib.decode_envelope(lib.encode_barrier(epoch=5, halt=True))
    assert envelope == lib.Envelope(type="BARRIER", payload={"epoch": 5, "halt": True})


def test_decode_envelope_round_trips_interact():
    envelope = lib.decode_envelope(lib.encode_interact("shutdown"))
    assert envelope == lib.Envelope(type="INTERACT", payload={"command": "shutdown", "args": {}})


def test_decode_envelope_round_trips_close_and_hello():
    assert lib.decode_envelope(lib.encode_close()) == lib.Envelope(type="CLOSE", payload={})
    assert lib.decode_envelope(lib.encode_hello()) == lib.Envelope(type="HELLO", payload={})


def test_decode_envelope_survives_an_embedded_newline_in_a_data_payload():
    # The whole point of going through json.dumps for the wire format:
    # a newline inside the payload must not be mistaken for the line
    # delimiter.
    line = lib.encode_data("first line\nsecond line")
    assert "\n" not in line
    envelope = lib.decode_envelope(line)
    assert envelope.payload == "first line\nsecond line"


def test_decode_envelope_rejects_missing_type_or_payload():
    with pytest.raises(ValueError):
        lib.decode_envelope(json.dumps({"payload": 1}))
    with pytest.raises(ValueError):
        lib.decode_envelope(json.dumps({"type": "DATA"}))


def test_decode_envelope_rejects_unknown_type():
    with pytest.raises(ValueError):
        lib.decode_envelope(json.dumps({"type": "BOGUS", "payload": 1}))


def test_decode_envelope_lets_malformed_json_propagate():
    with pytest.raises(json.JSONDecodeError):
        lib.decode_envelope("not json")


def test_barrier_is_never_nested_inside_data():
    # DATA's payload is opaque to the envelope layer -- encoding a
    # BARRIER-shaped dict as DATA's own payload must decode back as
    # DATA, not be mistaken for a real BARRIER: a reader must be able
    # to dispatch on the top-level "type" alone.
    line = lib.encode_data({"type": "BARRIER", "payload": {"epoch": 1, "halt": False}})
    envelope = lib.decode_envelope(line)
    assert envelope.type == "DATA"
    assert envelope.payload == {"type": "BARRIER", "payload": {"epoch": 1, "halt": False}}


def test_decode_envelope_rejects_a_json_value_that_is_not_an_object():
    for line in ("[1, 2]", '"DATA"', "7", "null"):
        with pytest.raises(ValueError):
            lib.decode_envelope(line)


def test_envelope_from_obj_accepts_an_already_decoded_envelope():
    envelope = lib._envelope_from_obj({"type": "DATA", "payload": [1, 2]}, "somewhere")
    assert envelope == lib.Envelope(type="DATA", payload=[1, 2])


def test_envelope_from_obj_rejects_what_decode_envelope_rejects_and_names_the_source():
    with pytest.raises(ValueError, match="somewhere"):
        lib._envelope_from_obj({"payload": 1}, "somewhere")
    with pytest.raises(ValueError, match="somewhere"):
        lib._envelope_from_obj(["DATA", 1], "somewhere")
    with pytest.raises(ValueError):
        lib._envelope_from_obj({"type": "BOGUS", "payload": 1}, "somewhere")
