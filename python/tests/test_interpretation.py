import pytest

from dsh_si.interpretation import normalize
from dsh_si.protocol import WorkerError


def bad(raw, n_ports):
    with pytest.raises(WorkerError) as info:
        normalize(raw, n_ports)
    assert info.value.code == "interpretation_invalid"
    return info.value.message


def test_rejects_non_object_and_unknown_device():
    assert "must be an object" in bad("x", 2)
    assert "device: expected one of" in bad({"device": "diode"}, 2)


def test_lumped_requires_terminal_mode():
    msg = bad({"device": "inductor"}, 1)
    assert "terminal_mode" in msg
    assert normalize({"device": "inductor", "terminal_mode": "one_port"}, 1) == {
        "device": "inductor",
        "input_is_mixed_mode": False,
        "terminal_mode": "one_port",
    }


def test_two_terminal_needs_two_ports():
    assert "needs a 2-port file" in bad(
        {"device": "capacitor", "terminal_mode": "two_terminal_differential"}, 4
    )


def test_line_ports_validated():
    msg = bad({"device": "transmission_line", "ports": {"in": [1, 9], "out": [1]}}, 4)
    assert "port 9" in msg
    assert "listed as both in and out" in msg
    out = normalize(
        {
            "device": "transmission_line",
            "ports": {"in": [1, 2], "out": [3, 4]},
            "pairs": [{"name": "A", "p": 1, "n": 2}, {"p": 3, "n": 4}],
        },
        4,
    )
    assert out["ports"] == {"in": [1, 2], "out": [3, 4]}
    assert out["pairs"][1]["name"] == "pair2"


def test_pairs_cannot_share_ports():
    msg = bad(
        {
            "device": "interposer",
            "topology": "differential_pairs",
            "pairs": [{"p": 1, "n": 2}, {"p": 2, "n": 3}],
        },
        4,
    )
    assert "more than one pair" in msg


def test_interposer_single_ended_needs_paths():
    assert "paths: required" in bad({"device": "interposer", "topology": "single_ended_paths"}, 4)
    out = normalize(
        {"device": "interposer", "topology": "single_ended_paths", "paths": [{"from": 1, "to": 3}]},
        4,
    )
    assert out["paths"] == [{"from": 1, "to": 3}]


def test_all_problems_reported_together():
    msg = bad({"device": "interposer", "topology": "nope", "input_is_mixed_mode": "yes"}, 4)
    assert "topology" in msg and "input_is_mixed_mode" in msg


def test_lumped_through_modes_need_two_ports_and_old_name_is_rejected():
    ok = normalize({"device": "inductor", "terminal_mode": "through_port2_grounded"}, 2)
    assert ok["terminal_mode"] == "through_port2_grounded"
    ok = normalize({"device": "capacitor", "terminal_mode": "through_port2_open"}, 2)
    assert ok["terminal_mode"] == "through_port2_open"
    with pytest.raises(WorkerError) as info:
        normalize({"device": "inductor", "terminal_mode": "through_port2_open"}, 1)
    assert "needs a 2-port file" in info.value.message
    with pytest.raises(WorkerError) as info:
        normalize({"device": "inductor", "terminal_mode": "through"}, 2)
    assert "through_port2_grounded" in info.value.message
