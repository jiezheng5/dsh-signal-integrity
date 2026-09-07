"""Touchstone loading: file identity, header metadata, and structural checks.

Everything the agent needs to reason about a file before any physics runs
comes from here: how many ports, which frequency span, which reference
impedance, and whether the header hints that the data is already mixed-mode.
"""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Any

import numpy as np

from .protocol import WorkerError

TOUCHSTONE_SUFFIX = re.compile(r"^\.(s\d+p|ts)$", re.IGNORECASE)
MIXED_MODE_HINT = re.compile(
    r"\b(mixed[- ]?mode|differential|common[- ]?mode|\bMM\b|Sdd|Scc|Sdc|Scd)\b", re.IGNORECASE
)
MIN_FREQUENCY_POINTS = 2
COMMENT_LIMIT = 2000


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_path(raw: Any) -> Path:
    if not isinstance(raw, str) or raw.strip() == "":
        raise WorkerError("bad_request", "payload.path must be a non-empty string")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        raise WorkerError("bad_request", f"path must be absolute, got {raw!r}")
    if not path.exists():
        raise WorkerError("file_not_found", f"no such file: {path}")
    if not path.is_file():
        raise WorkerError("file_not_found", f"not a regular file: {path}")
    if TOUCHSTONE_SUFFIX.match(path.suffix) is None:
        raise WorkerError(
            "unsupported_format",
            f"{path.name}: expected a Touchstone file (.sNp or .ts), got suffix {path.suffix!r}",
        )
    return path


def _complex_list(values: np.ndarray) -> list[dict[str, float]]:
    return [{"re": float(np.real(v)), "im": float(np.imag(v))} for v in values]


def load(path: Path) -> tuple[Any, dict[str, Any], list[str]]:
    """Parse a Touchstone file.

    Returns the scikit-rf Network, a JSON-ready metadata dict, and a list of
    human-readable warnings about the data (not about the device).
    """
    import skrf as rf

    warnings: list[str] = []
    try:
        header = rf.io.touchstone.Touchstone(str(path))
    except Exception as exc:  # scikit-rf raises a mix of ValueError/IndexError/etc.
        raise WorkerError(
            "parse_error",
            f"{path.name}: cannot parse Touchstone header/data",
            f"{type(exc).__name__}: {exc}",
        ) from exc
    try:
        network = rf.Network(str(path))
    except Exception as exc:
        raise WorkerError(
            "parse_error",
            f"{path.name}: scikit-rf could not build a network",
            f"{type(exc).__name__}: {exc}",
        ) from exc

    n_ports = int(network.nports)
    freq_hz = np.asarray(network.frequency.f, dtype=float)
    n_freq = int(freq_hz.size)
    if n_freq < MIN_FREQUENCY_POINTS:
        raise WorkerError(
            "parse_error",
            f"{path.name}: only {n_freq} frequency point(s); need at least {MIN_FREQUENCY_POINTS}",
        )
    if np.any(np.diff(freq_hz) <= 0):
        raise WorkerError("parse_error", f"{path.name}: frequency axis is not strictly increasing")
    if not np.all(np.isfinite(network.s)):
        raise WorkerError(
            "parse_error", f"{path.name}: S-parameter data contains NaN or infinite values"
        )

    parameter = str(getattr(header, "parameter", "s") or "s").lower()
    if parameter != "s":
        warnings.append(
            f"file stores {parameter.upper()}-parameters; scikit-rf converted them to S for analysis"
        )

    z0 = np.asarray(network.z0)
    z0_first = z0[0]
    if not np.allclose(z0, z0_first[None, :]):
        warnings.append(
            "reference impedance varies with frequency; the first-frequency values are reported"
        )
    if np.any(np.abs(np.imag(z0_first)) > 0):
        warnings.append(
            "reference impedance is complex; passivity is evaluated on the stored power-wave S matrix as-is"
        )
    if not np.allclose(z0_first, z0_first[0]):
        warnings.append("reference impedance differs between ports")

    comments = str(getattr(header, "comments", "") or "")
    port_names = getattr(network, "port_names", None)
    port_names_list = [str(name) for name in port_names] if port_names else None
    hint_sources = comments + " " + " ".join(port_names_list or [])
    mixed_mode_hint = MIXED_MODE_HINT.search(hint_sources) is not None
    if mixed_mode_hint:
        warnings.append(
            "header comments or port names mention mixed-mode terms; confirm whether the data is already mixed-mode before any conversion"
        )
    if freq_hz[0] == 0.0:
        warnings.append(
            "data starts at DC; extraction formulas dividing by frequency skip the first point"
        )

    metadata: dict[str, Any] = {
        "file_name": path.name,
        "n_ports": n_ports,
        "n_freq": n_freq,
        "f_min_hz": float(freq_hz[0]),
        "f_max_hz": float(freq_hz[-1]),
        "frequency_unit": str(getattr(header, "frequency_unit", "hz") or "hz").lower(),
        "parameter": parameter,
        "format": str(getattr(header, "format", "") or "").lower(),
        "touchstone_version": str(getattr(header, "version", "") or ""),
        "reference_impedance": _complex_list(z0_first),
        "port_names": port_names_list,
        "comments": comments[:COMMENT_LIMIT],
        "mixed_mode_hint": mixed_mode_hint,
        "size_bytes": int(path.stat().st_size),
    }
    if not all(math.isfinite(v) for v in (metadata["f_min_hz"], metadata["f_max_hz"])):
        raise WorkerError("parse_error", f"{path.name}: non-finite frequency values")
    return network, metadata, warnings
