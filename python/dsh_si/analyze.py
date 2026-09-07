"""`analyze` command: validate the interpretation, refuse changed inputs, run the
device analysis that exists, and always leave a report directory behind.

Lumped elements (inductor, capacitor) are complete: per-frequency CSV, one plot
per extracted quantity with invalid regions shaded, and a headline summary over
the valid region only. Lines and interposers are milestone 4; for them the
command still produces the overview plot, results.json and report.html, and
says so in `status`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from . import interpretation, lumped, plots, quality, report
from .protocol import WorkerError
from .touchstone import load, resolve_path, sha256_file

# Display unit per extracted quantity: (axis label, multiplier from SI, file stem).
LUMPED_PLOTS = {
    "L_h": ("Inductance (nH)", 1e9, "inductance"),
    "Q": ("Quality factor Q", 1.0, "quality_factor"),
    "C_f": ("Capacitance (pF)", 1e12, "capacitance"),
    "ESR_ohm": ("ESR (Ω)", 1.0, "esr"),
}


def _lumped(network: Any, interp: dict[str, Any]) -> dict[str, Any]:
    z = lumped.impedance_from_network(network, interp["terminal_mode"])
    freq = network.frequency.f
    if interp["device"] == "inductor":
        values = lumped.inductor_lq(z, freq)
    else:
        values = lumped.capacitor_c(z, freq)
    srf = lumped.self_resonance_hz(z, freq)
    regions = lumped.classify_region(z, freq, interp["device"])
    return {"z": z, "freq_hz": freq, "values": values, "srf_hz": srf, "regions": regions}


def _write_lumped(
    result: dict[str, Any],
    interp: dict[str, Any],
    report_dir: Path,
    name: str,
    subtitle: str,
    files: list[str],
    plot_entries: list[dict[str, str]],
    warnings: list[str],
) -> dict[str, Any]:
    """CSV, one PNG per quantity, region warnings; returns the headline summary."""
    values, regions, freq = result["values"], result["regions"], result["freq_hz"]
    z = result["z"]
    header = ["freq_hz", "re_z_ohm", "im_z_ohm", *values.keys(), "region"]
    rows = (
        [float(freq[k]), float(z[k].real), float(z[k].imag)]
        + [float(values[key][k]) for key in values]
        + [regions[k]]
        for k in range(len(freq))
    )
    files.append(str(report.write_csv(report_dir / "lumped.csv", header, rows)))

    for key, arr in values.items():
        if key not in LUMPED_PLOTS:
            continue  # R_ohm rides along in the CSV; Q already carries the loss
        ylabel, scale, stem = LUMPED_PLOTS[key]
        fig = plots.lumped_quantity(
            freq,
            arr,
            regions,
            result["srf_hz"],
            ylabel,
            scale,
            f"{ylabel.split(' (')[0]} of {name}",
            subtitle,
        )
        png = plots.save_png(fig, report_dir / f"{stem}.png")
        files.append(str(png))
        plot_entries.append({"name": stem, "path": str(png), "title": f"{ylabel} vs frequency"})

    counts: dict[str, int] = {}
    for label in regions:
        counts[label] = counts.get(label, 0) + 1
    if result["srf_hz"] is not None:
        beyond = counts.get("beyond_srf", 0) + counts.get("near_srf", 0)
        warnings.append(
            f"self-resonance at {result['srf_hz'] / 1e9:.4g} GHz: {beyond} of {len(regions)} points "
            "are near or beyond it and are excluded from the headline numbers"
        )
    if counts.get("wrong_sign"):
        warnings.append(
            f"{counts['wrong_sign']} points have the wrong reactance sign for a {interp['device']} "
            "and are excluded from the headline numbers"
        )
    return _summarize_lumped(result, interp, counts)


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
    lumped_sections: list[dict[str, Any]] = []
    if interp["device"] in ("inductor", "capacitor"):
        device_result = _lumped(network, interp)
        device_plots: list[dict[str, str]] = []
        summary = _write_lumped(
            device_result, interp, report_dir, path.name, subtitle, files, device_plots, warnings
        )
        plot_entries[:0] = device_plots  # the key plot (first) is the extracted quantity
        status = "complete"
        lumped_sections = [
            {
                "heading": f"{interp['device'].capitalize()} extraction ({interp['terminal_mode']})",
                "table": {
                    "header": ["Quantity", "Median (valid region)", "Min", "Max", "Valid points"],
                    "rows": [
                        [
                            key,
                            f"{stat['median']:.4g}",
                            f"{stat['min']:.4g}",
                            f"{stat['max']:.4g}",
                            stat["n_valid"],
                        ]
                        if stat["n_valid"]
                        else [key, "n/a", "n/a", "n/a", 0]
                        for key, stat in summary.items()
                        if isinstance(stat, dict) and "median" in stat
                    ],
                },
                "text": (
                    f"Self-resonance {summary['srf_hz'] / 1e9:.4g} GHz. "
                    if summary["srf_hz"]
                    else "No self-resonance in band. "
                )
                + "Regions: "
                + ", ".join(f"{k} {v}" for k, v in summary["regions"].items()),
            },
            *[{"heading": entry["title"], "image": entry["path"]} for entry in device_plots],
        ]
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
        *lumped_sections,
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
    result: dict[str, Any], interp: dict[str, Any], region_counts: dict[str, int]
) -> dict[str, Any]:
    """Headline numbers over the valid region only, so a resonance never leaks into the median."""
    valid = np.array([label == "valid" for label in result["regions"]])
    out: dict[str, Any] = {
        "terminal_mode": interp["terminal_mode"],
        "srf_hz": result["srf_hz"],
        "regions": region_counts,
        "n_points": int(valid.size),
    }
    for key, arr in result["values"].items():
        arr = np.asarray(arr, dtype=float)
        finite = arr[valid & np.isfinite(arr)]
        out[key] = {
            "median": float(np.median(finite)) if finite.size else None,
            "min": float(finite.min()) if finite.size else None,
            "max": float(finite.max()) if finite.size else None,
            "n_valid": int(finite.size),
        }
    return out
