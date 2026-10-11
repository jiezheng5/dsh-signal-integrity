# Transmission-line analysis (milestone 4, PR 1 of 2)

Status: approved design, 2026-09-07. Owner of the equations: Jie Zheng. Second PR (interposer multiport, mode-conversion plots) is out of scope here.

## Goal

`si_analyze` with `device: transmission_line` produces insertion loss, return loss, and complex characteristic impedance for a 2-port single-ended line and for a 4-port differential line (differential and common mode), with the same report shape as the lumped devices: CSV, per-quantity PNGs, valid-region summary, `status: complete`.

## Decisions taken during brainstorming

| Question | Decision |
|---|---|
| Scope of first PR | `line.py` and `mixed_mode.py` only; interposer later |
| Z_c branch selection | Both selectors (positive-real per point, continuity from the low-frequency anchor); points where they disagree are labelled `ambiguous` |
| Differential outputs | Differential and common mode (IL, RL, Z_c for each); no mode-conversion terms yet |
| 4-port port mapping | Preset question `through_convention` with `odd_even` listed first, then `half_split`, then `custom` |
| Preset polarity | Lower port number of a pair is P; the report states this assumption. Proven safe: IL, RL and Z_c are invariant under a P/N swap (a swap negates S21 and S12, hence all four ABCD terms, leaving B/C fixed), so no question is asked. `mixed_mode.polarity_check` warns when the through phase extrapolates to 180 degrees at DC. |

## Physics (domain owner's equations)

Reference impedance `Z_ref` is the file's port impedance (per mode after conversion: differential `2·Z0`, common `Z0/2`).

```text
IL  = -20 log10 |S21|          positive dB, "out" port from "in" port
RL_in  = -20 log10 |S11|,  RL_out = -20 log10 |S22|
ABCD from S (scikit-rf network.a); Z_c = ± sqrt(B / C)
equivalent closed form (symmetric reciprocal line):
  Z_c = Z_ref * sqrt(((1+S11)^2 - S12 S21) / ((1-S11)^2 - S12 S21))
```

`select_zc_branch(candidates, freq_hz) -> (zc, regions)` is written by the domain owner. Contract:

- `candidates`: complex array shape `(n, 2)`, the two roots per frequency.
- Selector A: the root with `Re > 0`; when both or neither qualify, mark `ambiguous`.
- Selector B: `Re > 0` at the first finite point, then the root nearest the previous accepted value.
- Output `zc` follows selector B; `regions[i]` is `valid` when A and B agree, `ambiguous` when they differ, `singular` when `|C|` is below `tolerances.singular_c` (default `1e-9`) or the root is not finite. Singular points carry `NaN`.

Symmetry (`|S11 - S22|`) and reciprocity (`|S12 - S21|`) beyond `tolerances.reciprocity` produce warnings, never refusals; the Z_c is still computed from the ABCD matrix, which does not assume symmetry.

## Modules

### `python/dsh_si/line.py`

Pure 2-port math on a scikit-rf `Network`; no file or report knowledge.

```python
def insertion_loss_db(network, in_port: int, out_port: int) -> np.ndarray
def return_loss_db(network, port: int) -> np.ndarray
def zc_candidates(network) -> np.ndarray            # (n, 2) complex, ±sqrt(B/C), NaN where |C| < tol
def select_zc_branch(candidates, freq_hz) -> tuple[np.ndarray, list[Region]]   # domain owner
def analyze_line(network, in_port, out_port, tolerances) -> dict
    # {"values": {"il_db", "rl_in_db", "rl_out_db", "zc_re_ohm", "zc_im_ohm"},
    #  "regions": [...], "warnings": [...], "z_ref_ohm": float}
```

`Region = Literal["valid", "ambiguous", "singular"]`. Ports are 1-based in the interpretation and converted to 0-based at the scikit-rf boundary inside this module.

### `python/dsh_si/mixed_mode.py`

Port-mapping presets and the single-ended → mixed-mode conversion.

```python
PRESETS = {
    "odd_even":   through (1,2),(3,4)...; pairs (1,3),(2,4)...   # PLTS-style
    "half_split": through (1,1+n/2)...;   pairs (1,2),(3,4)...
}
def resolve_mapping(interp, n_ports) -> dict   # fills ports {in,out} and pairs [{name,p,n}] from a preset
def to_mixed_mode(network, pairs) -> dict      # {"dd": Network, "cc": Network}
```

