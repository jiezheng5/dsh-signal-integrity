"""Network-quality diagnostics: passivity, reciprocity, and causality screening.

Passivity and reciprocity are computed directly (they are exact, per-frequency
statements about the matrix). Causality is a *screening* metric borrowed from
scikit-rf's IEEE P370 frequency-domain quality checks; it is reported with its
method name and never presented as a proof.
"""

from __future__ import annotations

from typing import Any

import numpy as np

CAUSALITY_METHOD = (
    "IEEE P370 initial causality quality metric (CQMi), scikit-rf IEEEP370_FD_QM.check_causality"
)
MAX_LISTED_VIOLATIONS = 10


def passivity(network: Any, tolerance: float) -> dict[str, Any]:
    """Largest singular value of S at every frequency; passive iff all <= 1 + tolerance."""
    s = np.asarray(network.s)
    sigma_max = np.linalg.svd(s, compute_uv=False)[:, 0]
    freq = np.asarray(network.frequency.f, dtype=float)
    violating = np.flatnonzero(sigma_max > 1.0 + tolerance)
    worst = int(np.argmax(sigma_max))
    return {
        "passive": bool(violating.size == 0),
        "tolerance": float(tolerance),
        "sigma_max_worst": float(sigma_max[worst]),
        "worst_freq_hz": float(freq[worst]),
        "violation_count": int(violating.size),
        "violation_freqs_hz": [float(freq[i]) for i in violating[:MAX_LISTED_VIOLATIONS]],
        "method": "max singular value of S per frequency (power-normalized as stored)",
    }


def reciprocity(network: Any, tolerance: float) -> dict[str, Any]:
    """Max |S_ij - S_ji| per frequency; one-ports are trivially not applicable."""
    s = np.asarray(network.s)
    freq = np.asarray(network.frequency.f, dtype=float)
    if s.shape[1] < 2:
        return {
            "applicable": False,
            "reciprocal": None,
            "tolerance": float(tolerance),
            "note": "one-port: reciprocity not applicable",
        }
    diff = np.abs(s - np.transpose(s, (0, 2, 1)))
    max_diff = diff.reshape(diff.shape[0], -1).max(axis=1)
    violating = np.flatnonzero(max_diff > tolerance)
    worst = int(np.argmax(max_diff))
    return {
        "applicable": True,
        "reciprocal": bool(violating.size == 0),
        "tolerance": float(tolerance),
        "max_abs_diff_worst": float(max_diff[worst]),
        "worst_freq_hz": float(freq[worst]),
        "violation_count": int(violating.size),
        "violation_freqs_hz": [float(freq[i]) for i in violating[:MAX_LISTED_VIOLATIONS]],
        "method": "max |S_ij - S_ji| per frequency on the stored S matrix",
    }


def causality_verdict(score_percent: float | None, n_freq: int) -> tuple[str, str]:
    """Map the P370 CQMi score to a verdict the agent can relay.

    TODO(brittany): decide the thresholds. CQMi is the percentage of
    frequency steps where consecutive S-parameter vectors rotate clockwise
    (100 = every step consistent with causality, 0 = every step reversed).
    The score is sensitive to frequency sampling, so a low score on coarse
    data may be undersampling rather than non-causality. Suggested shape:

        if score_percent is None or n_freq < <min points>: inconclusive
        elif score_percent >= <pass threshold>: pass
        elif score_percent <= <fail threshold>: fail
        else: inconclusive

    Return (verdict, note) where verdict is one of 'pass', 'fail',
    'inconclusive' and note is one sentence for the report.
    """
    if score_percent is None:
        return "inconclusive", "metric not computed (one-port or degenerate data)"
    return (
        "inconclusive",
        f"CQMi score {score_percent:.1f}% over {n_freq} points; verdict thresholds not yet defined (screening only)",
    )


def causality(network: Any) -> dict[str, Any]:
    """P370 initial causality screening; not applicable to one-ports."""
    n_freq = int(np.asarray(network.frequency.f).size)
    if network.nports < 2:
        verdict, note = causality_verdict(None, n_freq)
        return {
            "applicable": False,
            "score_percent": None,
            "verdict": verdict,
            "note": note,
            "method": CAUSALITY_METHOD,
        }
    from skrf.calibration.deembedding import IEEEP370_FD_QM

    try:
        score = float(IEEEP370_FD_QM().check_causality(network))
    except Exception as exc:  # degenerate data (e.g. all-zero S) can break the vector products
        verdict, note = causality_verdict(None, n_freq)
        return {
            "applicable": True,
            "score_percent": None,
            "verdict": verdict,
            "note": f"{note}: {type(exc).__name__}: {exc}",
            "method": CAUSALITY_METHOD,
        }
    if not np.isfinite(score):
        score_value: float | None = None
    else:
        score_value = score
    verdict, note = causality_verdict(score_value, n_freq)
    return {
        "applicable": True,
        "score_percent": score_value,
        "verdict": verdict,
        "note": note,
        "method": CAUSALITY_METHOD,
    }


def run_all(network: Any, tolerances: dict[str, Any]) -> dict[str, Any]:
    return {
        "passivity": passivity(network, float(tolerances.get("passivity", 1e-6))),
        "reciprocity": reciprocity(network, float(tolerances.get("reciprocity", 1e-6))),
        "causality": causality(network),
    }
