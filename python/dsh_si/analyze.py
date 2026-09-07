"""`analyze` command: validate the interpretation, refuse changed inputs, run the
device analysis that exists, and always leave a report directory behind.

Lumped elements (inductor, capacitor) and transmission lines are complete:
per-frequency CSV, one plot per extracted quantity with invalid regions shaded,
and a headline summary over the valid region only. Interposers are the next PR;
for them the command still produces the overview plot, results.json and
report.html, and says so in `status`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from . import interpretation, line, lumped, mixed_mode, plots, quality, report
from .protocol import WorkerError
from .touchstone import load, resolve_path, sha256_file

# Display unit per extracted quantity: (axis label, multiplier from SI, file stem).
LUMPED_PLOTS = {
    "L_h": ("Inductance (nH)", 1e9, "inductance"),
    "Q": ("Quality factor Q", 1.0, "quality_factor"),
    "C_f": ("Capacitance (pF)", 1e12, "capacitance"),
    "ESR_ohm": ("ESR (Ω)", 1.0, "esr"),
}


# (axis label, [(series label, value key)], file stem) per line plot; Z_c draws Re and Im.
LINE_PLOTS = [
    (
        "Characteristic impedance (Ω)",
        [("Re Zc", "zc_re_ohm"), ("Im Zc", "zc_im_ohm")],
        "characteristic_impedance",
    ),
    ("Insertion loss (dB)", [("IL", "il_db")], "insertion_loss"),
    ("Return loss (dB)", [("RL in", "rl_in_db"), ("RL out", "rl_out_db")], "return_loss"),
]
POLARITY_NOTE = "preset polarity: the lower-numbered port of each pair is P"


def _line_modes(
    network: Any, interp: dict[str, Any], tolerances: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Name -> analyze_line result: se (2-port), pathN (single-ended 4-port), dd/cc (differential)."""
    ports = interp["ports"]
    if interp.get("input_is_mixed_mode"):
        modes = mixed_mode.split_mixed_mode_file(network)
        return {name: line.analyze_line(net, 1, 2, tolerances) for name, net in modes.items()}
    if network.nports == 2:
        return {"se": line.analyze_line(network, ports["in"][0], ports["out"][0], tolerances)}
    if "pairs" in interp:
        modes = mixed_mode.to_mixed_mode(network, interp["pairs"])
        return {name: line.analyze_line(modes[name], 1, 2, tolerances) for name in ("dd", "cc")}
    out: dict[str, dict[str, Any]] = {}
    for k, (p_in, p_out) in enumerate(zip(ports["in"], ports["out"], strict=True)):
        sub = network.subnetwork([p_in - 1, p_out - 1])
        out[f"path{k + 1}"] = line.analyze_line(sub, 1, 2, tolerances)
    return out


def _summarize_line(result: dict[str, Any]) -> dict[str, Any]:
    """Headline numbers over the valid region only, so an ambiguous branch never sets the median."""
    valid = np.array([r == "valid" for r in result["regions"]])
    zc = np.asarray(result["values"]["zc_re_ohm"], dtype=float)
    finite = zc[valid & np.isfinite(zc)]
    counts: dict[str, int] = {}
    for label in result["regions"]:
        counts[label] = counts.get(label, 0) + 1
    il = np.asarray(result["values"]["il_db"], dtype=float)
    return {
        "z_ref_ohm": result["z_ref_ohm"],
        "zc_ohm": {
            "median": float(np.median(finite)) if finite.size else None,
            "min": float(finite.min()) if finite.size else None,
            "max": float(finite.max()) if finite.size else None,
            "n_valid": int(finite.size),
        },
        "il_db_at_fmax": float(il[-1]),
        "fmax_hz": float(result["freq_hz"][-1]),
        "regions": counts,
    }


