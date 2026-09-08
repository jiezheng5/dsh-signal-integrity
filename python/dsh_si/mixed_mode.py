"""Port-mapping presets and single-ended to mixed-mode conversion for 4-port lines.

Two industry conventions for a 2N-port differential channel:

    odd_even   through 1->2, 3->4, ...   pairs (1,3), (2,4), ...    (PLTS-style "1-2 through")
    half_split through 1->1+N, ...       pairs (1,2), (3,4), ...

scikit-rf's se2gmm expects the half_split layout: adjacent ports form a pair and port k
connects through to k+2. Any other layout is renumbered into it first. Preset polarity:
the lower-numbered port of each pair is P. Converted reference impedances are 2*Z0
(differential) and Z0/2 (common), and mixed-mode input is never converted twice.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .protocol import WorkerError

CONVENTIONS: tuple[str, ...] = ("odd_even", "half_split", "custom")


def _odd_even_pairs(n_ports: int) -> list[tuple[int, int]]:
    """Pairs for odd_even: the near end is the odd ports (1,3), the far end the even ports (2,4)."""
    odds = list(range(1, n_ports + 1, 2))
    evens = list(range(2, n_ports + 1, 2))
    near = [(odds[k], odds[k + 1]) for k in range(0, len(odds), 2)]
    far = [(evens[k], evens[k + 1]) for k in range(0, len(evens), 2)]
    return near + far


def preset_mapping(convention: str, n_ports: int) -> dict[str, Any]:
    """`ports` and `pairs` implied by a preset, 1-based."""
    if convention not in ("odd_even", "half_split"):
        raise WorkerError(
            "interpretation_invalid",
            f"through_convention: {convention!r} has no preset; use odd_even, half_split, "
            "or custom with explicit ports",
        )
    if n_ports % 2 or n_ports < 4:
        raise WorkerError(
            "interpretation_invalid",
            f"through_convention {convention} needs an even port count of at least 4, "
            f"this file has {n_ports}",
        )
    half = n_ports // 2
    if convention == "odd_even":
        ins = list(range(1, n_ports + 1, 2))
        outs = list(range(2, n_ports + 1, 2))
        pairs = _odd_even_pairs(n_ports)
    else:
        ins = list(range(1, half + 1))
        outs = list(range(half + 1, n_ports + 1))
        pairs = [(1 + 2 * k, 2 + 2 * k) for k in range(half)]
    return {
        "ports": {"in": ins, "out": outs},
        "pairs": [{"name": f"pair{k + 1}", "p": p, "n": n} for k, (p, n) in enumerate(pairs)],
    }


def to_mixed_mode(network: Any, pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert a 4-port single-ended network into differential and common-mode 2-ports.

    `pairs` is [{p, n}, {p, n}] in 1-based ports; the first pair is the input end.
    Returns {"dd", "cc"} as 2-ports with ports [in, out] plus {"mixed"}, the full
    mixed-mode 4-port [d_in, d_out, c_in, c_out].
    """
    if network.nports != 4 or len(pairs) != 2:
        raise WorkerError(
            "interpretation_invalid",
            "differential line analysis needs a 4-port file and exactly 2 pairs "
            f"(got {network.nports} ports, {len(pairs)} pairs)",
        )
    order = [pairs[0]["p"] - 1, pairs[0]["n"] - 1, pairs[1]["p"] - 1, pairs[1]["n"] - 1]
    mixed = network.copy()
    # renumber(from, to): the port currently at from[k] is moved to position to[k].
    mixed.renumber(order, [0, 1, 2, 3])
    try:
        mixed.se2gmm(p=2)
    except Exception as exc:  # scikit-rf raises plain exceptions for degenerate z0
        raise WorkerError("numerical_error", f"mixed-mode conversion failed: {exc}") from exc
    return split_mixed_mode_file(mixed) | {"mixed": mixed}


def split_mixed_mode_file(mixed: Any) -> dict[str, Any]:
    """Differential and common 2-ports from a mixed-mode 4-port [d_in, d_out, c_in, c_out]."""
    if mixed.nports != 4:
        raise WorkerError(
            "interpretation_invalid",
            f"a mixed-mode line file must have 4 ports, this one has {mixed.nports}",
        )
    dd = mixed.subnetwork([0, 1])
    cc = mixed.subnetwork([2, 3])
    dd.name, cc.name = "differential", "common"
    return {"dd": dd, "cc": cc}


# Points used to extrapolate the through phase to DC, and the |Sdd21| floor below which
# there is no through path to judge.
POLARITY_FIT_POINTS = 11
POLARITY_MIN_THROUGH = 1e-3


def polarity_check(dd: Any) -> str | None:
    """Warn when the differential through response looks inverted (P and N swapped at one end).

    Every quantity this plugin reports for a line (IL, RL, Z_c) is invariant under a P/N
    swap, so a wrong polarity guess cannot corrupt them. It does invert the sign of the
    differential through response, which matters to anyone who later takes phase, group
    delay, or a time-domain step from the same file. A physical passive through has
    Sdd21 -> +1 at DC, so unwrapping the measured phase and extrapolating to zero
    frequency gives about 0 degrees for the assumed polarity and about 180 for a swap.

    Returns the warning text, or None when polarity looks right or cannot be judged.
    """
    s21 = np.asarray(dd.s[:, 1, 0], dtype=complex)
    freq = np.asarray(dd.frequency.f, dtype=float)
    n = min(POLARITY_FIT_POINTS, s21.size)
    if n < 3 or np.abs(s21[:n]).min() < POLARITY_MIN_THROUGH:
        return None
    phase = np.unwrap(np.angle(s21[:n]))
    # Straight-line fit of the low-frequency phase; its intercept is the DC phase.
    intercept = float(np.polyfit(freq[:n], phase, 1)[1])
    dc_degrees = float(np.degrees(np.angle(np.exp(1j * intercept))))
    if abs(dc_degrees) <= 90.0:
        return None
    return (
        f"polarity: the differential through response extrapolates to {dc_degrees:.0f} degrees at DC "
        "rather than 0, which usually means P and N are swapped at one end. IL, RL and Z_c are "
        "unaffected; the phase sign is not. Set the pairs explicitly with "
        "through_convention custom if the assumed polarity is wrong."
    )
