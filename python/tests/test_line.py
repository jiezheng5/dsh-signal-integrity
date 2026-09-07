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
