import numpy as np

from dsh_si import plots

from . import fixtures


def test_overview_terms_prefer_reflections_then_strongest_transmissions():
    four = fixtures.two_uncoupled_lines(freq=fixtures.frequency(npoints=11))
    terms = plots.overview_terms(four)
    assert terms[:4] == [(0, 0), (1, 1), (2, 2), (3, 3)]
    assert len(terms) == plots.MAX_SERIES
    # the through paths 1->3 and 2->4 carry the energy; they must come before the zero-coupling terms
    assert {(0, 2), (2, 0), (1, 3), (3, 1)} <= set(terms[4:])


def test_two_port_draws_all_four_terms():
    line = fixtures.lossy_line(freq=fixtures.frequency(npoints=11))
    assert plots.overview_terms(line) == [(0, 0), (1, 1), (0, 1), (1, 0)]


def test_db_has_floor():
    assert plots.db(np.array([0.0]))[0] == plots.DB_FLOOR


def test_line_quantity_draws_two_series_and_shades_ambiguous(tmp_path):
    f = np.linspace(1e8, 1e10, 20)
    re = np.full(20, 50.0)
    im = np.zeros(20)
    regions = ["valid"] * 20
    regions[7] = "ambiguous"
    regions[15] = "singular"
    fig = plots.line_quantity(
        f,
        [("Re Zc", re), ("Im Zc", im)],
        regions,
        "Characteristic impedance (Ω)",
        "Zc of x",
        "sub",
    )
    ax = fig.axes[0]
    assert len(ax.get_lines()) == 2
    assert len(ax.patches) == 2  # one axvspan per shaded point
    png = plots.save_png(fig, tmp_path / "zc.png")
    assert png.stat().st_size > 1000
