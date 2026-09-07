"""Lumped-element extraction: inductor L and Q, capacitor C, from S-parameters.

This module is the domain owner's: the equations below are the ones the
report will carry, so they are written and reviewed by an RF engineer rather
than generated. tests/test_lumped.py checks every function against closed-form
fixtures. Sign convention: a series capacitor has Im(Z) < 0, so C = -1/(omega*Im(Z));
the sign is folded into the formulas below and any point with the wrong sign
becomes NaN rather than a negative component value.


## T and Pi Circuits for Extracting R, L, C from s2p.
T-circuit:

Port 1 --[ Z11 - Z12 ]--+--[ Z22 - Z12 ]-- Port 2
                        |
                      [ Z12 ]
                        |
Ground ----------------+------------------- Ground

Pi-circuit:

Port 1 ------------[ -Y12 ]------------ Port 2
        |                               |
   [ Y11 + Y12 ]                   [ Y22 + Y21 ]
        |                               |
Ground -+-------------------------------+- Ground

## Common Equation to extract R, L, C from s2p
S, Y, Z, ABCD matrix all have ready to use libraries to convert between each other. The following equations are based on the assumption that the s2p file is a 2-port network.

```json
assumption: microstrip or stripline
z_ref = 50
nominator = (1 + S11) * (1 + S11) - S12 * S21
denominator = (1 - S11) * (1 - S11) - S12 * S21
zc = z_ref * sqrt(nominator / denominator)

assumption: series RL circuit
zse = 1 / Y11
L = 1 / (2 * pi * f) * Im(zse)
Q = Im(zse) / Re(zse)

assumption: differential inductor
zdiff = z11 - z12 - z21 + z22
L = Im(zdiff) / (2 * pi * f)
Q = Im(zdiff) / Re(zdiff)

assumption: parallel RC circuit
zse = 1 / Y11
C = 1 / (2 * pi * f * Im(zse) )

assumption: series RC circuit
C = Im(Y11) / (2 * pi * f)
```



"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np

TerminalMode = Literal[
    "one_port", "two_terminal_differential", "through_port2_grounded", "through_port2_open"
]
Region = Literal["valid", "near_srf", "beyond_srf", "wrong_sign", "dc"]

# A point counts as "near" self-resonance when it lies within this fraction of f_srf.
NEAR_SRF_FRACTION = 0.1


def impedance_from_network(network: Any, terminal_mode: TerminalMode) -> np.ndarray:
    """Complex impedance Z(f) of the element under the chosen terminal interpretation.

    one_port                  Z11: element from port 1 to ground.
    two_terminal_differential Z11 + Z22 - Z12 - Z21: element floating between the ports
                              (the two series arms of the T-circuit; a shunt leg cancels).
    through_port2_grounded    1/Y11: element in a through fixture with port 2 grounded in use.
                              In the Pi-circuit this is the series arm in parallel with the
                              port-1 shunt leg; the port-2 leg is shorted out.
    through_port2_open        1/(Y11 + Y12): element in a through fixture with port 2 open in
                              use. In the Pi-circuit Y11 + Y12 = Yp1, the port-1 shunt leg
                              alone, so the through arm is treated as fixture, not device.
    -1/Y12 (the series arm alone) is deliberately not offered: it drops both shunt legs,
    which is only right when port-to-ground coupling is negligible.
    """
    if terminal_mode == "one_port":
        return np.asarray(network.z[:, 0, 0], dtype=complex)
    if terminal_mode == "two_terminal_differential":
        z = np.asarray(network.z, dtype=complex)
        return z[:, 0, 0] + z[:, 1, 1] - z[:, 0, 1] - z[:, 1, 0]
    if terminal_mode == "through_port2_grounded":
        return 1.0 / np.asarray(network.y[:, 0, 0], dtype=complex)
    if terminal_mode == "through_port2_open":
        y = np.asarray(network.y, dtype=complex)
        return 1.0 / (y[:, 0, 0] + y[:, 0, 1])
    raise ValueError(f"unknown terminal_mode {terminal_mode!r}")


def _omega(freq_hz: np.ndarray) -> np.ndarray:
    """2*pi*f with NaN at f <= 0 so that dividing by it never raises and marks DC as undefined."""
    f = np.asarray(freq_hz, dtype=float)
    return np.where(f > 0, 2.0 * np.pi * f, np.nan)


def inductor_lq(z: np.ndarray, freq_hz: np.ndarray) -> dict[str, np.ndarray]:
    """Series inductance, quality factor, and series resistance versus frequency.

    L = Im(Z)/omega, Q = Im(Z)/Re(Z), R = Re(Z). L and Q are NaN at DC and Q is NaN
    where Re(Z) = 0 (an ideal lossless element has no finite Q).
    """
    z = np.asarray(z, dtype=complex)
    omega = _omega(freq_hz)
    re, im = z.real, z.imag
    with np.errstate(divide="ignore", invalid="ignore"):
        l_h = im / omega
        q = np.where(re != 0, im / np.where(re != 0, re, np.nan), np.nan)
        q = np.where(np.isnan(omega), np.nan, q)
    return {"L_h": l_h, "Q": q, "R_ohm": re.copy()}


def capacitor_c(z: np.ndarray, freq_hz: np.ndarray) -> dict[str, np.ndarray]:
    """Series capacitance and ESR versus frequency.

    C = -1/(omega*Im(Z)) where the reactance is capacitive (Im(Z) < 0); NaN at DC or
    where the reactance is inductive, never a negative capacitance. ESR = Re(Z).
    """
    z = np.asarray(z, dtype=complex)
    omega = _omega(freq_hz)
    im = z.imag
    capacitive = im < 0
    with np.errstate(divide="ignore", invalid="ignore"):
        c_f = np.where(capacitive, -1.0 / (omega * np.where(capacitive, im, np.nan)), np.nan)
    return {"C_f": c_f, "ESR_ohm": z.real.copy()}


def self_resonance_hz(z: np.ndarray, freq_hz: np.ndarray) -> float | None:
    """First frequency above DC where Im(Z) changes sign, linearly interpolated, or None.

    Only the first crossing is returned: it bounds the region where a single-element
    model holds. Later crossings are visible in classify_region as beyond_srf.
    """
    f = np.asarray(freq_hz, dtype=float)
    im = np.asarray(z, dtype=complex).imag
    keep = f > 0
    f, im = f[keep], im[keep]
    if f.size < 2:
        return None
    sign = np.sign(im)
    for k in range(f.size - 1):
        if sign[k] == 0:
            return float(f[k])
        if sign[k] * sign[k + 1] < 0:
            # linear interpolation of the zero between the bracketing points
            frac = im[k] / (im[k] - im[k + 1])
            return float(f[k] + frac * (f[k + 1] - f[k]))
    return None


def classify_region(
    z: np.ndarray, freq_hz: np.ndarray, device: Literal["inductor", "capacitor"]
) -> list[str]:
    """Label each frequency point so plots and reports can mark where extraction is meaningful.

    dc          f <= 0, no reactance to extract
    beyond_srf  above the first self-resonance: the single-element model no longer holds
    near_srf    within NEAR_SRF_FRACTION of the self-resonance, values are steep and unreliable
    wrong_sign  reactance has the wrong sign for the device (inductor expects Im(Z) > 0,
                capacitor Im(Z) < 0)
    valid       everything else
    """
    f = np.asarray(freq_hz, dtype=float)
    im = np.asarray(z, dtype=complex).imag
    expected_positive = device == "inductor"
    srf = self_resonance_hz(z, freq_hz)
    labels: list[str] = []
    for fk, imk in zip(f, im, strict=True):
        if fk <= 0:
            labels.append("dc")
        elif srf is not None and abs(fk - srf) <= NEAR_SRF_FRACTION * srf:
            labels.append("near_srf")
        elif srf is not None and fk > srf:
            labels.append("beyond_srf")
        elif (imk > 0) != expected_positive:
            labels.append("wrong_sign")
        else:
            labels.append("valid")
    return labels
