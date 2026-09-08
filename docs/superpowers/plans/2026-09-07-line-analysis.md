# Transmission-Line Analysis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `si_analyze` with `device: transmission_line` reports insertion loss, return loss, and complex characteristic impedance for 2-port single-ended and 4-port differential lines (differential and common mode), with CSV, PNGs, region labels, and `status: complete`.

**Architecture:** `python/dsh_si/line.py` is pure 2-port math on a scikit-rf `Network` (IL, RL, ±sqrt(B/C) candidates, branch selection, region labels). `python/dsh_si/mixed_mode.py` owns the 4-port port-mapping presets and the `se2gmm` conversion into a differential and a common-mode 2-port. `analyze.py` runs `line.analyze_line` once (single-ended) or twice (dd, cc) and writes the same report shape the lumped devices use. TypeScript only renders the new `summary.modes` block and forwards one new tolerance.

**Tech Stack:** Python 3.13, scikit-rf 2.1.0, NumPy, Matplotlib, pytest; TypeScript, vitest, Schemastery.

**Spec:** `docs/superpowers/specs/2026-09-07-line-analysis-design.md`

## Global Constraints

- Equations are the domain owner's (spec "Physics" section); implement them verbatim, flag doubts in the PR, never "fix" them silently.
- Region vocabulary for lines: `valid | ambiguous | singular`. Ambiguous points keep selector B's value, are shaded in plots, and are excluded from medians. Singular points are `NaN`.
- Ports are 1-based everywhere in the interpretation and in reports; convert to 0-based only at the scikit-rf call boundary.
- Never convert mixed-mode data twice: `input_is_mixed_mode: true` skips `se2gmm`.
- `pnpm check` must be green before every push. Python formatting: `uv run --project python --frozen ruff format dsh_si tests`.
- Commit subjects use conventional commits; each commit ends with the `Co-Authored-By` and `Claude-Session` trailers used on this branch (see `git log -3`).
- Branch: `feat/line-analysis` off `main`. Do not stack on PR #6.
- Run Python tests as `uv run --project python --frozen --group dev pytest <file> -k <name>` from the repo root; TS tests as `pnpm vitest run <file>` after `source ~/.nvm/nvm.sh && nvm use 22.19.0`.

---

## File Structure

| File | Responsibility |
|---|---|
| Create `python/dsh_si/line.py` | IL, RL, Z_c candidates, `select_zc_branch`, `analyze_line` |
| Create `python/dsh_si/mixed_mode.py` | `PRESETS`, `resolve_mapping`, `to_mixed_mode` |
| Modify `python/dsh_si/interpretation.py` | `through_convention` validation for `transmission_line` |
| Modify `python/dsh_si/inspect.py` | `through_convention` question for 4-port files |
| Modify `python/dsh_si/plots.py` | `line_quantity` figure (one or two series, region shading) |
| Modify `python/dsh_si/analyze.py` | `transmission_line` branch: CSV, PNGs, summary, sections |
| Modify `python/tests/fixtures.py` | `two_uncoupled_lines_odd_even`, `zc_candidates_with_flip` |
| Create `python/tests/test_line.py`, `python/tests/test_mixed_mode.py` | closed-form tests |
| Modify `python/tests/test_interpretation.py`, `test_inspect.py`, `test_plots.py`, `test_analyze.py` | new behaviour |
| Modify `src/config.ts` | `tolerances.singularC` |
| Modify `src/tools/analyze.ts` | render `summary.modes` |
| Modify `tests/fixtures/fake-worker.mjs`, `tests/analyze.spec.ts` | `line` fixture mode; uv test expects `complete` |
| Modify `python/scripts/gen_examples.py`, `examples/synthetic/README.md` | odd_even 4-port example |
| Modify `docs/handoff.md`, `CLAUDE.md` (one line) | state |

---

### Task 1: IL, RL, and Z_c candidates in `line.py`

**Files:**
- Create: `python/dsh_si/line.py`
- Create: `python/tests/test_line.py`

**Interfaces:**
- Produces: `insertion_loss_db(network, in_port: int, out_port: int) -> np.ndarray`, `return_loss_db(network, port: int) -> np.ndarray`, `zc_candidates(network, singular_c: float = 1e-9) -> np.ndarray` (shape `(n, 2)`, complex, both rows `NaN` where `|C| < singular_c`), `Region = Literal["valid", "ambiguous", "singular"]`.

- [ ] **Step 1: Write the failing tests**

```python
# python/tests/test_line.py
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
    # space and converted back with rf.a2s.
    import skrf as rf

    f = fixtures.frequency(0.01, 1.0, 5)
    a = fixtures.lossy_line(freq=f).a.copy()
    a[2, 1, 0] = 0.0
    singular = rf.Network(frequency=f, s=rf.a2s(a, z0=50.0), z0=50.0)
    cand = line.zc_candidates(singular, singular_c=1e-9)
    assert np.all(np.isnan(cand[2]))
    assert np.all(np.isfinite(cand[[0, 1, 3, 4]]))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --project python --frozen --group dev pytest tests/test_line.py -v`
Expected: `ImportError: cannot import name 'line'` (collection error).

- [ ] **Step 3: Write the minimal implementation**

```python
# python/dsh_si/line.py
"""Transmission-line quantities from a 2-port S-parameter network.

Domain owner's equations (positive-dB losses, ABCD-based characteristic impedance):

    IL     = -20 log10 |S_out,in|
    RL_in  = -20 log10 |S_in,in|,   RL_out = -20 log10 |S_out,out|
    Z_c    = ± sqrt(B / C)        (ABCD of the 2-port; no symmetry assumed)

equivalent for a symmetric reciprocal line:
    Z_c = Z_ref * sqrt(((1+S11)^2 - S12 S21) / ((1-S11)^2 - S12 S21))

`select_zc_branch` picks one root per frequency and labels each point:
valid | ambiguous | singular. See the spec, docs/superpowers/specs/2026-09-07-line-analysis-design.md.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np

Region = Literal["valid", "ambiguous", "singular"]

DEFAULT_SINGULAR_C = 1e-9


def _s(network: Any, row: int, col: int) -> np.ndarray:
    """S[row, col] with 1-based ports."""
    return np.asarray(network.s[:, row - 1, col - 1], dtype=complex)


def insertion_loss_db(network: Any, in_port: int, out_port: int) -> np.ndarray:
    """Positive insertion loss in dB from `in_port` to `out_port`."""
    return -20.0 * np.log10(np.abs(_s(network, out_port, in_port)))


def return_loss_db(network: Any, port: int) -> np.ndarray:
    """Positive return loss in dB at `port`."""
    return -20.0 * np.log10(np.abs(_s(network, port, port)))


def zc_candidates(network: Any, singular_c: float = DEFAULT_SINGULAR_C) -> np.ndarray:
    """Both roots of sqrt(B/C) per frequency, shape (n, 2); NaN rows where |C| < singular_c."""
    a = np.asarray(network.a, dtype=complex)
    b, c = a[:, 0, 1], a[:, 1, 0]
    safe_c = np.where(np.abs(c) < singular_c, np.nan, c)
    root = np.sqrt(b / safe_c)
    return np.stack([root, -root], axis=1)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --project python --frozen --group dev pytest tests/test_line.py -v`
Expected: 4 passed.

- [ ] **Step 5: Format and commit**

```bash
uv run --project python --frozen ruff format python/dsh_si python/tests
git add python/dsh_si/line.py python/tests/test_line.py
git commit -m "feat(python): line.py with IL, RL and Z_c root candidates"
```

---

### Task 2: `select_zc_branch` (domain owner's algorithm, reference implementation)

