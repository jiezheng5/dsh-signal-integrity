"""Regenerate the committed synthetic Touchstone examples from the test fixtures.

    uv run --frozen --group dev python scripts/gen_examples.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests import fixtures  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "examples" / "synthetic"


def main() -> None:
    written = [
        fixtures.write(fixtures.lossy_line(), OUT, "lossy_line_20mm"),
        fixtures.write(fixtures.series_rl_oneport(), OUT, "series_rl_10nH"),
        fixtures.write(fixtures.two_uncoupled_lines(), OUT, "two_uncoupled_lines"),
        fixtures.write(
            fixtures.two_uncoupled_lines_odd_even(), OUT, "two_uncoupled_lines_odd_even"
        ),
        fixtures.write(fixtures.advanced_line(), OUT, "anticausal_line"),
        fixtures.write(fixtures.active_line(), OUT, "active_line_gain1p5"),
        fixtures.write(fixtures.nonreciprocal_line(), OUT, "nonreciprocal_line"),
    ]
    for path in written:
        print(path.relative_to(OUT.parents[1]))


if __name__ == "__main__":
    main()
