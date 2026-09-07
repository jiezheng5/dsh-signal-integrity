"""Network-quality diagnostics: passivity, reciprocity, and causality.

Two layers, reported side by side:

* **IEEE P370 quality metrics** from scikit-rf's ``IEEEP370_FD_QM`` (the only
  open-source Python implementation of the standard's frequency-domain
  checks). Each metric is a 0-100 % score with the standard's evaluation
  bands: good / acceptable / inconclusive / poor. These are the verdicts.
* **Exact per-frequency checks** computed here: the worst singular value of
  S and the worst |S_ij - S_ji|, with the frequency where it happens and the
  count of points beyond the configured tolerance. These tell the engineer
  *where* a problem is; the P370 score tells them *how bad* overall.

Causality has no exact per-frequency form on sampled data, so it is reported
from the P370 metric only and always labelled as a screening result.
"""

from __future__ import annotations

from typing import Any

import numpy as np

P370_METHOD = (
    "IEEE P370 frequency-domain quality metrics, scikit-rf IEEEP370_FD_QM.check_se_quality"
)
MAX_LISTED_VIOLATIONS = 10
P370_EVALUATIONS = ("good", "acceptable", "inconclusive", "poor")


def passivity_detail(network: Any, tolerance: float) -> dict[str, Any]:
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


def reciprocity_detail(network: Any, tolerance: float) -> dict[str, Any]:
    """Max |S_ij - S_ji| per frequency; one-ports are not applicable."""
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


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


def p370_metrics(network: Any) -> dict[str, Any]:
    """IEEE P370 PQMi / RQMi / CQMi with the standard's evaluation bands.

    Not applicable to one-ports: scikit-rf's implementation needs
    off-diagonal terms for every metric.
    """
    from skrf.calibration.deembedding import IEEEP370_FD_QM

    qm = IEEEP370_FD_QM()
    if network.nports < 2:
        # scikit-rf's P370 metrics need off-diagonal terms; the exact per-frequency
        # passivity check still covers one-ports.
        na = {"score_percent": None, "evaluation": "not_applicable", "note": "one-port"}
        return {"method": P370_METHOD, "passivity": na, "reciprocity": na, "causality": na}
    try:
        raw = qm.check_se_quality(network)
    except Exception as exc:  # degenerate data can break the vector products
        return {
            "method": P370_METHOD,
            "error": f"{type(exc).__name__}: {exc}",
            "passivity": {"score_percent": None, "evaluation": "inconclusive"},
            "reciprocity": {"score_percent": None, "evaluation": "inconclusive"},
            "causality": {"score_percent": None, "evaluation": "inconclusive"},
        }
    out: dict[str, Any] = {"method": P370_METHOD}
    for key in ("passivity", "reciprocity", "causality"):
        entry = raw.get(key, {})
        score = _finite(entry.get("value"))
        evaluation = str(entry.get("evaluation") or "inconclusive")
        if evaluation not in P370_EVALUATIONS:
            evaluation = "inconclusive"
        out[key] = {"score_percent": score, "evaluation": evaluation}
    return out


def _evaluate_passivity(score: float | None) -> str:
    """scikit-rf's P370 passivity bands (kept here so the bands are testable)."""
    if score is None:
        return "inconclusive"
    if score <= 80.0:
        return "poor"
    if score <= 99.0:
        return "inconclusive"
    if score <= 99.9:
        return "acceptable"
    return "good"


def run_all(network: Any, tolerances: dict[str, Any]) -> dict[str, Any]:
    p370 = p370_metrics(network)
    passivity = passivity_detail(network, float(tolerances.get("passivity", 1e-6)))
    reciprocity = reciprocity_detail(network, float(tolerances.get("reciprocity", 1e-6)))
    return {
        "passivity": {**passivity, "p370": p370["passivity"]},
        "reciprocity": {**reciprocity, "p370": p370["reciprocity"]},
        "causality": {
            "applicable": network.nports >= 2,
            "score_percent": p370["causality"]["score_percent"],
            "verdict": p370["causality"]["evaluation"],
            "note": "IEEE P370 initial causality metric: screening only, not a proof of causality; "
            "sensitive to frequency sampling",
            "method": P370_METHOD,
            "p370": p370["causality"],
        },
        "p370_method": p370["method"],
        **({"p370_error": p370["error"]} if "error" in p370 else {}),
    }
