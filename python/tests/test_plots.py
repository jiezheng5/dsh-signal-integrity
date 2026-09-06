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
