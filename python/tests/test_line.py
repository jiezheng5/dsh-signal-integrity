import numpy as np
import pytest

from dsh_si import line

from . import fixtures


@pytest.fixture(scope="module")
def lossy():
    return fixtures.lossy_line(freq=fixtures.frequency(npoints=101))


def test_insertion_loss_is_positive_db_and_grows_with_frequency(lossy):
    il = line.insertion_loss_db(lossy, in_port=1, out_port=2)
    assert il.shape == (101,)
    assert il[0] == pytest.approx(0.01, abs=2e-3)  # 5 dB/m * 20 mm * sqrt(0.01) at 10 MHz
    assert il[-1] == pytest.approx(5.0 * 0.020 * np.sqrt(20.0), abs=0.05)
    assert np.all(np.diff(il) > 0)


def test_return_loss_is_large_for_matched_line(lossy):
    rl = line.return_loss_db(lossy, port=1)
    assert rl.shape == (101,)
    assert np.all(rl > 40.0)


def test_zc_candidates_are_plus_minus_sqrt_b_over_c(lossy):
    cand = line.zc_candidates(lossy)
    assert cand.shape == (101, 2)
    assert np.allclose(cand[:, 0], -cand[:, 1])
    assert np.allclose(np.abs(cand[:, 0]), 50.0, atol=0.5)


def test_zc_candidates_nan_where_c_is_singular():
    # `network.a` is derived from `s` in scikit-rf, so the singular point is built in ABCD
    # space and converted back with skrf.network.a2s.
    import skrf as rf
    from skrf.network import a2s

    f = fixtures.frequency(0.01, 1.0, 5)
    a = fixtures.lossy_line(freq=f).a.copy()
    a[2, 1, 0] = 0.0
    singular = rf.Network(frequency=f, s=a2s(a, z0=50.0), z0=50.0)
    cand = line.zc_candidates(singular, singular_c=1e-9)
    assert np.all(np.isnan(cand[2]))
    assert np.all(np.isfinite(cand[[0, 1, 3, 4]]))


def test_select_zc_branch_follows_positive_real_root_on_clean_line(lossy):
    cand = line.zc_candidates(lossy)
    zc, regions = line.select_zc_branch(cand, lossy.frequency.f)
    assert np.allclose(zc.real, 50.0, atol=0.5)
    assert regions == ["valid"] * 101


def test_select_zc_branch_marks_disagreement_ambiguous():
    cand = fixtures.zc_candidates_with_flip(n=20, flip_at=12)
    zc, regions = line.select_zc_branch(cand, np.linspace(1e8, 2e9, 20))
    assert regions[12] == "ambiguous"
    assert regions[:12] == ["valid"] * 12 and regions[13:] == ["valid"] * 7
    # continuity picks the root nearest the previous value 50+0.5j:
    # |1+50j - (50+0.5j)| ~ 69.6 < |1-50j - (50+0.5j)| ~ 70.4, so 1+50j
    assert zc[12] == pytest.approx(1.0 + 50.0j)


def test_select_zc_branch_marks_nan_singular():
    cand = np.stack([np.full(5, 50.0 + 0j), np.full(5, -50.0 + 0j)], axis=1)
    cand[2] = np.nan
    zc, regions = line.select_zc_branch(cand, np.linspace(1e8, 1e9, 5))
    assert np.isnan(zc[2]) and regions[2] == "singular"
    assert regions[0] == "valid" and regions[4] == "valid"
    assert zc[3] == pytest.approx(50.0)  # continuity resumes from the last accepted value


def test_analyze_line_bundle_on_matched_line(lossy):
    out = line.analyze_line(lossy, in_port=1, out_port=2, tolerances={})
    assert set(out["values"]) == {"il_db", "rl_in_db", "rl_out_db", "zc_re_ohm", "zc_im_ohm"}
    assert out["regions"] == ["valid"] * 101
    assert out["warnings"] == []
    assert out["z_ref_ohm"] == pytest.approx(50.0)
    assert np.allclose(out["values"]["zc_re_ohm"], 50.0, atol=0.5)
    assert np.allclose(out["values"]["zc_im_ohm"], 0.0, atol=0.5)
    assert out["freq_hz"][0] == pytest.approx(1e7)


def test_analyze_line_warns_on_nonreciprocal_and_asymmetric_data():
    net = fixtures.nonreciprocal_line(freq=fixtures.frequency(npoints=21))
    out = line.analyze_line(net, in_port=1, out_port=2, tolerances={"reciprocity": 1e-6})
    assert any("reciprocity" in w for w in out["warnings"])
    asym = fixtures.lossy_line(freq=fixtures.frequency(npoints=21))
    s = asym.s.copy()
    s[:, 1, 1] = s[:, 1, 1] + 0.05
    asym.s = s
    out = line.analyze_line(asym, in_port=1, out_port=2, tolerances={"reciprocity": 1e-6})
    assert any("symmetry" in w for w in out["warnings"])
