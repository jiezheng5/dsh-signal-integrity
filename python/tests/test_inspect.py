from pathlib import Path

import numpy as np
import pytest

from dsh_si import quality
from dsh_si.inspect import run
from dsh_si.protocol import WorkerError
from dsh_si.touchstone import sha256_file

from . import fixtures


@pytest.fixture
def line_path(tmp_path: Path) -> Path:
    return fixtures.write(fixtures.lossy_line(), tmp_path, "line")


def test_inspect_clean_line(line_path: Path):
    result = run({"path": str(line_path)})
    assert result["hash"] == sha256_file(line_path)
    md = result["metadata"]
    assert md["n_ports"] == 2
    assert md["n_freq"] == 401
    assert md["frequency_unit"] == "ghz"
    assert md["f_min_hz"] == pytest.approx(10e6)
    assert md["f_max_hz"] == pytest.approx(20e9)
    assert md["reference_impedance"] == [{"re": 50.0, "im": 0.0}] * 2
    assert md["mixed_mode_hint"] is False
    q = result["quality"]
    assert q["passivity"]["passive"] is True
    assert q["reciprocity"]["reciprocal"] is True
    assert q["causality"]["score_percent"] == pytest.approx(100.0)
    assert q["causality"]["verdict"] == "good"
    assert "P370" in q["causality"]["method"]
    assert q["passivity"]["p370"]["evaluation"] == "good"
    assert q["reciprocity"]["p370"]["evaluation"] == "good"
    ids = [question["id"] for question in result["questions"]]
    assert ids == ["device", "terminal_mode"]
    assert {o["label"] for o in result["questions"][0]["options"]} == {
        "inductor",
        "capacitor",
        "transmission_line",
        "interposer",
    }
    assert result["warnings"] == []


def test_active_network_fails_passivity(tmp_path: Path):
    path = fixtures.write(fixtures.active_line(), tmp_path, "active")
    result = run({"path": str(path)})
    p = result["quality"]["passivity"]
    assert p["passive"] is False
    assert p["violation_count"] == 401
    assert p["sigma_max_worst"] > 1.4
    assert p["p370"]["evaluation"] == "poor"
    assert any("passivity violated" in w for w in result["warnings"])


def test_nonreciprocal_network_flagged(tmp_path: Path):
    path = fixtures.write(fixtures.nonreciprocal_line(), tmp_path, "nonrecip")
    r = run({"path": str(path)})["quality"]["reciprocity"]
    assert r["reciprocal"] is False
    assert r["max_abs_diff_worst"] > 0.5
    assert r["p370"]["evaluation"] == "poor"


def test_advanced_network_scores_low_on_causality(tmp_path: Path):
    path = fixtures.write(fixtures.advanced_line(), tmp_path, "advanced")
    c = run({"path": str(path)})["quality"]["causality"]
    assert c["applicable"] is True
    assert c["score_percent"] == pytest.approx(0.0, abs=1.0)
    assert c["verdict"] == "poor"


def test_oneport_skips_reciprocity_and_causality(tmp_path: Path):
    path = fixtures.write(fixtures.series_rl_oneport(), tmp_path, "rl")
    result = run({"path": str(path)})
    assert result["metadata"]["n_ports"] == 1
    assert result["quality"]["reciprocity"]["applicable"] is False
    assert result["quality"]["causality"]["applicable"] is False
    assert result["quality"]["causality"]["verdict"] == "not_applicable"
    assert result["quality"]["passivity"]["passive"] is True
    assert result["quality"]["passivity"]["p370"]["evaluation"] == "not_applicable"
    assert [q["id"] for q in result["questions"]] == ["device", "terminal_mode"]
    assert result["questions"][1]["options"][0]["label"] == "one_port"


def test_multiport_asks_topology(tmp_path: Path):
    four = fixtures.two_uncoupled_lines(freq=fixtures.frequency(npoints=51))
    path = fixtures.write(four, tmp_path, "four")
    result = run({"path": str(path)})
    assert result["metadata"]["n_ports"] == 4
    assert result["quality"]["passivity"]["passive"] is True
    ids = [q["id"] for q in result["questions"]]
    assert ids == ["device", "topology"]
    labels = {o["label"] for o in result["questions"][1]["options"]}
    assert labels == {"single_ended_paths", "differential_pairs", "mixed_mode_already"}


def test_mixed_mode_hint_from_comment(tmp_path: Path):
    path = fixtures.write(fixtures.lossy_line(), tmp_path, "mm")
    text = path.read_text()
    path.write_text("! Mixed-mode S-parameters Sdd11 exported\n" + text)
    result = run({"path": str(path)})
    assert result["metadata"]["mixed_mode_hint"] is True
    assert "input_is_mixed_mode" in [q["id"] for q in result["questions"]]


@pytest.mark.parametrize(
    "payload, code",
    [
        ({}, "bad_request"),
        ({"path": "relative/file.s2p"}, "bad_request"),
        ({"path": "/definitely/missing.s2p"}, "file_not_found"),
    ],
)
def test_path_errors(payload, code):
    with pytest.raises(WorkerError) as info:
        run(payload)
    assert info.value.code == code


def test_wrong_suffix(tmp_path: Path):
    path = tmp_path / "data.csv"
    path.write_text("1,2,3\n")
    with pytest.raises(WorkerError) as info:
        run({"path": str(path)})
    assert info.value.code == "unsupported_format"


def test_malformed_file(tmp_path: Path):
    path = tmp_path / "broken.s2p"
    path.write_text("# GHz S RI R 50\n1.0 0.1 0.2\n")
    with pytest.raises(WorkerError) as info:
        run({"path": str(path)})
    assert info.value.code == "parse_error"


def test_non_monotonic_frequency(tmp_path: Path):
    path = tmp_path / "nonmono.s1p"
    path.write_text("# GHz S RI R 50\n1.0 0.1 0.0\n3.0 0.1 0.0\n2.0 0.1 0.0\n")
    with pytest.raises(WorkerError) as info:
        run({"path": str(path)})
    assert info.value.code == "parse_error"
    assert "increasing" in info.value.message


def test_passivity_tolerance_is_honored(tmp_path: Path):
    line = fixtures.lossy_line()
    sigma = np.linalg.svd(line.s, compute_uv=False)[:, 0].max()
    path = fixtures.write(fixtures.active_line(gain=(1 + 5e-4) / sigma), tmp_path, "barely")
    strict = run({"path": str(path), "tolerances": {"passivity": 0.0}})["quality"]["passivity"]
    loose = run({"path": str(path), "tolerances": {"passivity": 1e-2}})["quality"]["passivity"]
    assert strict["passive"] is False
    assert loose["passive"] is True
    assert loose["tolerance"] == 1e-2


def test_p370_bands_follow_scikit_rf():
    assert quality._evaluate_passivity(100.0) == "good"
    assert quality._evaluate_passivity(99.5) == "acceptable"
    assert quality._evaluate_passivity(90.0) == "inconclusive"
    assert quality._evaluate_passivity(10.0) == "poor"
    assert quality._evaluate_passivity(None) == "inconclusive"


def test_sigma_max_matches_direct_norm():
    ntwk = fixtures.lossy_line(freq=fixtures.frequency(npoints=11))
    p = quality.passivity_detail(ntwk, 1e-9)
    direct = max(np.linalg.norm(ntwk.s[i], 2) for i in range(11))
    assert p["sigma_max_worst"] == pytest.approx(direct)
