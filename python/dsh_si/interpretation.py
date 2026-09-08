"""Validate the engineer's interpretation of a file before any analysis runs.

The model collects these answers through ask_user_question; this module is the
hard gate that refuses incomplete or inconsistent interpretations with a
message listing every problem, in the same vocabulary si_inspect proposed.
"""

from __future__ import annotations

from typing import Any

from . import mixed_mode
from .protocol import WorkerError

DEVICES = ("inductor", "capacitor", "transmission_line", "interposer")
LUMPED_MODES = (
    "one_port",
    "two_terminal_differential",
    "through_port2_grounded",
    "through_port2_open",
)
TOPOLOGIES = ("single_ended_paths", "differential_pairs", "mixed_mode_already")


def _port_list(value: Any, field: str, n_ports: int, problems: list[str]) -> list[int]:
    if not isinstance(value, list) or not value:
        problems.append(f"{field}: expected a non-empty list of port numbers (1..{n_ports})")
        return []
    ports: list[int] = []
    for item in value:
        if not isinstance(item, int) or isinstance(item, bool) or not 1 <= item <= n_ports:
            problems.append(f"{field}: port {item!r} is not an integer in 1..{n_ports}")
        else:
            ports.append(item)
    if len(set(ports)) != len(ports):
        problems.append(f"{field}: duplicate ports {ports}")
    return ports


