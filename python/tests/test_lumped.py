"""Analytic checks for lumped extraction. Strict-xfail until dsh_si/lumped.py is implemented:
remove the marker on each test as its function lands."""

import numpy as np
import pytest

from dsh_si import lumped

from . import fixtures

PENDING = pytest.mark.xfail(
    strict=True, raises=NotImplementedError, reason="TODO(brittany): lumped.py"
)


@PENDING
def test_one_port_series_rl_recovers_l_and_q():
    f = fixtures.frequency(0.1, 5.0, 50)
    ntwk = fixtures.series_rl_oneport(r_ohm=1.0, l_nh=10.0, freq=f)
    z = lumped.impedance_from_network(ntwk, "one_port")
    out = lumped.inductor_lq(z, f.f)
    assert out["L_h"] == pytest.approx(np.full(50, 10e-9), rel=1e-6)
    assert out["R_ohm"] == pytest.approx(np.full(50, 1.0), rel=1e-6)
    assert out["Q"] == pytest.approx(f.w * 10e-9 / 1.0, rel=1e-6)


@PENDING
def test_two_terminal_differential_matches_one_port_for_floating_element():
    f = fixtures.frequency(0.1, 5.0, 20)
    import skrf as rf

    # Series element floating between port 1 and port 2: Z11+Z22-Z12-Z21 must equal Z_element.
    z_elem = 1.0 + 1j * f.w * 10e-9
    media = rf.media.DefinedGammaZ0(f, z0=50)
    two_port = media.resistor(1.0) ** media.inductor(10e-9)
    z = lumped.impedance_from_network(two_port, "two_terminal_differential")
    assert z == pytest.approx(z_elem, rel=1e-6)


@PENDING
def test_capacitor_recovers_c():
    f = fixtures.frequency(0.1, 5.0, 20)
    c = 2e-12
    z = 0.2 + 1 / (1j * f.w * c)
    out = lumped.capacitor_c(z, f.f)
    assert out["C_f"] == pytest.approx(np.full(20, c), rel=1e-6)
    assert out["ESR_ohm"] == pytest.approx(np.full(20, 0.2), rel=1e-6)


@PENDING
def test_capacitor_reports_nan_when_inductive():
    f = fixtures.frequency(0.1, 5.0, 5)
    z = 0.2 + 1j * f.w * 1e-9  # inductive reactance: no valid series C
    out = lumped.capacitor_c(z, f.f)
    assert np.all(np.isnan(out["C_f"]))


@PENDING
def test_self_resonance_of_series_rlc():
    f = fixtures.frequency(0.1, 10.0, 991)
    l, c = 10e-9, 1e-12  # f_srf = 1/(2*pi*sqrt(LC)) ~ 1.5915 GHz
    z = 0.5 + 1j * (f.w * l - 1 / (f.w * c))
    assert lumped.self_resonance_hz(z, f.f) == pytest.approx(
        1 / (2 * np.pi * np.sqrt(l * c)), rel=2e-3
    )


@PENDING
def test_classify_region_marks_beyond_srf():
    f = fixtures.frequency(0.1, 10.0, 100)
    l, c = 10e-9, 1e-12
    z = 0.5 + 1j * (f.w * l - 1 / (f.w * c))
    labels = lumped.classify_region(z, f.f, "inductor")
    assert len(labels) == 100
    assert labels[0] != "valid"  # below SRF the reactance is capacitive for this series RLC
    assert "beyond_srf" in labels or "wrong_sign" in labels
