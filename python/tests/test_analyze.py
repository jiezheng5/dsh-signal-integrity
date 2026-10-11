import json
from pathlib import Path

import pytest

from dsh_si.analyze import run
from dsh_si.inspect import run as inspect_run
from dsh_si.protocol import WorkerError
from dsh_si.touchstone import sha256_file

from . import fixtures


@pytest.fixture
def line(tmp_path: Path) -> tuple[Path, str]:
    path = fixtures.write(
        fixtures.lossy_line(freq=fixtures.frequency(npoints=101)), tmp_path / "in", "line"
    )
    return path, sha256_file(path)


def base(path: Path, digest: str, out: Path, **interp) -> dict:
    return {"path": str(path), "hash": digest, "output_dir": str(out), "interpretation": interp}


def test_hash_mismatch_refuses(line, tmp_path):
    path, digest = line
    with pytest.raises(WorkerError) as info:
        run(
            base(
                path,
                "0" * 64,
                tmp_path / "out",
                device="transmission_line",
                ports={"in": [1], "out": [2]},
            )
        )
    assert info.value.code == "hash_mismatch"
    assert "run si_inspect again" in info.value.message
    assert not (tmp_path / "out").exists()


def test_bad_hash_shape_is_bad_request(line, tmp_path):
    path, _ = line
    with pytest.raises(WorkerError) as info:
        run(base(path, "abc", tmp_path / "out", device="transmission_line"))
    assert info.value.code == "bad_request"


def test_invalid_interpretation_writes_nothing(line, tmp_path):
    path, digest = line
    with pytest.raises(WorkerError) as info:
        run(base(path, digest, tmp_path / "out", device="inductor"))
    assert info.value.code == "interpretation_invalid"
    assert not (tmp_path / "out").exists()


def test_line_report_is_complete(line, tmp_path):
    path, digest = line
    result = run(
        base(
            path,
            digest,
            tmp_path / "out",
            device="transmission_line",
            ports={"in": [1], "out": [2]},
        )
    )
    assert result["status"] == "complete"
    assert not any("milestone 4" in w for w in result["warnings"])
    report_dir = Path(result["report_dir"])
    assert report_dir.parent == tmp_path / "out" / "analyze"
    assert report_dir.name.startswith(f"line-{digest[:8]}-")
    names = {Path(f).name for f in result["files"]}
    assert names == {
        "s_magnitude.png",
        "line.csv",
        "insertion_loss.png",
        "return_loss.png",
        "characteristic_impedance.png",
        "results.json",
        "report.html",
    }
    results = json.loads((report_dir / "results.json").read_text())
    assert results["input"]["sha256"] == digest
    assert set(results["versions"]) >= {"dsh_si", "scikit-rf", "numpy", "matplotlib"}
    assert results["quality"]["passivity"]["p370"]["evaluation"] == "good"
    html = (report_dir / "report.html").read_text()
    assert "data:image/png;base64," in html and "results.json" in html
    assert result["plots"][0]["name"] == "characteristic_impedance"
    assert (report_dir / "s_magnitude.png").stat().st_size > 5000


def test_inductor_report_has_csv_plots_and_headline(tmp_path):
    path = fixtures.write(
        fixtures.series_rl_oneport(freq=fixtures.frequency(npoints=51)), tmp_path / "in", "rl"
    )
    digest = sha256_file(path)
    result = run(base(path, digest, tmp_path / "out", device="inductor", terminal_mode="one_port"))
    assert result["status"] == "complete"
    report_dir = Path(result["report_dir"])
    names = {Path(f).name for f in result["files"]}
    assert names == {
        "s_magnitude.png",
        "inductance.png",
        "quality_factor.png",
        "lumped.csv",
        "results.json",
        "report.html",
    }
    assert [p["name"] for p in result["plots"]] == ["inductance", "quality_factor", "s_magnitude"]
    csv_lines = (report_dir / "lumped.csv").read_text().splitlines()
    assert csv_lines[0] == "freq_hz,re_z_ohm,im_z_ohm,L_h,Q,R_ohm,region"
    assert len(csv_lines) == 52
    assert csv_lines[1].endswith(",valid")
    summary = result["summary"]
    assert summary["L_h"]["median"] == pytest.approx(10e-9, rel=1e-6)
    assert summary["L_h"]["n_valid"] == 51
    assert summary["srf_hz"] is None
    assert summary["regions"] == {"valid": 51}
    html = (report_dir / "report.html").read_text()
    assert html.count("data:image/png;base64,") == 3 and "lumped.csv" in html