**Files:**
- Modify: `python/dsh_si/line.py`
- Modify: `python/tests/fixtures.py`
- Modify: `python/tests/test_line.py`

**Interfaces:**
- Consumes: `zc_candidates` output `(n, 2)`.
- Produces: `select_zc_branch(candidates: np.ndarray, freq_hz: np.ndarray) -> tuple[np.ndarray, list[Region]]`.

The spec's contract, decided with the domain owner (option 3): selector A = the root with `Re > 0` (ambiguous when both or neither qualify); selector B = `Re > 0` at the first finite point, then nearest root to the previous accepted value. Reported value follows B; region is `valid` when A and B agree, `ambiguous` when they differ, `singular` when the candidates are not finite. The implementation below is the reference the domain owner reviews in the PR; if they replace the body, the tests still define the contract.

- [ ] **Step 1: Add the branch-flip fixture**

Append to `python/tests/fixtures.py`:

```python
def zc_candidates_with_flip(n: int = 20, flip_at: int = 12) -> np.ndarray:
    """Roots of a 50 Ω line with one point where both roots have Re > 0.

    Selector A (positive real) cannot decide there; selector B (continuity) still follows
    the curve, so the point must come back labelled `ambiguous`.
    """
    root = np.full(n, 50.0 + 0.5j, dtype=complex)
    cand = np.stack([root, -root], axis=1)
    cand[flip_at] = [1.0 + 50.0j, 1.0 - 50.0j]
    return cand
```

- [ ] **Step 2: Write the failing tests**

Append to `python/tests/test_line.py`:

```python
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
    # |1+50j - (50+0.5j)| ≈ 69.6 < |1-50j - (50+0.5j)| ≈ 70.4, so 1+50j
    assert zc[12] == pytest.approx(1.0 + 50.0j)


def test_select_zc_branch_marks_nan_singular():
    cand = np.stack([np.full(5, 50.0 + 0j), np.full(5, -50.0 + 0j)], axis=1)
    cand[2] = np.nan
    zc, regions = line.select_zc_branch(cand, np.linspace(1e8, 1e9, 5))
    assert np.isnan(zc[2]) and regions[2] == "singular"
    assert regions[0] == "valid" and regions[4] == "valid"
    assert zc[3] == pytest.approx(50.0)  # continuity resumes from the last accepted value
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run --project python --frozen --group dev pytest tests/test_line.py -k select_zc -v`
Expected: 3 failed with `AttributeError: module 'dsh_si.line' has no attribute 'select_zc_branch'`.

- [ ] **Step 4: Write the reference implementation**

Append to `python/dsh_si/line.py`:

```python
def select_zc_branch(candidates: np.ndarray, freq_hz: np.ndarray) -> tuple[np.ndarray, list[Region]]:
    """Pick one Z_c root per frequency and label the point.

    Selector A: the root with Re > 0 (undecided when both or neither qualify).
    Selector B: Re > 0 at the first finite point, then the root nearest the previously
    accepted value (frequency continuity).
    The reported value follows B. Regions: `valid` when A and B agree, `ambiguous` when
    they differ or A is undecided, `singular` when neither root is finite (value NaN).
    """
    cand = np.asarray(candidates, dtype=complex)
    n = cand.shape[0]
    zc = np.full(n, np.nan, dtype=complex)
    regions: list[Region] = ["singular"] * n
    previous: complex | None = None
    for k in range(n):
        pair = cand[k]
        finite = np.isfinite(pair)
        if not finite.any():
            continue
        positive = finite & (pair.real > 0)
        a_choice = pair[positive][0] if positive.sum() == 1 else None
        if previous is None:
            if a_choice is None:
                # No anchor yet and A undecided: take the finite root with the larger Re.
                b_choice = pair[finite][np.argmax(pair[finite].real)]
            else:
                b_choice = a_choice
        else:
            b_choice = pair[finite][np.argmin(np.abs(pair[finite] - previous))]
        zc[k] = b_choice
        previous = b_choice
        regions[k] = "valid" if a_choice is not None and a_choice == b_choice else "ambiguous"
    return zc, regions
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --project python --frozen --group dev pytest tests/test_line.py -v`
Expected: 7 passed.

- [ ] **Step 6: Format and commit**

```bash
uv run --project python --frozen ruff format python/dsh_si python/tests
git add python/dsh_si/line.py python/tests/fixtures.py python/tests/test_line.py
git commit -m "feat(python): Z_c branch selection with valid/ambiguous/singular regions"
```

---

### Task 3: `analyze_line` bundle with symmetry and reciprocity warnings

**Files:**
- Modify: `python/dsh_si/line.py`
- Modify: `python/tests/test_line.py`

**Interfaces:**
- Produces: `analyze_line(network, in_port: int, out_port: int, tolerances: dict) -> dict` returning `{"freq_hz": np.ndarray, "values": {"il_db", "rl_in_db", "rl_out_db", "zc_re_ohm", "zc_im_ohm"}, "regions": list[Region], "warnings": list[str], "z_ref_ohm": float}`. `tolerances` keys used: `reciprocity` (default `1e-6`), `singular_c` (default `1e-9`).

- [ ] **Step 1: Write the failing tests**

Append to `python/tests/test_line.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --project python --frozen --group dev pytest tests/test_line.py -k analyze_line -v`
Expected: 2 failed, `AttributeError ... 'analyze_line'`.

- [ ] **Step 3: Write the implementation**

Append to `python/dsh_si/line.py`:

```python
def analyze_line(network: Any, in_port: int, out_port: int, tolerances: dict[str, Any]) -> dict[str, Any]:
    """IL, RL, and Z_c with region labels for one 2-port (or one mixed-mode 2-port)."""
    reciprocity_tol = float(tolerances.get("reciprocity", 1e-6))
    singular_c = float(tolerances.get("singular_c", DEFAULT_SINGULAR_C))
    freq = np.asarray(network.frequency.f, dtype=float)
    cand = zc_candidates(network, singular_c)
    zc, regions = select_zc_branch(cand, freq)

    warnings: list[str] = []
    s_in_out, s_out_in = _s(network, in_port, out_port), _s(network, out_port, in_port)
    n_nonrecip = int(np.count_nonzero(np.abs(s_in_out - s_out_in) > reciprocity_tol))
    if n_nonrecip:
        warnings.append(
            f"reciprocity: |S{in_port}{out_port} - S{out_port}{in_port}| exceeds {reciprocity_tol:g} at "
            f"{n_nonrecip} of {freq.size} points; Z_c still follows the ABCD definition"
        )
    s_ii, s_oo = _s(network, in_port, in_port), _s(network, out_port, out_port)
    n_asym = int(np.count_nonzero(np.abs(s_ii - s_oo) > reciprocity_tol))
    if n_asym:
        warnings.append(
            f"symmetry: |S{in_port}{in_port} - S{out_port}{out_port}| exceeds {reciprocity_tol:g} at "
            f"{n_asym} of {freq.size} points; the line is not uniform end to end"
        )
    z_ref = complex(np.asarray(network.z0)[0, in_port - 1])
    return {
        "freq_hz": freq,
        "values": {
            "il_db": insertion_loss_db(network, in_port, out_port),
            "rl_in_db": return_loss_db(network, in_port),
            "rl_out_db": return_loss_db(network, out_port),
            "zc_re_ohm": zc.real,
            "zc_im_ohm": zc.imag,
        },
        "regions": regions,
        "warnings": warnings,
        "z_ref_ohm": float(z_ref.real),
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --project python --frozen --group dev pytest tests/test_line.py -v`
Expected: 9 passed.

- [ ] **Step 5: Format and commit**

```bash
uv run --project python --frozen ruff format python/dsh_si python/tests
git add python/dsh_si/line.py python/tests/test_line.py
git commit -m "feat(python): analyze_line bundles IL, RL, Z_c with reciprocity and symmetry warnings"
```

