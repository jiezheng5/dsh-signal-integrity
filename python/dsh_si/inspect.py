"""`inspect` command: identify the file, screen its quality, and tell the agent
which interpretation questions it still has to ask before analysis."""

from __future__ import annotations

from typing import Any

from . import quality
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
    "transmission_line": ["ports", "pairs (if differential)", "input_is_mixed_mode"],
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
                        "label": "through",
                        "description": "Port 1 is the input and port 2 the output (transmission line, series element in a through fixture).",
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
    return {
        "path": str(path),
        "hash": file_hash,
        "metadata": metadata,
        "quality": checks,
        "warnings": warnings,
        "questions": build_questions(metadata),
        "required_by_device": REQUIRED_BY_DEVICE,
    }
