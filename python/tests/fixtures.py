"""Synthetic networks with known properties, written as Touchstone files."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import skrf as rf

C0 = 299_792_458.0


def frequency(start_ghz: float = 0.01, stop_ghz: float = 20.0, npoints: int = 401) -> rf.Frequency:
    return rf.Frequency(start_ghz, stop_ghz, npoints, "ghz")


def lossy_line(
    length_mm: float = 20.0,
    z0: float = 50.0,
    eps_r: float = 4.0,
    alpha_db_per_m_at_1ghz: float = 5.0,
    freq: rf.Frequency | None = None,
) -> rf.Network:
    """Uniform lossy line with sqrt(f) conductor-like loss; causal, passive, reciprocal."""
    f = freq or frequency()
    beta = f.w * np.sqrt(eps_r) / C0
    alpha_np = alpha_db_per_m_at_1ghz / 8.686 * np.sqrt(f.f / 1e9)
    media = rf.media.DefinedGammaZ0(f, z0=z0, gamma=alpha_np + 1j * beta)
    ntwk = media.line(length_mm, unit="mm", name="lossy_line")
    return ntwk


def advanced_line(**kwargs) -> rf.Network:
    """Time-reversed line: anti-causal (phase advances with frequency)."""
    ntwk = lossy_line(**kwargs)
    adv = ntwk.copy()
    adv.s = np.conj(ntwk.s)
    adv.name = "advanced_line"
    return adv


def active_line(gain: float = 1.5, **kwargs) -> rf.Network:
    ntwk = lossy_line(**kwargs)
    act = ntwk.copy()
    act.s = ntwk.s * gain
    act.name = "active_line"
    return act


def nonreciprocal_line(**kwargs) -> rf.Network:
    """Isolator-like: S12 = 0 while S21 keeps the line response."""
    ntwk = lossy_line(**kwargs)
    nr = ntwk.copy()
    nr.s[:, 0, 1] = 0.0
    nr.name = "nonreciprocal_line"
    return nr


def two_uncoupled_lines(freq: rf.Frequency | None = None, **kwargs) -> rf.Network:
    """4-port made of two identical uncoupled lines: ports 1->3 and 2->4."""
    line = lossy_line(freq=freq, **kwargs)
    n = line.s.shape[0]
    s = np.zeros((n, 4, 4), dtype=complex)
    for a, b in ((0, 2), (1, 3)):
        s[:, a, a] = line.s[:, 0, 0]
        s[:, b, b] = line.s[:, 1, 1]
        s[:, a, b] = line.s[:, 0, 1]
        s[:, b, a] = line.s[:, 1, 0]
    return rf.Network(frequency=line.frequency, s=s, z0=50.0, name="two_lines")


def series_rlc_oneport(
    r_ohm: float = 0.5, l_nh: float = 10.0, c_pf: float = 1.0, freq: rf.Frequency | None = None
) -> rf.Network:
    """One-port series R + L + C to ground: capacitive below SRF, inductive above."""
    f = freq or frequency()
    z = r_ohm + 1j * (f.w * l_nh * 1e-9 - 1 / (f.w * c_pf * 1e-12))
    s = ((z - 50.0) / (z + 50.0)).reshape(-1, 1, 1)
    return rf.Network(frequency=f, s=s, z0=50.0, name="series_rlc")


def series_rl_oneport(
    r_ohm: float = 1.0, l_nh: float = 10.0, freq: rf.Frequency | None = None
) -> rf.Network:
    """One-port series R + L to ground: Z = R + jwL."""
    f = freq or frequency()
    z = r_ohm + 1j * f.w * l_nh * 1e-9
    s = ((z - 50.0) / (z + 50.0)).reshape(-1, 1, 1)
    return rf.Network(frequency=f, s=s, z0=50.0, name="series_rl")


def write(ntwk: rf.Network, directory: Path, stem: str, form: str = "ri") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    ntwk.write_touchstone(str(directory / stem), form=form)
    return directory / f"{stem}.s{ntwk.nports}p"
