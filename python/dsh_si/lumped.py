"""Lumped-element extraction: inductor L and Q, capacitor C, from S-parameters.

This module is the domain owner's: the equations below are the ones the
report will carry, so they are written and reviewed by an RF engineer rather
than generated. Each function documents its contract; the accompanying tests
in tests/test_lumped.py are marked strict-xfail until implemented, so CI stays
green now and fails the moment an implementation lands without the marker
being removed.

Conventions (from docs/plans/dsh-signal-integrity-plan.md):
    L = Im(Z) / omega            series inductance
    Q = Im(Z) / Re(Z)            quality factor
    C = -1 / (omega * Im(Z))     series capacitance
    Z_2T = Z11 + Z22 - Z12 - Z21 two-terminal differential impedance of a 2-port
Positive omega = 2*pi*f; a DC point (f = 0) must be skipped, never divided by.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np

TerminalMode = Literal["one_port", "two_terminal_differential", "through"]


def impedance_from_network(network: Any, terminal_mode: TerminalMode) -> np.ndarray:
    """Complex impedance Z(f) of the element under the chosen terminal interpretation.

    TODO(brittany): implement.
      one_port                  -> Z = network.z[:, 0, 0] (port 1 to ground)
      two_terminal_differential -> Z = Z11 + Z22 - Z12 - Z21 (element floating between ports)
      through                   -> series element in a through fixture; decide whether to
                                   support it here or defer to fixture de-embedding.
    Returns a complex array with one value per frequency point.
    """
    raise NotImplementedError("impedance_from_network: equations pending")


def inductor_lq(z: np.ndarray, freq_hz: np.ndarray) -> dict[str, np.ndarray]:
    """Series inductance, quality factor, and series resistance versus frequency.

    TODO(brittany): implement.
    Returns {"L_h": ..., "Q": ..., "R_ohm": ...}, each a float array aligned with
    freq_hz. Use NaN where the quantity is undefined (e.g. f = 0, Re(Z) = 0).
    """
    raise NotImplementedError("inductor_lq: equations pending")


def capacitor_c(z: np.ndarray, freq_hz: np.ndarray) -> dict[str, np.ndarray]:
    """Series capacitance and ESR versus frequency.

    TODO(brittany): implement.
    Returns {"C_f": ..., "ESR_ohm": ...}. Use NaN where Im(Z) >= 0 (inductive)
    or f = 0 rather than reporting a negative capacitance.
    """
    raise NotImplementedError("capacitor_c: equations pending")


def self_resonance_hz(z: np.ndarray, freq_hz: np.ndarray) -> float | None:
    """First frequency where Im(Z) changes sign (series self-resonance), or None.

    TODO(brittany): implement (linear interpolation between the bracketing
    points is enough; decide how to treat multiple crossings).
    """
    raise NotImplementedError("self_resonance_hz: pending")


def classify_region(
    z: np.ndarray, freq_hz: np.ndarray, device: Literal["inductor", "capacitor"]
) -> list[str]:
    """Label each frequency point so plots and reports can mark where extraction is meaningful.

    TODO(brittany): decide the labels and their rules. Suggested vocabulary:
      "valid"              extraction physically meaningful
      "near_srf"           within some band of the self-resonance
      "beyond_srf"         above self-resonance, sign of reactance flipped
      "wrong_sign"         reactance has the wrong sign for the device at this point
      "dc"                 f = 0, skipped
    Returns one label per frequency point.
    """
    raise NotImplementedError("classify_region: policy pending")