---

### Task 4: `mixed_mode.py` presets and conversion

**Files:**
- Create: `python/dsh_si/mixed_mode.py`
- Create: `python/tests/test_mixed_mode.py`
- Modify: `python/tests/fixtures.py`

**Interfaces:**
- Produces: `CONVENTIONS = ("odd_even", "half_split", "custom")`; `preset_mapping(convention: str, n_ports: int) -> dict` returning `{"ports": {"in": [...], "out": [...]}, "pairs": [{"name": "pair1", "p": int, "n": int}, ...]}` (1-based); `to_mixed_mode(network, pairs: list[dict]) -> dict` returning `{"dd": Network, "cc": Network, "mixed": Network}` where `dd`/`cc` are 2-ports with ports `[in, out]`; `split_mixed_mode_file(network) -> dict` for already-mixed 4-port files (ports taken as `[d_in, d_out, c_in, c_out]`).

Facts verified against scikit-rf 2.1.0: `se2gmm(p=2)` pairs ports (1,2) and (3,4), through 1→3 and 2→4, and sets z0 to `[2Z0, 2Z0, Z0/2, Z0/2]`; `subnetwork([0,1])` keeps those z0s; `renumber([0,1,2,3],[0,2,1,3])` reorders odd_even data into that layout.

- [ ] **Step 1: Add the odd_even fixture**

Append to `python/tests/fixtures.py`:

```python
def two_uncoupled_lines_odd_even(freq: rf.Frequency | None = None, **kwargs) -> rf.Network:
    """The same two lines numbered PLTS-style: through 1->2 and 3->4, pairs (1,3) and (2,4)."""
    net = two_uncoupled_lines(freq=freq, **kwargs).copy()
    net.renumber([0, 1, 2, 3], [0, 2, 1, 3])
    net.name = "two_lines_odd_even"
    return net
```

- [ ] **Step 2: Write the failing tests**

```python
# python/tests/test_mixed_mode.py
import numpy as np
import pytest

from dsh_si import line, mixed_mode
from dsh_si.protocol import WorkerError

from . import fixtures


def test_preset_half_split_for_four_ports():
    m = mixed_mode.preset_mapping("half_split", 4)
    assert m["ports"] == {"in": [1, 2], "out": [3, 4]}
    assert m["pairs"] == [{"name": "pair1", "p": 1, "n": 2}, {"name": "pair2", "p": 3, "n": 4}]


def test_preset_odd_even_for_four_ports():
    m = mixed_mode.preset_mapping("odd_even", 4)
    assert m["ports"] == {"in": [1, 3], "out": [2, 4]}
    assert m["pairs"] == [{"name": "pair1", "p": 1, "n": 3}, {"name": "pair2", "p": 2, "n": 4}]


def test_preset_rejects_odd_port_count_and_custom():
    with pytest.raises(WorkerError) as info:
        mixed_mode.preset_mapping("odd_even", 3)
    assert info.value.code == "interpretation_invalid"
    with pytest.raises(WorkerError):
        mixed_mode.preset_mapping("custom", 4)


@pytest.fixture(scope="module")
def freq():
    return fixtures.frequency(npoints=51)


def test_to_mixed_mode_half_split_gives_100_and_25_ohm(freq):
    four = fixtures.two_uncoupled_lines(freq=freq)
    modes = mixed_mode.to_mixed_mode(four, mixed_mode.preset_mapping("half_split", 4)["pairs"])
    dd, cc = modes["dd"], modes["cc"]
    assert dd.nports == 2 and cc.nports == 2
    assert np.allclose(dd.z0, 100.0) and np.allclose(cc.z0, 25.0)
    zc_dd, _ = line.select_zc_branch(line.zc_candidates(dd), freq.f)
    zc_cc, _ = line.select_zc_branch(line.zc_candidates(cc), freq.f)
    assert np.allclose(zc_dd.real, 100.0, atol=1.0) and np.allclose(zc_cc.real, 25.0, atol=0.25)
    single = fixtures.lossy_line(freq=freq)
    assert np.allclose(line.insertion_loss_db(dd, 1, 2), line.insertion_loss_db(single, 1, 2))


def test_to_mixed_mode_odd_even_matches_half_split(freq):
    a = mixed_mode.to_mixed_mode(
        fixtures.two_uncoupled_lines(freq=freq), mixed_mode.preset_mapping("half_split", 4)["pairs"]
    )
    b = mixed_mode.to_mixed_mode(
        fixtures.two_uncoupled_lines_odd_even(freq=freq),
        mixed_mode.preset_mapping("odd_even", 4)["pairs"],
    )
    assert np.allclose(a["dd"].s, b["dd"].s) and np.allclose(a["cc"].s, b["cc"].s)


def test_swapping_polarity_of_one_pair_flips_sdd21_phase_only(freq):
    four = fixtures.two_uncoupled_lines(freq=freq)
    normal = mixed_mode.to_mixed_mode(four, mixed_mode.preset_mapping("half_split", 4)["pairs"])
    swapped_pairs = [{"name": "pair1", "p": 1, "n": 2}, {"name": "pair2", "p": 4, "n": 3}]
    swapped = mixed_mode.to_mixed_mode(four, swapped_pairs)
    phase = np.angle(swapped["dd"].s[:, 1, 0]) - np.angle(normal["dd"].s[:, 1, 0])
    assert np.allclose(np.abs(np.angle(np.exp(1j * phase))), np.pi)
    assert np.allclose(np.abs(swapped["dd"].s[:, 1, 0]), np.abs(normal["dd"].s[:, 1, 0]))
    assert np.abs(normal["mixed"].s[:, 0, 2]).max() < 1e-12  # no mode conversion for uncoupled lines


def test_split_mixed_mode_file_takes_stored_order(freq):
    four = fixtures.two_uncoupled_lines(freq=freq)
    mixed = mixed_mode.to_mixed_mode(four, mixed_mode.preset_mapping("half_split", 4)["pairs"])["mixed"]
    modes = mixed_mode.split_mixed_mode_file(mixed)
    assert np.allclose(modes["dd"].z0, 100.0) and np.allclose(modes["cc"].z0, 25.0)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv run --project python --frozen --group dev pytest tests/test_mixed_mode.py -v`
Expected: collection error `ImportError: cannot import name 'mixed_mode'`.

- [ ] **Step 4: Write the implementation**

```python
# python/dsh_si/mixed_mode.py
"""Port-mapping presets and single-ended to mixed-mode conversion for 4-port lines.

Two industry conventions for a 2N-port differential channel:

    odd_even   through 1->2, 3->4, ...   pairs (1,3), (2,4), ...    (PLTS-style "1-2 through")
    half_split through 1->1+N, ...       pairs (1,2), (3,4), ...

scikit-rf's se2gmm expects the half_split layout: adjacent ports form a pair and port k
connects through to k+2. Any other layout is renumbered into it first. Preset polarity:
the lower-numbered port of each pair is P. Converted reference impedances are 2*Z0
(differential) and Z0/2 (common), and mixed-mode input is never converted twice.
"""

from __future__ import annotations

from typing import Any

from .protocol import WorkerError

CONVENTIONS: tuple[str, ...] = ("odd_even", "half_split", "custom")


def preset_mapping(convention: str, n_ports: int) -> dict[str, Any]:
    """`ports` and `pairs` implied by a preset, 1-based."""
    if convention not in ("odd_even", "half_split"):
        raise WorkerError(
            "interpretation_invalid",
            f"through_convention: {convention!r} has no preset; use odd_even, half_split, or custom with ports",
        )
    if n_ports % 2 or n_ports < 4:
        raise WorkerError(
            "interpretation_invalid",
            f"through_convention {convention} needs an even port count of at least 4, this file has {n_ports}",
        )
    half = n_ports // 2
    if convention == "odd_even":
        ins = list(range(1, n_ports + 1, 2))
        outs = list(range(2, n_ports + 1, 2))
        pairs = _odd_even_pairs(n_ports)
    else:
        ins = list(range(1, half + 1))
        outs = list(range(half + 1, n_ports + 1))
        pairs = [(1 + 2 * k, 2 + 2 * k) for k in range(half)]
    return {
        "ports": {"in": ins, "out": outs},
        "pairs": [{"name": f"pair{k + 1}", "p": p, "n": n} for k, (p, n) in enumerate(pairs)],
    }


def _odd_even_pairs(n_ports: int) -> list[tuple[int, int]]:
    """Pairs for odd_even: the near end is the odd ports (1,3), the far end the even ports (2,4)."""
    odds = list(range(1, n_ports + 1, 2))
    evens = list(range(2, n_ports + 1, 2))
    near = [(odds[k], odds[k + 1]) for k in range(0, len(odds), 2)]
    far = [(evens[k], evens[k + 1]) for k in range(0, len(evens), 2)]
    return near + far
```

