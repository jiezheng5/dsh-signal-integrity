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


def test_lumped_pending_is_reported_not_raised(tmp_path):
    path = fixtures.write(
        fixtures.series_rl_oneport(freq=fixtures.frequency(npoints=51)), tmp_path / "in", "rl"
    )
    digest = sha256_file(path)
    result = run(base(path, digest, tmp_path / "out", device="inductor", terminal_mode="one_port"))
    assert result["status"] == "overview_only"
    assert any("lumped.py" in w for w in result["warnings"])
    assert Path(result["report_dir"]).exists()


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
