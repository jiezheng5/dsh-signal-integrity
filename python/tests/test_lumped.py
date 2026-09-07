"""Analytic checks for lumped extraction against closed-form fixtures."""

import numpy as np
import pytest

from dsh_si import lumped

from . import fixtures


def test_one_port_series_rl_recovers_l_and_q():
    f = fixtures.frequency(0.1, 5.0, 50)
    ntwk = fixtures.series_rl_oneport(r_ohm=1.0, l_nh=10.0, freq=f)
    z = lumped.impedance_from_network(ntwk, "one_port")
    out = lumped.inductor_lq(z, f.f)
    assert out["L_h"] == pytest.approx(np.full(50, 10e-9), rel=1e-6)
    assert out["R_ohm"] == pytest.approx(np.full(50, 1.0), rel=1e-6)
    assert out["Q"] == pytest.approx(f.w * 10e-9 / 1.0, rel=1e-6)


def test_two_terminal_differential_recovers_series_arm_of_t_circuit():
    f = fixtures.frequency(0.1, 5.0, 20)
    import skrf as rf

    # T-circuit: element Z_el in the port-1 arm, shunt leg Z_sh, nothing in the port-2 arm.
    # Z11 = Z_el + Z_sh, Z22 = Z_sh, Z12 = Z21 = Z_sh, so Z11 + Z22 - Z12 - Z21 = Z_el exactly.
    z_el = 1.0 + 1j * f.w * 10e-9
    z_sh = 1 / (1j * f.w * 0.5e-12)
    zmat = np.empty((f.npoints, 2, 2), dtype=complex)
    zmat[:, 0, 0] = z_el + z_sh
    zmat[:, 1, 1] = z_sh
    zmat[:, 0, 1] = zmat[:, 1, 0] = z_sh
    two_port = rf.Network(frequency=f, z=zmat, z0=50.0)
    z = lumped.impedance_from_network(two_port, "two_terminal_differential")
    assert z == pytest.approx(z_el, rel=1e-6)


def test_capacitor_recovers_c():
    f = fixtures.frequency(0.1, 5.0, 20)
    c = 2e-12
    z = 0.2 + 1 / (1j * f.w * c)
    out = lumped.capacitor_c(z, f.f)
    assert out["C_f"] == pytest.approx(np.full(20, c), rel=1e-6)
    assert out["ESR_ohm"] == pytest.approx(np.full(20, 0.2), rel=1e-6)


def test_capacitor_reports_nan_when_inductive():
    f = fixtures.frequency(0.1, 5.0, 5)
    z = 0.2 + 1j * f.w * 1e-9  # inductive reactance: no valid series C
    out = lumped.capacitor_c(z, f.f)
    assert np.all(np.isnan(out["C_f"]))


def test_self_resonance_of_series_rlc():
    f = fixtures.frequency(0.1, 10.0, 991)
    ind, cap = 10e-9, 1e-12  # f_srf = 1/(2*pi*sqrt(LC)) ~ 1.5915 GHz
    z = 0.5 + 1j * (f.w * ind - 1 / (f.w * cap))
    assert lumped.self_resonance_hz(z, f.f) == pytest.approx(
        1 / (2 * np.pi * np.sqrt(ind * cap)), rel=2e-3
    )


def test_classify_region_marks_beyond_srf():
    f = fixtures.frequency(0.1, 10.0, 100)
    ind, cap = 10e-9, 1e-12
    z = 0.5 + 1j * (f.w * ind - 1 / (f.w * cap))
    labels = lumped.classify_region(z, f.f, "inductor")
    assert len(labels) == 100
    assert labels[0] != "valid"  # below SRF the reactance is capacitive for this series RLC
    assert "beyond_srf" in labels or "wrong_sign" in labels


def _pi_circuit(f, y_series, y_shunt1, y_shunt2):
    """2-port from Pi-circuit legs: Y11 = Yp1 + Ys, Y22 = Yp2 + Ys, Y12 = Y21 = -Ys."""
    import skrf as rf

    ymat = np.empty((f.npoints, 2, 2), dtype=complex)
    ymat[:, 0, 0] = y_shunt1 + y_series
    ymat[:, 1, 1] = y_shunt2 + y_series
    ymat[:, 0, 1] = ymat[:, 1, 0] = -y_series
    return rf.Network(frequency=f, y=ymat, z0=50.0)


def test_through_port2_grounded_is_one_over_y11():
    f = fixtures.frequency(0.1, 5.0, 20)
    y_series = 1 / (1.0 + 1j * f.w * 10e-9)
    y_shunt1 = 1j * f.w * 0.3e-12
    y_shunt2 = 1j * f.w * 0.7e-12
    two_port = _pi_circuit(f, y_series, y_shunt1, y_shunt2)
    z = lumped.impedance_from_network(two_port, "through_port2_grounded")
    # port 2 shorted: series arm in parallel with the port-1 shunt leg; port-2 leg shorted out
    assert z == pytest.approx(1 / (y_shunt1 + y_series), rel=1e-6)


def test_through_port2_open_is_one_over_y11_plus_y12():
    f = fixtures.frequency(0.1, 5.0, 20)
    y_series = 1 / (1.0 + 1j * f.w * 10e-9)
    y_shunt1 = 1j * f.w * 0.3e-12
    y_shunt2 = 1j * f.w * 0.7e-12
    two_port = _pi_circuit(f, y_series, y_shunt1, y_shunt2)
    z = lumped.impedance_from_network(two_port, "through_port2_open")
    # Y11 + Y12 = Yp1: the port-1 shunt leg alone
    assert z == pytest.approx(1 / y_shunt1, rel=1e-6)


def test_unknown_terminal_mode_raises():
    f = fixtures.frequency(0.1, 5.0, 3)
    ntwk = fixtures.series_rl_oneport(freq=f)
    with pytest.raises(ValueError):
        lumped.impedance_from_network(ntwk, "through")


def test_inductor_reports_nan_at_dc():
    f = np.array([0.0, 1e9])
    z = np.array([1.0 + 0j, 1.0 + 1j * 2 * np.pi * 1e9 * 10e-9])
    out = lumped.inductor_lq(z, f)
    assert np.isnan(out["L_h"][0]) and np.isnan(out["Q"][0])
    assert out["L_h"][1] == pytest.approx(10e-9)
    assert out["R_ohm"][0] == pytest.approx(1.0)


def test_self_resonance_none_without_crossing():
    f = fixtures.frequency(0.1, 5.0, 20)
    z = 1.0 + 1j * f.w * 10e-9
    assert lumped.self_resonance_hz(z, f.f) is None


def test_classify_region_all_valid_for_ideal_inductor():
    f = fixtures.frequency(0.1, 5.0, 20)
    z = 1.0 + 1j * f.w * 10e-9
    assert lumped.classify_region(z, f.f, "inductor") == ["valid"] * 20


def test_classify_region_marks_dc_and_wrong_sign_for_capacitor():
    f = np.array([0.0, 1e9, 2e9])
    z = np.array([1e6 + 0j, 1.0 - 1j * 100.0, 1.0 + 1j * 5.0])
    labels = lumped.classify_region(z, f, "capacitor")
    assert labels[0] == "dc" and labels[1] == "valid" and labels[2] != "valid"