def _write_line(
    modes: dict[str, dict[str, Any]],
    interp: dict[str, Any],
    report_dir: Path,
    name: str,
    subtitle: str,
    files: list[str],
    plot_entries: list[dict[str, str]],
    warnings: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """line.csv, three PNGs per mode, warnings; returns (summary, report sections)."""
    header = [
        "mode",
        "freq_hz",
        "il_db",
        "rl_in_db",
        "rl_out_db",
        "zc_re_ohm",
        "zc_im_ohm",
        "region",
    ]

    def rows():
        for mode, res in modes.items():
            values, freq = res["values"], res["freq_hz"]
            for k in range(len(freq)):
                yield [
                    mode,
                    float(freq[k]),
                    *(float(values[key][k]) for key in header[2:7]),
                    res["regions"][k],
                ]

    files.append(str(report.write_csv(report_dir / "line.csv", header, rows())))
    sections: list[dict[str, Any]] = []
    is_preset = interp.get("through_convention") in ("odd_even", "half_split")
    summary: dict[str, Any] = {
        "through_convention": interp.get("through_convention"),
        "polarity_note": POLARITY_NOTE if is_preset and "pairs" in interp else None,
        "modes": {},
    }
    single = len(modes) == 1
    for mode, res in modes.items():
        prefix = "" if single else f"{mode}_"
        for ylabel, series, stem in LINE_PLOTS:
            fig = plots.line_quantity(
                res["freq_hz"],
                [(label, res["values"][key]) for label, key in series],
                res["regions"],
                ylabel,
                f"{ylabel.split(' (')[0]} of {name}" + ("" if single else f" ({mode})"),
                subtitle,
            )
            png = plots.save_png(fig, report_dir / f"{prefix}{stem}.png")
            files.append(str(png))
            plot_entries.append(
                {
                    "name": f"{prefix}{stem}",
                    "path": str(png),
                    "title": f"{ylabel} vs frequency ({mode})",
                }
            )
        for warning in res["warnings"]:
            warnings.append(f"{mode}: {warning}")
        stats = _summarize_line(res)
        summary["modes"][mode] = stats
        if stats["regions"].get("ambiguous") or stats["regions"].get("singular"):
            warnings.append(
                f"{mode}: {stats['regions'].get('ambiguous', 0)} ambiguous and "
                f"{stats['regions'].get('singular', 0)} singular Z_c points are excluded "
                "from the headline numbers"
            )
        zc = stats["zc_ohm"]
        sections.append(
            {
                "heading": f"Line analysis ({mode}, Z_ref {stats['z_ref_ohm']:g} Ω)",
                "table": {
                    "header": ["Quantity", "Value"],
                    "rows": [
                        [
                            "Z_c median (valid region)",
                            f"{zc['median']:.4g} Ω" if zc["median"] is not None else "n/a",
                        ],
                        [
                            "Z_c min / max",
                            f"{zc['min']:.4g} / {zc['max']:.4g} Ω"
                            if zc["median"] is not None
                            else "n/a",
                        ],
                        [
                            "IL at f_max",
                            f"{stats['il_db_at_fmax']:.3g} dB at {stats['fmax_hz'] / 1e9:.3g} GHz",
                        ],
                        ["Regions", ", ".join(f"{k} {v}" for k, v in stats["regions"].items())],
                    ],
                },
                "text": (summary["polarity_note"] or "") if mode == "dd" else "",
            }
        )
        for entry in plot_entries:
            if entry["name"] == "s_magnitude":
                continue
            if single or entry["name"].startswith(f"{mode}_"):
                sections.append({"heading": entry["title"], "image": entry["path"]})
    return summary, sections


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
    elif interp["device"] == "transmission_line":
        modes = _line_modes(network, interp, tolerances)
        line_plots: list[dict[str, str]] = []
        summary, lumped_sections = _write_line(
            modes, interp, report_dir, path.name, subtitle, files, line_plots, warnings
        )
        plot_entries[:0] = line_plots  # the key plot (first) is the characteristic impedance
        status = "complete"
    else:
        warnings.append(
            f"{interp['device']} analysis arrives in the interposer PR; only the overview is reported"
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