`to_mixed_mode` reorders ports to `[P1, N1, P2, N2]` (scikit-rf's `se2gmm` pairs adjacent ports and connects port k through to k+2), calls `se2gmm(p=2)`, then extracts the differential 2-port (mixed ports 1,2) and the common 2-port (mixed ports 3,4) as scikit-rf sub-networks with their converted reference impedances. When `input_is_mixed_mode` is true, conversion is skipped and the file's port order is taken as `[d_in, d_out, c_in, c_out]`; the data is never converted twice.

### `python/dsh_si/interpretation.py`

New optional field for `transmission_line`: `through_convention ∈ {odd_even, half_split, custom}`. For n = 2 it is ignored (`ports` defaults to in `[1]`, out `[2]`). For n = 4: a preset derives `ports` and, when `topology == differential_pairs`, `pairs`; `custom` requires the existing free-form fields. n other than 2 or 4 stays a validation error for lines.

### `python/dsh_si/inspect.py`

For a 4-port file, `build_questions` adds after `topology`:

```text
id: through_convention
question: Which ports connect through the line?
options (in this order):
  odd_even   "1→2 and 3→4 are the through paths (pairs 1/3 and 2/4)."
  half_split "1→3 and 2→4 are the through paths (pairs 1/2 and 3/4)."
  custom     "Enter the port lists yourself."
```

### `python/dsh_si/analyze.py`

`device == transmission_line` branch: resolve mapping → for single-ended run `analyze_line` once; for differential run `to_mixed_mode` then `analyze_line` on `dd` and on `cc`. Write `line.csv` (one file, mode column), PNGs `insertion_loss.png`, `return_loss.png`, `characteristic_impedance.png` (differential run: prefixed `dd_` and `cc_`), key plot first = Z_c. Summary per mode: `zc_ohm` median over `valid`, `il_db_max_freq`, region counts, `through_convention`, polarity note. Status `complete`. The "arrives in milestone 4" warning is removed for lines; interposers keep it.

### `python/dsh_si/plots.py`

One new figure: `line_quantity(f, y, ylabel, regions)` reusing the region shading of `lumped_quantity`; Z_c plot draws Re and Im as two series. No new plot library.

### TypeScript

`Config.tolerances` gains `singularC` (Schemastery number, default `1e-9`), forwarded to the worker as `tolerances.singular_c`. Otherwise no schema change: `summary` is `additionalProperties: true`. `renderAnalyze` gains one branch: when `summary` has `modes`, print one line per mode (`dd: Zc median 100.2 Ω over 398 valid points, IL 3.1 dB at 20 GHz`). Fake worker gets a `line` mode fixture.

## Error handling

- Non-2/4-port file with `device: transmission_line` → `interpretation_invalid`.
- `custom` without `ports` → `interpretation_invalid` listing the missing field.
- Singular `C` at a point → `NaN` Z_c, region `singular`, no exception.
- se2gmm failure (should not happen for 4 distinct ports) → `WorkerError("analysis_failed")` with the scikit-rf message; new code added to `protocol.py` on both sides (mirror test).

## Tests

Python (`python/tests/test_line.py`, `test_mixed_mode.py`, fixtures in `fixtures.py`):

- Analytic lossy line: `Z_c` recovers 50 Ω within 0.5 Ω over the band; IL matches the loss model within 0.05 dB; RL is large (> 40 dB) for the matched line.
- Branch flip fixture: candidates constructed so selector A alone would pick the wrong root at one point → region `ambiguous` there, `valid` elsewhere.
- Singular point: `C = 0` at one frequency → `NaN` and `singular`.
- `two_uncoupled_lines.s4p` with `half_split`: `Zc_dd = 100 Ω`, `Zc_cc = 25 Ω`, dd IL equals the single line IL.
- Same network renumbered to odd_even order analysed with `odd_even` gives the same dd/cc results.
- Swapping P and N in one pair negates that side's differential wave: `Sdd21` flips phase by 180° (asserted on the intermediate mixed-mode network) while `|Sdd21|`, IL, and `Zc_dd` are unchanged. Mode conversion stays zero for the uncoupled fixture, so no sign test on `Sdc21`.
- `interpretation.normalize`: presets fill `ports`/`pairs`; `custom` without ports fails; 3-port line fails.
- `inspect.build_questions` for n = 4 includes `through_convention` with `odd_even` first.
- `analyze.run` end to end on the synthetic 2-port and 4-port files writes the CSV and three (or six) PNGs and returns `status: complete`.

TypeScript: `tests/analyze.spec.ts` renders the fake line summary; `protocol-mirror.spec.ts` covers the new error code.

## Out of scope

Mode conversion plots, interposer multiport report, RLGC, TDR, fixture de-embedding, `examples/realdata` redistribution.