def test_capacitor_report_flags_points_beyond_resonance(tmp_path):
    path = fixtures.write(
        fixtures.series_rlc_oneport(freq=fixtures.frequency(0.1, 10.0, 100)), tmp_path / "in", "c"
    )
    digest = sha256_file(path)
    result = run(base(path, digest, tmp_path / "out", device="capacitor", terminal_mode="one_port"))
    assert result["status"] == "complete"
    names = {Path(f).name for f in result["files"]}
    assert {"capacitance.png", "esr.png", "lumped.csv"} <= names
    summary = result["summary"]
    assert summary["srf_hz"] == pytest.approx(1.5915e9, rel=5e-3)
    # series RLC: C_eff = C / (1 - w^2 L C) grows toward the SRF, so only the low end is ~C
    assert summary["C_f"]["min"] == pytest.approx(1e-12, rel=5e-3)
    assert 1e-12 < summary["C_f"]["median"] < 3e-12
    assert summary["regions"]["beyond_srf"] > 0 and summary["regions"]["near_srf"] > 0
    assert any("beyond" in w or "resonance" in w for w in result["warnings"])


def test_inspect_writes_overview_plot_when_output_dir_given(line, tmp_path):
    path, digest = line
    result = inspect_run({"path": str(path), "output_dir": str(tmp_path / "out")})
    assert result["report_dir"].startswith(str(tmp_path / "out" / "inspect"))
    assert Path(result["plots"][0]["path"]).exists()
    without = inspect_run({"path": str(path)})
    assert without["plots"] == [] and without["report_dir"] is None


def test_report_dir_rejects_unwritable_location(line):
    path, digest = line
    with pytest.raises(WorkerError) as info:
        run(
            base(
                path,
                digest,
                Path("/proc/definitely-not-writable"),
                device="transmission_line",
                ports={"in": [1], "out": [2]},
            )
        )
    assert info.value.code == "report_write_failed"


def test_two_port_line_summary_and_csv(line, tmp_path):
    path, digest = line
    out = run(base(path, digest, tmp_path / "out", device="transmission_line"))
    se = out["summary"]["modes"]["se"]
    assert se["zc_ohm"]["median"] == pytest.approx(50.0, abs=0.5)
    assert se["zc_ohm"]["n_valid"] == 101
    assert se["il_db_at_fmax"] == pytest.approx(5.0 * 0.020 * (20.0**0.5), abs=0.05)
    header = (Path(out["report_dir"]) / "line.csv").read_text().splitlines()[0]
    assert header == "mode,freq_hz,il_db,rl_in_db,rl_out_db,zc_re_ohm,zc_im_ohm,region"


def test_four_port_differential_line_reports_dd_and_cc(tmp_path):
    net = fixtures.two_uncoupled_lines_odd_even(freq=fixtures.frequency(npoints=51))
    path = fixtures.write(net, tmp_path / "in", "diff")
    out = run(
        base(
            path,
            sha256_file(path),
            tmp_path / "out",
            device="transmission_line",
            topology="differential_pairs",
            through_convention="odd_even",
        )
    )
    assert out["status"] == "complete"
    modes = out["summary"]["modes"]
    assert modes["dd"]["zc_ohm"]["median"] == pytest.approx(100.0, abs=1.0)
    assert modes["cc"]["zc_ohm"]["median"] == pytest.approx(25.0, abs=0.25)
    assert out["summary"]["through_convention"] == "odd_even"
    assert "lower" in out["summary"]["polarity_note"]
    names = {Path(f).name for f in out["files"]}
    assert {"dd_characteristic_impedance.png", "cc_insertion_loss.png", "line.csv"} <= names
    rows = (Path(out["report_dir"]) / "line.csv").read_text().splitlines()
    assert rows[1].startswith("dd,") and rows[52].startswith("cc,")


def test_four_port_single_ended_preset_reports_two_paths(tmp_path):
    net = fixtures.two_uncoupled_lines(freq=fixtures.frequency(npoints=21))
    path = fixtures.write(net, tmp_path / "in", "se4")
    out = run(
        base(
            path,
            sha256_file(path),
            tmp_path / "out",
            device="transmission_line",
            through_convention="half_split",
        )
    )
    assert out["status"] == "complete"
    assert set(out["summary"]["modes"]) == {"path1", "path2"}
    assert out["summary"]["modes"]["path1"]["zc_ohm"]["median"] == pytest.approx(50.0, abs=0.5)


def test_differential_report_warns_when_the_pair_polarity_looks_swapped(tmp_path):
    net = fixtures.two_uncoupled_lines(freq=fixtures.frequency(npoints=51))
    path = fixtures.write(net, tmp_path / "in", "swapped")
    out = run(
        base(
            path,
            sha256_file(path),
            tmp_path / "out",
            device="transmission_line",
            topology="differential_pairs",
            # Far end reversed relative to the preset, so the through response inverts.
            pairs=[{"name": "pair1", "p": 1, "n": 2}, {"name": "pair2", "p": 4, "n": 3}],
            ports={"in": [1, 2], "out": [3, 4]},
        )
    )
    assert any("polarity" in w for w in out["warnings"])
    # The reported numbers are unchanged by the swap.
    assert out["summary"]["modes"]["dd"]["zc_ohm"]["median"] == pytest.approx(100.0, abs=1.0)
