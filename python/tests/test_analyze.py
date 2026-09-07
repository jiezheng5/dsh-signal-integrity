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


def test_line_overview_only_report(line, tmp_path):
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
    assert result["status"] == "overview_only"
    assert any("milestone 4" in w for w in result["warnings"])
    report_dir = Path(result["report_dir"])
    assert report_dir.parent == tmp_path / "out" / "analyze"
    assert report_dir.name.startswith(f"line-{digest[:8]}-")
    names = {Path(f).name for f in result["files"]}
    assert names == {"s_magnitude.png", "results.json", "report.html"}
    results = json.loads((report_dir / "results.json").read_text())
    assert results["input"]["sha256"] == digest
    assert set(results["versions"]) >= {"dsh_si", "scikit-rf", "numpy", "matplotlib"}
    assert results["quality"]["passivity"]["p370"]["evaluation"] == "good"
    html = (report_dir / "report.html").read_text()
    assert "data:image/png;base64," in html and "results.json" in html
    assert result["plots"][0]["name"] == "s_magnitude"
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
