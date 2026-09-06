"""`analyze` command: validate the interpretation, refuse changed inputs, run the
device analysis that exists, and always leave a report directory behind.

Device analyses land in later milestones (lumped.py is the domain owner's;
lines and interposers are milestone 4). Until then the command still produces
the overview plot, results.json and report.html, and says so in `status`.
"""

from __future__ import annotations

from typing import Any

from . import interpretation, plots, quality, report
from .protocol import WorkerError
from .touchstone import load, resolve_path, sha256_file


def _lumped(network: Any, interp: dict[str, Any], warnings: list[str]) -> dict[str, Any] | None:
    from . import lumped

    try:
        z = lumped.impedance_from_network(network, interp["terminal_mode"])
        freq = network.frequency.f
        if interp["device"] == "inductor":
            values = lumped.inductor_lq(z, freq)
        else:
            values = lumped.capacitor_c(z, freq)
        srf = lumped.self_resonance_hz(z, freq)
        regions = lumped.classify_region(z, freq, interp["device"])
    except NotImplementedError as exc:
        warnings.append(f"lumped extraction pending in python/dsh_si/lumped.py ({exc})")
        return None
    return {"z": z, "values": values, "srf_hz": srf, "regions": regions}


def run(payload: dict[str, Any]) -> dict[str, Any]:
    path = resolve_path(payload.get("path"))
    expected_hash = payload.get("hash")
    if not isinstance(expected_hash, str) or len(expected_hash) != 64:
        raise WorkerError(
            "bad_request", "payload.hash must be the 64-character sha256 returned by inspect"
        )
    actual_hash = sha256_file(path)
    if actual_hash != expected_hash:
        raise WorkerError(
            "hash_mismatch",
            f"{path.name} changed since it was inspected (sha256 {actual_hash[:12]}… vs {expected_hash[:12]}…); run si_inspect again",
        )
    output_dir = payload.get("output_dir")
    if not isinstance(output_dir, str) or output_dir == "":
        raise WorkerError("bad_request", "payload.output_dir must be a directory path")
    tolerances = payload.get("tolerances") if isinstance(payload.get("tolerances"), dict) else {}

    network, metadata, warnings = load(path)
    interp = interpretation.normalize(payload.get("interpretation"), metadata["n_ports"])
    checks = quality.run_all(network, tolerances)

    report_dir = report.create_report_dir(output_dir, path.stem, actual_hash, kind="analyze")
    files: list[str] = []
    plot_entries: list[dict[str, str]] = []

    subtitle = (
        f"{metadata['n_ports']}-port · {metadata['n_freq']} points · Z0 {metadata['reference_impedance'][0]['re']:g} Ω · "
        f"device {interp['device']} · sha256 {actual_hash[:8]}"
    )
    overview = plots.save_png(
        plots.s_magnitude_overview(network, path.name, subtitle), report_dir / "s_magnitude.png"
    )
    files.append(str(overview))
    plot_entries.append(
        {"name": "s_magnitude", "path": str(overview), "title": f"|S| overview of {path.name}"}
    )

    status = "overview_only"
    summary: dict[str, Any] = {}
    device_result = None
    if interp["device"] in ("inductor", "capacitor"):
        device_result = _lumped(network, interp, warnings)
        if device_result is not None:
            status = "complete"
            summary = _summarize_lumped(device_result, interp, network)
    else:
        warnings.append(
            f"{interp['device']} analysis arrives in milestone 4; only the overview is reported"
        )

    results = {
        "input": {"path": str(path), "sha256": actual_hash, "metadata": metadata},
        "interpretation": interp,
        "settings": {"tolerances": tolerances},
        "versions": report.versions(),
        "quality": checks,
        "status": status,
        "summary": summary,
        "warnings": warnings,
        "plots": plot_entries,
    }
    files.append(str(report.write_json(report_dir / "results.json", results)))
    sections: list[dict[str, Any]] = [
        {"heading": "Input", "pre": f"{path}\nsha256 {actual_hash}\n{subtitle}"},
        {"heading": "|S| overview", "image": overview},
        {
            "heading": "Quality (IEEE P370 bands · exact detail)",
            "table": {
                "header": ["Check", "P370", "Exact"],
                "rows": [
                    [
                        "Passivity",
                        checks["passivity"]["p370"]["evaluation"],
                        f"max σ {checks['passivity']['sigma_max_worst']:.4f}, {checks['passivity']['violation_count']} violating",
                    ],
                    [
                        "Reciprocity",
                        checks["reciprocity"]["p370"]["evaluation"],
                        "n/a"
                        if not checks["reciprocity"].get("applicable")
                        else f"max |Sij-Sji| {checks['reciprocity']['max_abs_diff_worst']:.3g}, {checks['reciprocity']['violation_count']} violating",
                    ],
                    ["Causality", checks["causality"]["p370"]["evaluation"], "screening only"],
                ],
            },
        },
        {"heading": "Status", "text": f"{status}. " + " ".join(warnings)},
        {"heading": "Files", "links": [f for f in files if not f.endswith(".html")]},
    ]
    files.append(
        str(
            report.write_html(
                report_dir / "report.html", f"Signal-integrity report: {path.name}", sections
            )
        )
    )

    return {
        "path": str(path),
        "hash": actual_hash,
        "device": interp["device"],
        "interpretation": interp,
        "status": status,
        "report_dir": str(report_dir),
        "files": files,
        "plots": plot_entries,
        "summary": summary,
        "warnings": warnings,
    }


def _summarize_lumped(
    result: dict[str, Any], interp: dict[str, Any], network: Any
) -> dict[str, Any]:
    """Headline numbers once lumped.py exists; shape only, filled by milestone 3 follow-up."""
    import numpy as np

    values = result["values"]
    out: dict[str, Any] = {"terminal_mode": interp["terminal_mode"], "srf_hz": result["srf_hz"]}
    for key, arr in values.items():
        finite = np.asarray(arr, dtype=float)
        finite = finite[np.isfinite(finite)]
        out[key] = {
            "median": float(np.median(finite)) if finite.size else None,
            "n_valid": int(finite.size),
        }
    out["n_points"] = int(np.asarray(network.frequency.f).size)
    return out