def _pairs(value: Any, n_ports: int, problems: list[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        problems.append("pairs: expected a non-empty list of {name, p, n}")
        return []
    out: list[dict[str, Any]] = []
    used: list[int] = []
    for i, pair in enumerate(value):
        if not isinstance(pair, dict):
            problems.append(f"pairs[{i}]: expected an object with name, p, n")
            continue
        name = pair.get("name") or f"pair{i + 1}"
        p = pair.get("p")
        n = pair.get("n")
        ok = True
        for label, port in (("p", p), ("n", n)):
            if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= n_ports:
                problems.append(
                    f"pairs[{i}].{label}: port {port!r} is not an integer in 1..{n_ports}"
                )
                ok = False
        if ok and p == n:
            problems.append(f"pairs[{i}]: p and n are the same port {p}")
            ok = False
        if ok:
            used.extend([p, n])
            out.append({"name": str(name), "p": p, "n": n})
    if len(set(used)) != len(used):
        problems.append(f"pairs: a port appears in more than one pair {sorted(used)}")
    return out


def _paths(value: Any, n_ports: int, problems: list[str]) -> list[dict[str, int]]:
    if not isinstance(value, list) or not value:
        problems.append("paths: expected a non-empty list of {from, to}")
        return []
    out: list[dict[str, int]] = []
    for i, path in enumerate(value):
        if not isinstance(path, dict):
            problems.append(f"paths[{i}]: expected an object with from, to")
            continue
        src = path.get("from")
        dst = path.get("to")
        ok = True
        for label, port in (("from", src), ("to", dst)):
            if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= n_ports:
                problems.append(
                    f"paths[{i}].{label}: port {port!r} is not an integer in 1..{n_ports}"
                )
                ok = False
        if ok and src == dst:
            problems.append(f"paths[{i}]: from and to are the same port {src}")
            ok = False
        if ok:
            out.append({"from": src, "to": dst})
    return out


def normalize(raw: Any, n_ports: int) -> dict[str, Any]:
    """Return a normalized interpretation or raise interpretation_invalid listing every problem."""
    problems: list[str] = []
    if not isinstance(raw, dict):
        raise WorkerError("interpretation_invalid", "interpretation must be an object")
    device = raw.get("device")
    if device not in DEVICES:
        problems.append(f"device: expected one of {list(DEVICES)}, got {device!r}")
        raise WorkerError("interpretation_invalid", "; ".join(problems))

    out: dict[str, Any] = {"device": device}
    mixed = raw.get("input_is_mixed_mode", False)
    if not isinstance(mixed, bool):
        problems.append("input_is_mixed_mode: expected true or false")
        mixed = False
    out["input_is_mixed_mode"] = mixed

    if device in ("inductor", "capacitor"):
        mode = raw.get("terminal_mode")
        if mode not in LUMPED_MODES:
            problems.append(f"terminal_mode: expected one of {list(LUMPED_MODES)}, got {mode!r}")
        elif mode == "one_port" and n_ports < 1:
            problems.append("terminal_mode one_port needs at least one port")
        elif mode != "one_port" and n_ports != 2:
            problems.append(f"terminal_mode {mode} needs a 2-port file, this file has {n_ports}")
        out["terminal_mode"] = mode
    elif device == "transmission_line":
        topology = raw.get("topology", "single_ended_paths")
        if topology not in TOPOLOGIES:
            problems.append(f"topology: expected one of {list(TOPOLOGIES)}, got {topology!r}")
            topology = "single_ended_paths"
        out["topology"] = topology
        convention = raw.get("through_convention")
        if n_ports not in (2, 4):
            problems.append(
                f"transmission_line analysis needs a 2- or 4-port file, this file has {n_ports}"
            )
        if convention is not None and convention not in mixed_mode.CONVENTIONS:
            problems.append(
                f"through_convention: expected one of {list(mixed_mode.CONVENTIONS)}, "
                f"got {convention!r}"
            )
            convention = None
        if n_ports == 2:
            out["ports"] = {"in": [1], "out": [2]}
        elif topology == "mixed_mode_already" or mixed:
            # Stored as [d_in, d_out, c_in, c_out]; the analysis splits it without converting.
            out["ports"] = {"in": [1], "out": [2]}
            out["input_is_mixed_mode"] = True
        elif convention in ("odd_even", "half_split") and n_ports == 4:
            preset = mixed_mode.preset_mapping(convention, n_ports)
            out["through_convention"] = convention
            out["ports"] = preset["ports"]
            if topology == "differential_pairs":
                out["pairs"] = preset["pairs"]
        else:
            if convention == "custom":
                out["through_convention"] = "custom"
            ports = raw.get("ports")
            if not isinstance(ports, dict):
                problems.append(
                    "ports: expected {in: [...], out: [...]} "
                    "(or choose through_convention odd_even / half_split)"
                )
            else:
                out["ports"] = {
                    "in": _port_list(ports.get("in"), "ports.in", n_ports, problems),
                    "out": _port_list(ports.get("out"), "ports.out", n_ports, problems),
                }
                if out["ports"]["in"] and out["ports"]["out"]:
                    if len(out["ports"]["in"]) != len(out["ports"]["out"]):
                        problems.append("ports: in and out must have the same length")
                    overlap = set(out["ports"]["in"]) & set(out["ports"]["out"])
                    if overlap:
                        problems.append(f"ports: {sorted(overlap)} listed as both in and out")
            if topology == "differential_pairs":
                out["pairs"] = _pairs(raw.get("pairs"), n_ports, problems)
            elif "pairs" in raw and raw["pairs"] is not None:
                out["pairs"] = _pairs(raw["pairs"], n_ports, problems)
    else:  # interposer
        topology = raw.get("topology")
        if topology not in TOPOLOGIES:
            problems.append(f"topology: expected one of {list(TOPOLOGIES)}, got {topology!r}")
        out["topology"] = topology
        if topology == "differential_pairs":
            out["pairs"] = _pairs(raw.get("pairs"), n_ports, problems)
        if "paths" in raw and raw["paths"] is not None:
            out["paths"] = _paths(raw["paths"], n_ports, problems)
        elif topology == "single_ended_paths":
            problems.append("paths: required for single_ended_paths")
    if mixed and device in ("inductor", "capacitor"):
        problems.append("input_is_mixed_mode is not meaningful for a lumped element")
    if problems:
        raise WorkerError("interpretation_invalid", "; ".join(problems))
    return out
