"""Transmission-line quantities from a 2-port S-parameter network.

Domain owner's equations (positive-dB losses, ABCD-based characteristic impedance):

    IL     = -20 log10 |S_out,in|
    RL_in  = -20 log10 |S_in,in|,   RL_out = -20 log10 |S_out,out|
    Z_c    = ± sqrt(B / C)        (ABCD of the 2-port; no symmetry assumed)

equivalent for a symmetric reciprocal line:
    Z_c = Z_ref * sqrt(((1+S11)^2 - S12 S21) / ((1-S11)^2 - S12 S21))

`select_zc_branch` picks one root per frequency and labels each point
valid | ambiguous | singular. See docs/superpowers/specs/2026-09-07-line-analysis-design.md.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np

Region = Literal["valid", "ambiguous", "singular"]

DEFAULT_SINGULAR_C = 1e-9


def _s(network: Any, row: int, col: int) -> np.ndarray:
    """S[row, col] with 1-based ports."""
    return np.asarray(network.s[:, row - 1, col - 1], dtype=complex)


def _positive_db(values: np.ndarray) -> np.ndarray:
    """-20 log10 |v| with an ideal |v| = 0 reported as inf loss rather than a warning."""
    with np.errstate(divide="ignore"):
        return -20.0 * np.log10(np.abs(values))


def insertion_loss_db(network: Any, in_port: int, out_port: int) -> np.ndarray:
    """Positive insertion loss in dB from `in_port` to `out_port`."""
    return _positive_db(_s(network, out_port, in_port))


def return_loss_db(network: Any, port: int) -> np.ndarray:
    """Positive return loss in dB at `port`; a perfect match gives inf."""
    return _positive_db(_s(network, port, port))


def zc_candidates(network: Any, singular_c: float = DEFAULT_SINGULAR_C) -> np.ndarray:
    """Both roots of sqrt(B/C) per frequency, shape (n, 2); NaN rows where |C| < singular_c."""
    a = np.asarray(network.a, dtype=complex)
    b, c = a[:, 0, 1], a[:, 1, 0]
    safe_c = np.where(np.abs(c) < singular_c, np.nan, c)
    # Dividing by the NaN placeholder is how a singular point becomes NaN; not an error.
    with np.errstate(invalid="ignore", divide="ignore"):
        root = np.sqrt(b / safe_c)
    return np.stack([root, -root], axis=1)
