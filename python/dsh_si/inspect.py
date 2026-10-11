"""`inspect` command: identify the file, screen its quality, and tell the agent
which interpretation questions it still has to ask before analysis."""

from __future__ import annotations

from typing import Any

from . import plots, quality, report
from .touchstone import load, resolve_path, sha256_file

DEVICE_OPTIONS = [
    {
        "label": "inductor",
        "description": "Lumped inductor; extract series L and Q from the impedance.",
    },
    {"label": "capacitor", "description": "Lumped capacitor; extract series C from the impedance."},
    {
        "label": "transmission_line",
        "description": "Uniform line or cable segment; insertion loss, return loss, characteristic impedance.",
    },
    {
        "label": "interposer",
        "description": "Connector, package, or interposer; per-port return loss and every through path.",
    },
]

# What si_analyze will require per device, so the agent can gather it up front.
REQUIRED_BY_DEVICE: dict[str, list[str]] = {
    "inductor": ["terminal_mode"],
    "capacitor": ["terminal_mode"],
    "transmission_line": [
        "through_convention (4-port) or ports",
        "topology (4-port)",
        "input_is_mixed_mode",
    ],
    "interposer": ["paths", "pairs (if differential)", "input_is_mixed_mode"],
}


def build_questions(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    """Questions shaped exactly like DSH's `ask_user_question` parameters."""
    n_ports = int(metadata["n_ports"])
    questions: list[dict[str, Any]] = [
        {
            "id": "device",
            "header": "Device",
            "question": f"What device does this {n_ports}-port S-parameter file describe?",
            "options": DEVICE_OPTIONS,
        }
    ]
    if n_ports == 1:
        questions.append(
            {
                "id": "terminal_mode",
                "header": "Terminals",
                "question": "A one-port file gives the impedance seen at that port. Is that the intended terminal pair of the device?",
                "options": [
                    {
                        "label": "one_port",
                        "description": "Yes: port 1 to ground is the device's terminal pair.",
                    },
                ],
            }
        )
    elif n_ports == 2:
        questions.append(
            {
                "id": "terminal_mode",
                "header": "Port roles",
                "question": "How should the two ports be interpreted?",
                "options": [
                    {
                        "label": "through_port2_grounded",
                        "description": "Element in a through fixture, port 2 grounded in use: Z = 1/Y11 (input impedance with V2 = 0).",
                    },
                    {
                        "label": "through_port2_open",
                        "description": "Element in a through fixture, port 2 open in use: Z = Z11 (input impedance with I2 = 0).",
                    },
                    {
                        "label": "two_terminal_differential",
                        "description": "The two ports are the two terminals of one lumped element; use Z11+Z22-Z12-Z21.",
                    },
                    {
                        "label": "one_port",
                        "description": "Only port 1 matters; port 2 is terminated and ignored.",
                    },
                ],
            }
        )
    else:
        questions.append(
            {
                "id": "topology",
                "header": "Topology",
                "question": f"How are the {n_ports} ports organized?",
                "options": [
                    {
                        "label": "single_ended_paths",
                        "description": "Independent single-ended through paths; name each input/output pair.",
                    },
                    {
                        "label": "differential_pairs",
                        "description": "Ports form P/N pairs; name each pair's positive and negative ports so the data can be converted to mixed mode.",
                    },
                    {
                        "label": "mixed_mode_already",
                        "description": "The file already stores mixed-mode (Sdd/Sdc/Scd/Scc) data; do not convert again.",
                    },
                ],
            }
        )
        if n_ports == 4:
            questions.append(
                {
                    "id": "through_convention",
                    "header": "Through paths",
                    "question": "Which ports connect through the line? (Preset polarity: the lower port of a pair is P.)",
                    "options": [
                        {
                            "label": "odd_even",
                            "description": "1\u21922 and 3\u21924 are the through paths; pairs are 1/3 and 2/4 (PLTS-style).",
                        },
                        {
                            "label": "half_split",
                            "description": "1\u21923 and 2\u21924 are the through paths; pairs are 1/2 and 3/4.",
                        },
                        {
                            "label": "custom",
                            "description": "Enter ports {in, out} and, for differential, pairs {p, n} yourself.",
                        },
                    ],
                }
            )
    if metadata.get("mixed_mode_hint") and n_ports != 1:
        questions.append(
            {
                "id": "input_is_mixed_mode",
                "header": "Mixed mode",
                "question": "The file header mentions mixed-mode terms. Is the stored data already mixed-mode?",
                "options": [
                    {"label": "yes", "description": "Already mixed-mode; analyze as stored."},
                    {"label": "no", "description": "Single-ended data; convert after pairing."},
                ],
            }
        )
    return questions


def run(payload: dict[str, Any]) -> dict[str, Any]:
    path = resolve_path(payload.get("path"))
    tolerances = payload.get("tolerances") or {}
    if not isinstance(tolerances, dict):
        tolerances = {}
    file_hash = sha256_file(path)
    network, metadata, warnings = load(path)
    checks = quality.run_all(network, tolerances)
    if not checks["passivity"]["passive"]:
        warnings.append(
            f"passivity violated at {checks['passivity']['violation_count']} of {metadata['n_freq']} points "
            f"(max singular value {checks['passivity']['sigma_max_worst']:.4f})"
        )
    if checks["reciprocity"].get("applicable") and not checks["reciprocity"]["reciprocal"]:
        warnings.append(
            f"reciprocity violated at {checks['reciprocity']['violation_count']} points "
            f"(max |Sij-Sji| = {checks['reciprocity']['max_abs_diff_worst']:.4g})"
        )
    plot_entries: list[dict[str, str]] = []
    report_dir: str | None = None
    output_dir = payload.get("output_dir")
    if isinstance(output_dir, str) and output_dir:
        directory = report.create_report_dir(output_dir, path.stem, file_hash, kind="inspect")
        subtitle = (
            f"{metadata['n_ports']}-port · {metadata['n_freq']} points · "
            f"Z0 {metadata['reference_impedance'][0]['re']:g} Ω · sha256 {file_hash[:8]}"
        )
        png = plots.save_png(
            plots.s_magnitude_overview(network, path.name, subtitle), directory / "s_magnitude.png"
        )
        plot_entries.append(
            {"name": "s_magnitude", "path": str(png), "title": f"|S| overview of {path.name}"}
        )
        report_dir = str(directory)
    return {
        "path": str(path),
        "hash": file_hash,
        "metadata": metadata,
        "quality": checks,
        "warnings": warnings,
        "questions": build_questions(metadata),
        "required_by_device": REQUIRED_BY_DEVICE,
        "report_dir": report_dir,
        "plots": plot_entries,
    }