Then append the conversion:

```python
def to_mixed_mode(network: Any, pairs: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert a 4-port single-ended network into differential and common-mode 2-ports.

    `pairs` is [{p, n}, {p, n}] in 1-based ports; the first pair is the input end.
    Returns {"dd", "cc"} as 2-ports with ports [in, out] and {"mixed"} as the full
    mixed-mode 4-port [d_in, d_out, c_in, c_out].
    """
    if network.nports != 4 or len(pairs) != 2:
        raise WorkerError(
            "interpretation_invalid",
            f"differential line analysis needs a 4-port file and exactly 2 pairs (got {network.nports} ports, {len(pairs)} pairs)",
        )
    order = [pairs[0]["p"] - 1, pairs[0]["n"] - 1, pairs[1]["p"] - 1, pairs[1]["n"] - 1]
    mixed = network.copy()
    # renumber(from, to): the port currently at from[k] becomes port to[k]
    mixed.renumber(order, [0, 1, 2, 3])
    try:
        mixed.se2gmm(p=2)
    except Exception as exc:  # scikit-rf raises plain exceptions for degenerate z0
        raise WorkerError("numerical_error", f"mixed-mode conversion failed: {exc}") from exc
    return split_mixed_mode_file(mixed) | {"mixed": mixed}


def split_mixed_mode_file(mixed: Any) -> dict[str, Any]:
    """Differential and common 2-ports from a mixed-mode 4-port stored as [d_in, d_out, c_in, c_out]."""
    if mixed.nports != 4:
        raise WorkerError(
            "interpretation_invalid", f"a mixed-mode line file must have 4 ports, this one has {mixed.nports}"
        )
    dd = mixed.subnetwork([0, 1])
    cc = mixed.subnetwork([2, 3])
    dd.name, cc.name = "differential", "common"
    return {"dd": dd, "cc": cc}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --project python --frozen --group dev pytest tests/test_mixed_mode.py -v`
Expected: 7 passed. If `test_to_mixed_mode_odd_even_matches_half_split` fails, the `renumber` direction is inverted: swap the two argument lists in `mixed.renumber(order, [0, 1, 2, 3])` and re-run; the polarity test then disambiguates.

- [ ] **Step 6: Format and commit**

```bash
uv run --project python --frozen ruff format python/dsh_si python/tests
git add python/dsh_si/mixed_mode.py python/tests/test_mixed_mode.py python/tests/fixtures.py
git commit -m "feat(python): mixed_mode presets (odd_even, half_split) and se2gmm split into dd/cc"
```

---

### Task 5: `through_convention` in the interpretation contract

**Files:**
- Modify: `python/dsh_si/interpretation.py` (the `elif device == "transmission_line":` block)
- Modify: `python/tests/test_interpretation.py`

**Interfaces:**
- Consumes: `mixed_mode.CONVENTIONS`, `mixed_mode.preset_mapping`.
- Produces: normalized `transmission_line` interpretations always carry `ports {in, out}`; for n = 4 with a preset they also carry `pairs` when `topology == "differential_pairs"` and `through_convention`. `topology` is now accepted for lines (`single_ended_paths` default when absent, `differential_pairs`, `mixed_mode_already`).

- [ ] **Step 1: Write the failing tests**

Append to `python/tests/test_interpretation.py` (it already imports `normalize` and `WorkerError`; check the top of the file and reuse its helpers):

```python
def test_line_two_port_defaults_ports_and_convention_is_ignored():
    out = normalize({"device": "transmission_line"}, 2)
    assert out["ports"] == {"in": [1], "out": [2]}
    assert out["topology"] == "single_ended_paths"
    assert "pairs" not in out


def test_line_four_port_preset_fills_ports_and_pairs():
    out = normalize(
        {"device": "transmission_line", "through_convention": "odd_even", "topology": "differential_pairs"},
        4,
    )
    assert out["through_convention"] == "odd_even"
    assert out["ports"] == {"in": [1, 3], "out": [2, 4]}
    assert out["pairs"] == [{"name": "pair1", "p": 1, "n": 3}, {"name": "pair2", "p": 2, "n": 4}]


def test_line_four_port_single_ended_preset_has_no_pairs():
    out = normalize({"device": "transmission_line", "through_convention": "half_split"}, 4)
    assert out["ports"] == {"in": [1, 2], "out": [3, 4]}
    assert out["topology"] == "single_ended_paths" and "pairs" not in out


def test_line_custom_requires_ports():
    with pytest.raises(WorkerError) as info:
        normalize({"device": "transmission_line", "through_convention": "custom"}, 4)
    assert "ports" in info.value.message


def test_line_rejects_three_ports_and_unknown_convention():
    with pytest.raises(WorkerError):
        normalize({"device": "transmission_line", "ports": {"in": [1], "out": [2]}}, 3)
    with pytest.raises(WorkerError) as info:
        normalize({"device": "transmission_line", "through_convention": "zigzag"}, 4)
    assert "through_convention" in info.value.message


def test_line_mixed_mode_input_keeps_stored_order():
    out = normalize(
        {"device": "transmission_line", "topology": "mixed_mode_already", "input_is_mixed_mode": True}, 4
    )
    assert out["ports"] == {"in": [1], "out": [2]}
    assert out["input_is_mixed_mode"] is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --project python --frozen --group dev pytest tests/test_interpretation.py -k line_ -v`
Expected: 6 failed (mostly `WorkerError: ports: expected {in: [...], out: [...]}` and missing keys).

- [ ] **Step 3: Replace the `transmission_line` branch**

In `python/dsh_si/interpretation.py`, add `from . import mixed_mode` under the existing imports and replace the whole `elif device == "transmission_line":` block with:

```python
    elif device == "transmission_line":
        topology = raw.get("topology", "single_ended_paths")
        if topology not in TOPOLOGIES:
            problems.append(f"topology: expected one of {list(TOPOLOGIES)}, got {topology!r}")
            topology = "single_ended_paths"
        out["topology"] = topology
        convention = raw.get("through_convention")
        if n_ports not in (2, 4):
            problems.append(f"transmission_line analysis needs a 2- or 4-port file, this file has {n_ports}")
        if convention is not None and convention not in mixed_mode.CONVENTIONS:
            problems.append(
                f"through_convention: expected one of {list(mixed_mode.CONVENTIONS)}, got {convention!r}"
            )
            convention = None
        if n_ports == 2:
            out["ports"] = {"in": [1], "out": [2]}
        elif topology == "mixed_mode_already" or mixed:
            # Stored as [d_in, d_out, c_in, c_out]; the analysis splits it without conversion.
            out["ports"] = {"in": [1], "out": [2]}
            out["input_is_mixed_mode"] = True
        elif convention in ("odd_even", "half_split") and n_ports == 4:
            preset = mixed_mode.preset_mapping(convention, n_ports)
            out["through_convention"] = convention
            out["ports"] = preset["ports"]
            if topology == "differential_pairs":
                out["pairs"] = preset["pairs"]
        else:
            if convention == "custom":
                out["through_convention"] = "custom"
            ports = raw.get("ports")
            if not isinstance(ports, dict):
                problems.append(
                    "ports: expected {in: [...], out: [...]} (or choose through_convention odd_even / half_split)"
                )
            else:
                out["ports"] = {
                    "in": _port_list(ports.get("in"), "ports.in", n_ports, problems),
                    "out": _port_list(ports.get("out"), "ports.out", n_ports, problems),
                }
                if out["ports"]["in"] and out["ports"]["out"]:
                    if len(out["ports"]["in"]) != len(out["ports"]["out"]):
                        problems.append("ports: in and out must have the same length")
                    overlap = set(out["ports"]["in"]) & set(out["ports"]["out"])
                    if overlap:
                        problems.append(f"ports: {sorted(overlap)} listed as both in and out")
            if topology == "differential_pairs":
                out["pairs"] = _pairs(raw.get("pairs"), n_ports, problems)
            elif "pairs" in raw and raw["pairs"] is not None:
                out["pairs"] = _pairs(raw["pairs"], n_ports, problems)
```

Also, in `inspect.py`'s `REQUIRED_BY_DEVICE`, change the `transmission_line` entry to `["through_convention (4-port) or ports", "topology (4-port)", "input_is_mixed_mode"]`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --project python --frozen --group dev pytest tests/test_interpretation.py -v`
Expected: all pass, including the pre-existing line tests (they pass explicit `ports` for 2-port files, which the new branch overrides with the same values).

- [ ] **Step 5: Format and commit**

```bash
uv run --project python --frozen ruff format python/dsh_si python/tests
git add python/dsh_si/interpretation.py python/dsh_si/inspect.py python/tests/test_interpretation.py
git commit -m "feat(python): through_convention presets in the transmission_line interpretation"
```

---

### Task 6: `through_convention` question in `si_inspect`

**Files:**
- Modify: `python/dsh_si/inspect.py` (`build_questions`)
- Modify: `python/tests/test_inspect.py`

**Interfaces:**
- Produces: for `n_ports == 4`, a question `{"id": "through_convention", "header": "Through paths", ...}` placed right after the `topology` question with options in the order `odd_even`, `half_split`, `custom`.

- [ ] **Step 1: Write the failing test**

Append to `python/tests/test_inspect.py` (check how it imports `build_questions`; the existing tests call it with a metadata dict):

```python
def test_four_port_asks_through_convention_after_topology():
    questions = build_questions({"n_ports": 4, "mixed_mode_hint": False})
    ids = [q["id"] for q in questions]
    assert ids[:3] == ["device", "topology", "through_convention"]
    labels = [o["label"] for o in questions[2]["options"]]
    assert labels == ["odd_even", "half_split", "custom"]
    assert "1→2 and 3→4" in questions[2]["options"][0]["description"]


def test_two_and_eight_port_do_not_ask_through_convention():
    for n in (2, 8):
        ids = [q["id"] for q in build_questions({"n_ports": n, "mixed_mode_hint": False})]
        assert "through_convention" not in ids
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --project python --frozen --group dev pytest tests/test_inspect.py -k through_convention -v`
Expected: 1 failed on `ids[:3]`, 1 passed.

- [ ] **Step 3: Add the question**

In `build_questions`, inside the `else:` branch (n_ports > 2), after `questions.append({... "id": "topology" ...})`, add:

```python
        if n_ports == 4:
            questions.append(
                {
                    "id": "through_convention",
                    "header": "Through paths",
                    "question": "Which ports connect through the line? (Preset polarity: the lower port of a pair is P.)",
                    "options": [
                        {
                            "label": "odd_even",
                            "description": "1→2 and 3→4 are the through paths; pairs are 1/3 and 2/4 (PLTS-style).",
                        },
                        {
                            "label": "half_split",
                            "description": "1→3 and 2→4 are the through paths; pairs are 1/2 and 3/4.",
                        },
                        {
                            "label": "custom",
                            "description": "Enter ports {in, out} and, for differential, pairs {p, n} yourself.",
                        },
                    ],
                }
            )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --project python --frozen --group dev pytest tests/test_inspect.py -v`
Expected: all pass.

- [ ] **Step 5: Format and commit**

```bash
uv run --project python --frozen ruff format python/dsh_si python/tests
git add python/dsh_si/inspect.py python/tests/test_inspect.py
git commit -m "feat(python): si_inspect asks the through convention for 4-port files"
```

---

### Task 7: `plots.line_quantity`

**Files:**
- Modify: `python/dsh_si/plots.py`
- Modify: `python/tests/test_plots.py`

**Interfaces:**
- Produces: `line_quantity(freq_hz, series: list[tuple[str, np.ndarray]], regions: list[str], ylabel: str, title: str, subtitle: str) -> Figure`. Draws one line per `(label, values)` entry, shades `ambiguous` and `singular` spans, legend when more than one series or any shading.

- [ ] **Step 1: Write the failing test**

