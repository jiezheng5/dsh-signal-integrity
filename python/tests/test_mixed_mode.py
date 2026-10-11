import numpy as np
import pytest

from dsh_si import line, mixed_mode
from dsh_si.protocol import WorkerError

from . import fixtures


def test_preset_half_split_for_four_ports():
    m = mixed_mode.preset_mapping("half_split", 4)
    assert m["ports"] == {"in": [1, 2], "out": [3, 4]}
    assert m["pairs"] == [{"name": "pair1", "p": 1, "n": 2}, {"name": "pair2", "p": 3, "n": 4}]


def test_preset_odd_even_for_four_ports():
    m = mixed_mode.preset_mapping("odd_even", 4)
    assert m["ports"] == {"in": [1, 3], "out": [2, 4]}
    assert m["pairs"] == [{"name": "pair1", "p": 1, "n": 3}, {"name": "pair2", "p": 2, "n": 4}]


def test_preset_rejects_odd_port_count_and_custom():
    with pytest.raises(WorkerError) as info:
        mixed_mode.preset_mapping("odd_even", 3)
    assert info.value.code == "interpretation_invalid"
    with pytest.raises(WorkerError):
        mixed_mode.preset_mapping("custom", 4)


@pytest.fixture(scope="module")
def freq():
    return fixtures.frequency(npoints=51)


def test_to_mixed_mode_half_split_gives_100_and_25_ohm(freq):
    four = fixtures.two_uncoupled_lines(freq=freq)
    modes = mixed_mode.to_mixed_mode(four, mixed_mode.preset_mapping("half_split", 4)["pairs"])
    dd, cc = modes["dd"], modes["cc"]
    assert dd.nports == 2 and cc.nports == 2
    assert np.allclose(dd.z0, 100.0) and np.allclose(cc.z0, 25.0)
    zc_dd, _ = line.select_zc_branch(line.zc_candidates(dd), freq.f)
    zc_cc, _ = line.select_zc_branch(line.zc_candidates(cc), freq.f)
    assert np.allclose(zc_dd.real, 100.0, atol=1.0) and np.allclose(zc_cc.real, 25.0, atol=0.25)
    single = fixtures.lossy_line(freq=freq)
    assert np.allclose(line.insertion_loss_db(dd, 1, 2), line.insertion_loss_db(single, 1, 2))


def test_to_mixed_mode_odd_even_matches_half_split(freq):
    a = mixed_mode.to_mixed_mode(
        fixtures.two_uncoupled_lines(freq=freq), mixed_mode.preset_mapping("half_split", 4)["pairs"]
    )
    b = mixed_mode.to_mixed_mode(
        fixtures.two_uncoupled_lines_odd_even(freq=freq),
        mixed_mode.preset_mapping("odd_even", 4)["pairs"],
    )
    assert np.allclose(a["dd"].s, b["dd"].s) and np.allclose(a["cc"].s, b["cc"].s)


def test_swapping_polarity_of_one_pair_flips_sdd21_phase_only(freq):
    four = fixtures.two_uncoupled_lines(freq=freq)
    normal = mixed_mode.to_mixed_mode(four, mixed_mode.preset_mapping("half_split", 4)["pairs"])
    swapped_pairs = [{"name": "pair1", "p": 1, "n": 2}, {"name": "pair2", "p": 4, "n": 3}]
    swapped = mixed_mode.to_mixed_mode(four, swapped_pairs)
    phase = np.angle(swapped["dd"].s[:, 1, 0]) - np.angle(normal["dd"].s[:, 1, 0])
    assert np.allclose(np.abs(np.angle(np.exp(1j * phase))), np.pi)
    assert np.allclose(np.abs(swapped["dd"].s[:, 1, 0]), np.abs(normal["dd"].s[:, 1, 0]))
    assert np.abs(normal["mixed"].s[:, 0, 2]).max() < 1e-12  # no mode conversion, uncoupled lines


def test_reported_quantities_are_invariant_under_any_polarity_choice(freq):
    """IL, RL and Z_c cannot distinguish P from N, so the preset polarity is safe.

    A P/N swap negates S21 and S12, which negates every ABCD term, so B/C and all
    magnitudes are unchanged. This is what lets the preset assume the lower-numbered
    port is P without asking.
    """
    four = fixtures.two_uncoupled_lines(freq=freq)
    base = mixed_mode.preset_mapping("half_split", 4)["pairs"]
    variants = [
        [{"name": "pair1", "p": 1, "n": 2}, {"name": "pair2", "p": 4, "n": 3}],  # far end
        [{"name": "pair1", "p": 2, "n": 1}, {"name": "pair2", "p": 3, "n": 4}],  # near end
        [{"name": "pair1", "p": 2, "n": 1}, {"name": "pair2", "p": 4, "n": 3}],  # both
    ]
    reference = {
        mode: line.analyze_line(mixed_mode.to_mixed_mode(four, base)[mode], 1, 2, {})
        for mode in ("dd", "cc")
    }
    for pairs in variants:
        modes = mixed_mode.to_mixed_mode(four, pairs)
        for mode in ("dd", "cc"):
            got = line.analyze_line(modes[mode], 1, 2, {})
            for key in ("zc_re_ohm", "zc_im_ohm", "il_db", "rl_in_db", "rl_out_db"):
                assert np.allclose(got["values"][key], reference[mode]["values"][key], atol=0)


def test_polarity_check_flags_an_inverted_through_and_passes_a_normal_one(freq):
    four = fixtures.two_uncoupled_lines(freq=freq)
    normal = mixed_mode.to_mixed_mode(four, mixed_mode.preset_mapping("half_split", 4)["pairs"])
    assert mixed_mode.polarity_check(normal["dd"]) is None
    swapped = mixed_mode.to_mixed_mode(
        four, [{"name": "pair1", "p": 1, "n": 2}, {"name": "pair2", "p": 4, "n": 3}]
    )
    message = mixed_mode.polarity_check(swapped["dd"])
    assert message is not None and "polarity" in message


def test_polarity_check_is_silent_when_there_is_no_through_path(freq):
    four = fixtures.two_uncoupled_lines(freq=freq)
    modes = mixed_mode.to_mixed_mode(four, mixed_mode.preset_mapping("half_split", 4)["pairs"])
    dead = modes["dd"].copy()
    dead.s[:, 1, 0] = 0.0
    dead.s[:, 0, 1] = 0.0
    assert mixed_mode.polarity_check(dead) is None


def test_split_mixed_mode_file_takes_stored_order(freq):
    four = fixtures.two_uncoupled_lines(freq=freq)
    mixed = mixed_mode.to_mixed_mode(four, mixed_mode.preset_mapping("half_split", 4)["pairs"])[
        "mixed"
    ]
    modes = mixed_mode.split_mixed_mode_file(mixed)
    assert np.allclose(modes["dd"].z0, 100.0) and np.allclose(modes["cc"].z0, 25.0)