Append to `python/tests/test_plots.py` (it already imports `plots` and writes to `tmp_path`; follow the existing `lumped_quantity` test's style):

```python
def test_line_quantity_draws_two_series_and_shades_ambiguous(tmp_path):
    import numpy as np

    f = np.linspace(1e8, 1e10, 20)
    re = np.full(20, 50.0)
    im = np.zeros(20)
    regions = ["valid"] * 20
    regions[7] = "ambiguous"
    regions[15] = "singular"
    fig = plots.line_quantity(
        f, [("Re Zc", re), ("Im Zc", im)], regions, "Characteristic impedance (Ω)", "Zc of x", "sub"
    )
    ax = fig.axes[0]
    assert len(ax.get_lines()) == 2
    assert len(ax.patches) == 2  # one axvspan per shaded point
    png = plots.save_png(fig, tmp_path / "zc.png")
    assert png.stat().st_size > 1000
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --project python --frozen --group dev pytest tests/test_plots.py -k line_quantity -v`
Expected: `AttributeError: module 'dsh_si.plots' has no attribute 'line_quantity'`.

- [ ] **Step 3: Implement**

In `python/dsh_si/plots.py`, extend `REGION_SHADE` with two entries and add the function after `lumped_quantity`:

```python
REGION_SHADE.update({"ambiguous": "#e0a020", "singular": "#e34948"})


def _shade_regions(ax: Any, f_ghz: np.ndarray, regions: list[str]) -> set[str]:
    """Shade every maximal run of shaded region labels; returns the labels used."""
    shaded: set[str] = set()
    start = None
    for k, label in enumerate(list(regions) + [None]):
        if start is not None and (label != regions[start]):
            ax.axvspan(f_ghz[start], f_ghz[k - 1], color=REGION_SHADE[regions[start]], alpha=0.12, linewidth=0)
            shaded.add(regions[start])
            start = None
        if label in REGION_SHADE and start is None:
            start = k
    return shaded


def line_quantity(
    freq_hz: np.ndarray,
    series: list[tuple[str, np.ndarray]],
    regions: list[str],
    ylabel: str,
    title: str,
    subtitle: str,
) -> Any:
    """One or two line quantities versus frequency with ambiguous/singular spans shaded."""
    f_ghz = np.asarray(freq_hz, dtype=float) / 1e9
    fig, ax = plt.subplots(figsize=(9, 5), dpi=100)
    for k, (label, values) in enumerate(series):
        ax.plot(f_ghz, np.asarray(values, dtype=float), color=PALETTE[k], linewidth=1.6, label=label)
    shaded = _shade_regions(ax, f_ghz, regions)
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel(ylabel)
    ax.set_title(f"{title}\n{subtitle}", fontsize=11, loc="left")
    ax.grid(True, alpha=0.25, linewidth=0.6)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    if len(series) > 1 or shaded:
        ax.legend(frameon=False, fontsize=9)
    if shaded:
        ax.text(
            1.0, -0.14, "shaded: " + ", ".join(sorted(shaded)),
            transform=ax.transAxes, ha="right", fontsize=8, color="#52514e",
        )
    fig.tight_layout()
    return fig
```

Do not touch `lumped_quantity`; its own shading loop stays as is (a later cleanup may share `_shade_regions`, not this PR).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --project python --frozen --group dev pytest tests/test_plots.py -v`
Expected: all pass.

- [ ] **Step 5: Format and commit**

```bash
uv run --project python --frozen ruff format python/dsh_si python/tests
git add python/dsh_si/plots.py python/tests/test_plots.py
git commit -m "feat(python): line_quantity plot with ambiguous/singular shading"
```

---

### Task 8: `analyze.py` transmission-line branch

**Files:**
- Modify: `python/dsh_si/analyze.py`
- Modify: `python/tests/test_analyze.py`
- Modify: `tests/analyze.spec.ts` (the uv-gated test expecting `overview_only`)

**Interfaces:**
- Consumes: `line.analyze_line`, `mixed_mode.to_mixed_mode`, `mixed_mode.split_mixed_mode_file`, `plots.line_quantity`, `report.write_csv`.
- Produces: `results["summary"]` for lines: `{"through_convention": str | None, "polarity_note": str | None, "modes": {"se" | "dd" | "cc": {"z_ref_ohm", "zc_ohm": {"median", "min", "max", "n_valid"}, "il_db_at_fmax", "fmax_hz", "regions": {...}}}}`; files `line.csv`, `<prefix>insertion_loss.png`, `<prefix>return_loss.png`, `<prefix>characteristic_impedance.png` with prefix `""` (single-ended) or `dd_` / `cc_`; `status == "complete"`.

- [ ] **Step 1: Write the failing tests**

Append to `python/tests/test_analyze.py`:

```python
def test_two_port_line_is_complete_with_csv_and_three_plots(line, tmp_path):
    path, digest = line
    out = run(base(path, digest, tmp_path / "out", device="transmission_line"))
    assert out["status"] == "complete"
    names = {Path(f).name for f in out["files"]}
    assert {"line.csv", "insertion_loss.png", "return_loss.png", "characteristic_impedance.png"} <= names
    assert out["plots"][0]["name"] == "characteristic_impedance"
    se = out["summary"]["modes"]["se"]
    assert se["zc_ohm"]["median"] == pytest.approx(50.0, abs=0.5)
    assert se["zc_ohm"]["n_valid"] == 101
    assert se["il_db_at_fmax"] == pytest.approx(5.0 * 0.020 * (20.0**0.5), abs=0.05)
    header = (Path(out["report_dir"]) / "line.csv").read_text().splitlines()[0]
    assert header == "mode,freq_hz,il_db,rl_in_db,rl_out_db,zc_re_ohm,zc_im_ohm,region"
    assert not any("milestone 4" in w for w in out["warnings"])


def test_four_port_differential_line_reports_dd_and_cc(tmp_path):
    net = fixtures.two_uncoupled_lines_odd_even(freq=fixtures.frequency(npoints=51))
    path = fixtures.write(net, tmp_path / "in", "diff")
    out = run(
        base(
            path, sha256_file(path), tmp_path / "out",
            device="transmission_line", topology="differential_pairs", through_convention="odd_even",
        )
    )
    assert out["status"] == "complete"
    modes = out["summary"]["modes"]
    assert modes["dd"]["zc_ohm"]["median"] == pytest.approx(100.0, abs=1.0)
    assert modes["cc"]["zc_ohm"]["median"] == pytest.approx(25.0, abs=0.25)
    assert out["summary"]["through_convention"] == "odd_even"
    assert "lower" in out["summary"]["polarity_note"]
    names = {Path(f).name for f in out["files"]}
    assert {"dd_characteristic_impedance.png", "cc_insertion_loss.png", "line.csv"} <= names
    rows = (Path(out["report_dir"]) / "line.csv").read_text().splitlines()
    assert rows[1].startswith("dd,") and rows[52].startswith("cc,")


def test_four_port_single_ended_preset_reports_two_paths(tmp_path):
    net = fixtures.two_uncoupled_lines(freq=fixtures.frequency(npoints=21))
    path = fixtures.write(net, tmp_path / "in", "se4")
    out = run(
        base(path, sha256_file(path), tmp_path / "out", device="transmission_line", through_convention="half_split")
    )
    assert out["status"] == "complete"
    assert set(out["summary"]["modes"]) == {"path1", "path2"}
    assert out["summary"]["modes"]["path1"]["zc_ohm"]["median"] == pytest.approx(50.0, abs=0.5)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --project python --frozen --group dev pytest tests/test_analyze.py -k "line_is_complete or dd_and_cc or two_paths" -v`
Expected: 3 failed, `assert 'overview_only' == 'complete'`.

- [ ] **Step 3: Implement the branch**

In `python/dsh_si/analyze.py`:

1. Change the import line to `from . import interpretation, line, lumped, mixed_mode, plots, quality, report`.
2. Add after `LUMPED_PLOTS`:

```python
# (axis label, CSV/summary keys, file stem) per line plot; Z_c draws Re and Im together.
LINE_PLOTS = [
    ("Characteristic impedance (Ω)", [("Re Zc", "zc_re_ohm"), ("Im Zc", "zc_im_ohm")], "characteristic_impedance"),
    ("Insertion loss (dB)", [("IL", "il_db")], "insertion_loss"),
    ("Return loss (dB)", [("RL in", "rl_in_db"), ("RL out", "rl_out_db")], "return_loss"),
]
POLARITY_NOTE = "preset polarity: the lower-numbered port of each pair is P"


def _line_modes(network: Any, interp: dict[str, Any], tolerances: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Name -> analyze_line result: se (2-port), pathN (single-ended 4-port), dd/cc (differential)."""
    ports = interp["ports"]
    if interp.get("input_is_mixed_mode"):
        modes = mixed_mode.split_mixed_mode_file(network)
        return {name: line.analyze_line(net, 1, 2, tolerances) for name, net in modes.items()}
    if network.nports == 2:
        return {"se": line.analyze_line(network, ports["in"][0], ports["out"][0], tolerances)}
    if "pairs" in interp:
        modes = mixed_mode.to_mixed_mode(network, interp["pairs"])
        return {name: line.analyze_line(modes[name], 1, 2, tolerances) for name in ("dd", "cc")}
    out: dict[str, dict[str, Any]] = {}
    for k, (p_in, p_out) in enumerate(zip(ports["in"], ports["out"], strict=True)):
        sub = network.subnetwork([p_in - 1, p_out - 1])
        out[f"path{k + 1}"] = line.analyze_line(sub, 1, 2, tolerances)
    return out


def _summarize_line(result: dict[str, Any]) -> dict[str, Any]:
    valid = np.array([r == "valid" for r in result["regions"]])
    zc = np.asarray(result["values"]["zc_re_ohm"], dtype=float)
    finite = zc[valid & np.isfinite(zc)]
    counts: dict[str, int] = {}
    for label in result["regions"]:
        counts[label] = counts.get(label, 0) + 1
    il = np.asarray(result["values"]["il_db"], dtype=float)
    return {
        "z_ref_ohm": result["z_ref_ohm"],
        "zc_ohm": {
            "median": float(np.median(finite)) if finite.size else None,
            "min": float(finite.min()) if finite.size else None,
            "max": float(finite.max()) if finite.size else None,
            "n_valid": int(finite.size),
        },
        "il_db_at_fmax": float(il[-1]),
        "fmax_hz": float(result["freq_hz"][-1]),
        "regions": counts,
    }


def _write_line(
    modes: dict[str, dict[str, Any]],
    interp: dict[str, Any],
    report_dir: Path,
    name: str,
    subtitle: str,
    files: list[str],
    plot_entries: list[dict[str, str]],
    warnings: list[str],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """line.csv, three PNGs per mode, warnings; returns (summary, report sections)."""
    header = ["mode", "freq_hz", "il_db", "rl_in_db", "rl_out_db", "zc_re_ohm", "zc_im_ohm", "region"]

    def rows():
        for mode, res in modes.items():
            v, f = res["values"], res["freq_hz"]
            for k in range(len(f)):
                yield [mode, float(f[k]), *(float(v[key][k]) for key in header[2:7]), res["regions"][k]]

    files.append(str(report.write_csv(report_dir / "line.csv", header, rows())))
    sections: list[dict[str, Any]] = []
    summary: dict[str, Any] = {
        "through_convention": interp.get("through_convention"),
        "polarity_note": POLARITY_NOTE if interp.get("through_convention") in ("odd_even", "half_split") and "pairs" in interp else None,
        "modes": {},
    }
    single = len(modes) == 1
    for mode, res in modes.items():
        prefix = "" if single else f"{mode}_"
        for ylabel, series, stem in LINE_PLOTS:
            fig = plots.line_quantity(
                res["freq_hz"],
                [(label, res["values"][key]) for label, key in series],
                res["regions"],
                ylabel,
                f"{ylabel.split(' (')[0]} of {name}" + ("" if single else f" ({mode})"),
                subtitle,
            )
            png = plots.save_png(fig, report_dir / f"{prefix}{stem}.png")
            files.append(str(png))
            plot_entries.append({"name": f"{prefix}{stem}", "path": str(png), "title": f"{ylabel} vs frequency ({mode})"})
        for w in res["warnings"]:
            warnings.append(f"{mode}: {w}")
        stats = _summarize_line(res)
        summary["modes"][mode] = stats
        if stats["regions"].get("ambiguous") or stats["regions"].get("singular"):
            warnings.append(
                f"{mode}: {stats['regions'].get('ambiguous', 0)} ambiguous and {stats['regions'].get('singular', 0)} "
                "singular Z_c points are excluded from the headline numbers"
            )
        sections.append(
            {
                "heading": f"Line analysis ({mode}, Z_ref {stats['z_ref_ohm']:g} Ω)",
                "table": {
                    "header": ["Quantity", "Value"],
                    "rows": [
                        ["Z_c median (valid region)", f"{stats['zc_ohm']['median']:.4g} Ω" if stats["zc_ohm"]["median"] is not None else "n/a"],
                        ["Z_c min / max", f"{stats['zc_ohm']['min']:.4g} / {stats['zc_ohm']['max']:.4g} Ω" if stats["zc_ohm"]["median"] is not None else "n/a"],
                        ["IL at f_max", f"{stats['il_db_at_fmax']:.3g} dB at {stats['fmax_hz'] / 1e9:.3g} GHz"],
                        ["Regions", ", ".join(f"{k} {v}" for k, v in stats["regions"].items())],
                    ],
                },
                "text": (summary["polarity_note"] or "") if mode == "dd" else "",
            }
        )
        for entry in plot_entries:
            if entry["name"] == "s_magnitude":
                continue
            if single or entry["name"].startswith(f"{mode}_"):
                sections.append({"heading": entry["title"], "image": entry["path"]})
    return summary, sections
```

3. In `run`, replace the `if interp["device"] in ("inductor", "capacitor"): ... else: warnings.append(...)` block's `else` with:

```python
    elif interp["device"] == "transmission_line":
        modes = _line_modes(network, interp, tolerances)
        line_plots: list[dict[str, str]] = []
        summary, lumped_sections = _write_line(
            modes, interp, report_dir, path.name, subtitle, files, line_plots, warnings
        )
        plot_entries[:0] = line_plots  # key plot first: Z_c
        status = "complete"
    else:
        warnings.append(
            f"{interp['device']} analysis arrives in milestone 4; only the overview is reported"
        )
```

(`lumped_sections` is the existing variable that feeds the HTML sections; reusing it avoids touching the section assembly below. Rename it to `device_sections` throughout `run` if you prefer, in the same commit.)

4. Update the module docstring's second paragraph to: "Lumped elements and transmission lines are complete; interposers are the next PR and still return `overview_only`."

- [ ] **Step 4: Run the Python tests**

Run: `uv run --project python --frozen --group dev pytest tests/test_analyze.py -v`
Expected: all pass. The pre-existing test that expected `overview_only` for a line (search `overview_only` in the file) must be updated to expect `complete` and no milestone-4 warning.

- [ ] **Step 5: Update the TS uv-gated expectation**

In `tests/analyze.spec.ts`, in the test `inspects, then analyzes the line as overview_only with a real report directory`: rename it to `... analyzes the line as complete ...`, change `expect(text).toContain('as transmission_line: status overview_only')` to `'as transmission_line: status complete'`, delete the `Warning: transmission_line analysis arrives in milestone 4` expectation, and add `'line.csv'` and `'characteristic_impedance.png'` to the `existsSync` list.

Run: `source ~/.nvm/nvm.sh && nvm use 22.19.0 && pnpm vitest run tests/analyze.spec.ts`
Expected: pass (the uv block runs only when uv is installed, which it is here).

- [ ] **Step 6: Format and commit**

```bash
uv run --project python --frozen ruff format python/dsh_si python/tests
git add python/dsh_si/analyze.py python/tests/test_analyze.py tests/analyze.spec.ts
git commit -m "feat(python): transmission_line analysis with line.csv, IL/RL/Zc plots, dd/cc modes"
```

---

### Task 9: TypeScript: `singularC` tolerance and the `modes` summary line

**Files:**
- Modify: `src/config.ts`
- Modify: `src/tools/analyze.ts` (`renderAnalyze`)
- Modify: `tests/fixtures/fake-worker.mjs` (new mode `line`)
- Modify: `tests/analyze.spec.ts`

**Interfaces:**
- Consumes: `summary.modes` shape from Task 8.
- Produces: `Config.tolerances.singularC: number` forwarded as `tolerances.singular_c`; rendered line per mode: `  <mode>: Zc median <x> Ω over <n> valid points, IL <y> dB at <f>`.

- [ ] **Step 1: Write the failing test**

Add to `tests/analyze.spec.ts` inside `describe('si_analyze with the fake worker', ...)`:

```ts
  it('renders one summary line per line mode', async () => {
    const ctx = await mount({ pythonCommand: fakeWorker('line') })
    const result = await callTool(ctx, 'si_analyze', { path: '/data/diff.s4p', hash: HASH, interpretation: { device: 'transmission_line', topology: 'differential_pairs', through_convention: 'odd_even' } })
    expect(result.isError).toBe(false)
    const text = textOf(result)
    expect(text).toContain('Analysis of diff.s4p as transmission_line: status complete')
    expect(text).toContain('  dd: Zc median 100.2 Ω over 398 valid points, IL 3.1 dB at 20 GHz')
    expect(text).toContain('  cc: Zc median 25.1 Ω over 401 valid points, IL 3.1 dB at 20 GHz')
    expect(text).toContain('  through_convention: odd_even (preset polarity: the lower-numbered port of each pair is P)')
  })
```

- [ ] **Step 2: Add the fake worker mode**

In `tests/fixtures/fake-worker.mjs`, add a `case 'line':` next to `case 'analyze':` replying:

```js
  case 'line':
    reply({
      protocol: 1,
      ok: true,
      result: {
        path: request.payload.path,
        hash: 'a'.repeat(64),
        device: 'transmission_line',
        status: 'complete',
        report_dir: join(request.payload.output_dir, 'fake'),
        files: [join(request.payload.output_dir, 'fake', 'line.csv')],
        plots: writePlot(request.payload),
        summary: {
          through_convention: 'odd_even',
          polarity_note: 'preset polarity: the lower-numbered port of each pair is P',
          modes: {
            dd: { z_ref_ohm: 100, zc_ohm: { median: 100.2, min: 99.1, max: 101.3, n_valid: 398 }, il_db_at_fmax: 3.1, fmax_hz: 2e10, regions: { valid: 398, ambiguous: 3 } },
            cc: { z_ref_ohm: 25, zc_ohm: { median: 25.1, min: 24.8, max: 25.4, n_valid: 401 }, il_db_at_fmax: 3.1, fmax_hz: 2e10, regions: { valid: 401 } },
          },
        },
        warnings: ['dd: 3 ambiguous and 0 singular Z_c points are excluded from the headline numbers'],
      },
    })
    break
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `pnpm vitest run tests/analyze.spec.ts -t "per line mode"`
Expected: FAIL on the `dd:` line (the current renderer prints `modes: {...}` as JSON).

- [ ] **Step 4: Implement the renderer branch and the tolerance**

In `src/tools/analyze.ts`, inside `renderAnalyze`'s summary loop, before the `if (typeof raw === 'object' ... 'median' in raw)` branch add:

```ts
      if (key === 'modes' && typeof raw === 'object' && raw !== null && !Array.isArray(raw)) {
        for (const [mode, stats] of Object.entries(raw)) {
          if (typeof stats !== 'object' || stats === null || Array.isArray(stats)) continue
          const zc = stats['zc_ohm']
          const median = typeof zc === 'object' && zc !== null && !Array.isArray(zc) ? zc['median'] : null
          const nValid = typeof zc === 'object' && zc !== null && !Array.isArray(zc) ? zc['n_valid'] : 0
          const il = stats['il_db_at_fmax']
          const fmax = stats['fmax_hz']
          const zcText = median === null || median === undefined ? 'Zc undefined' : `Zc median ${trim4(Number(median))} Ω over ${String(nValid)} valid points`
          const ilText = typeof il === 'number' && typeof fmax === 'number' ? `, IL ${trim4(il)} dB at ${formatHz(fmax)}` : ''
          lines.push(`  ${mode}: ${zcText}${ilText}`)
        }
        continue
      }
      if (key === 'through_convention' && typeof raw === 'string') {
        const note = value.summary['polarity_note']
        lines.push(`  through_convention: ${raw}${typeof note === 'string' ? ` (${note})` : ''}`)
        continue
      }
      if (key === 'polarity_note') continue
```

and add at module level:

```ts
function trim4(value: number): string {
  return Number.parseFloat(value.toPrecision(4)).toString()
}
```

In `src/config.ts`, add `singularC: number` to the `tolerances` interface (doc comment: `/** |C| of the ABCD matrix below which Z_c = sqrt(B/C) is reported as singular. */`) and `singularC: Schema.number().min(0).default(1e-9),` in the Schemastery object with `.default({ passivity: 1e-6, reciprocity: 1e-6, singularC: 1e-9 })`. In `src/tools/analyze.ts` `execute`, replace `tolerances: config.tolerances,` with:

```ts
          tolerances: { passivity: config.tolerances.passivity, reciprocity: config.tolerances.reciprocity, singular_c: config.tolerances.singularC },
```

(`si_inspect` keeps passing `config.tolerances`; the Python `quality` module ignores unknown keys, but `singularC` camelCase would be unused there, which is fine.)

- [ ] **Step 5: Run typecheck and the tests**

Run: `pnpm typecheck && pnpm vitest run tests/analyze.spec.ts tests/report-route.spec.ts`
Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/config.ts src/tools/analyze.ts tests/fixtures/fake-worker.mjs tests/analyze.spec.ts
git commit -m "feat: render per-mode line summary; singularC tolerance forwarded to the worker"
```

---

### Task 10: Examples, docs, full check, PR

**Files:**
- Modify: `python/scripts/gen_examples.py`, `examples/synthetic/README.md`
- Modify: `docs/handoff.md`, `CLAUDE.md` (one line), `README.md` (device table row if it has one)

- [ ] **Step 1: Add the odd_even example**

In `python/scripts/gen_examples.py`, next to the `two_uncoupled_lines` entry, add `("two_uncoupled_lines_odd_even", fixtures.two_uncoupled_lines_odd_even())` following the file's existing pattern, then run:

```bash
uv run --project python --frozen --group dev python scripts/gen_examples.py
```

Add a row to `examples/synthetic/README.md`: `| two_uncoupled_lines_odd_even.s4p | same two lines numbered PLTS-style: through 1→2 and 3→4 | differential analysis with through_convention odd_even gives Zc_dd 100 Ω, Zc_cc 25 Ω |`.

- [ ] **Step 2: Docs**

- `CLAUDE.md`, invariants list: change the `lumped.py` bullet to `python/dsh_si/lumped.py and line.py carry the domain owner's equations (module docstrings are their spec) ...` and keep the file under 80 lines.
- `docs/handoff.md`: state = PR #7 `feat/line-analysis` open; next = interposer multiport PR (mode conversion plots, `paths`, per-port RL), and the browser demo. Keep under 60 lines.
- `README.md`: if it lists device support, mark transmission line as supported (IL, RL, Z_c; 2-port and 4-port differential).

- [ ] **Step 3: Full check**

Run: `source ~/.nvm/nvm.sh && nvm use 22.19.0 && pnpm check` (takes over two minutes; run in the background and wait for `exit 0`).
Expected: typecheck, vitest, ruff, pytest all green.

- [ ] **Step 4: Commit, push, PR**

```bash
git add -A
git commit -m "docs: odd_even 4-port example, handoff and CLAUDE.md for line analysis"
git push -u origin feat/line-analysis
gh pr create --base main --title "feat: transmission-line analysis (IL, RL, Zc; single-ended and differential)" --body "<problem, behavior, assumptions, tests run, per docs/plans/dsh-signal-integrity-plan.md section 5>"
```

The PR body must name `select_zc_branch` as the function the domain owner reviews first, and list the spec and this plan.

---

## Self-Review

- Spec coverage: physics (T1–T3), branch contract (T2), modules (T1–T4), interpretation (T5), inspect question (T6), plots (T7), analyze outputs and summary (T8), TS render and tolerance (T9), tests listed in the spec (T1–T9), examples and docs (T10). The spec's `analysis_failed` error code is replaced by the existing `numerical_error` code, so no protocol change and no mirror test change.
- Placeholders: none; every code block is the final form.
- Type consistency: `Region`, `analyze_line` return keys (`freq_hz`, `values`, `regions`, `warnings`, `z_ref_ohm`), `preset_mapping` output (`ports`, `pairs` with `name/p/n`), `to_mixed_mode` keys (`dd`, `cc`, `mixed`), `summary.modes[<mode>]` keys (`z_ref_ohm`, `zc_ohm{median,min,max,n_valid}`, `il_db_at_fmax`, `fmax_hz`, `regions`) are used identically in T8 and T9.
