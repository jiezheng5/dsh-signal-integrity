# Handoff

Short, committed state for the next session (human or agent). Keep it under a screen; history lives in git and `docs/learning-log.html`.

## State (2026-09-07)

- `main`: milestones 1 to 3 merged (scaffold, inspection, lumped equations with the through-mode split).
- PR #6 `feat/report-link` (open, off `main`): `si_analyze` returns `report_url`, the plugin serves `outputDir` at `/si-reports` on the DSH web server, plus `scripts/dev-restart.sh` and `docs/deployment.md`.
- PR #7 `feat/line-analysis` (open, off `main`, not stacked on #6): milestone 4 part 1. `line.py` (IL, RL, `Z_c = sqrt(B/C)` with `select_zc_branch`), `mixed_mode.py` (odd_even / half_split presets, `se2gmm` into dd and cc, `polarity_check`), `through_convention` question and validation, `line.csv`, IL/RL/Z_c plots, `status: complete` for lines.
- Both PRs were merged locally on the throwaway branch `demo/integration` to run the demo: no code conflicts, only `docs/handoff.md`. Delete that branch once one of them lands.
- Dev profile `~/.dsh/profiles/web` links this checkout; `patchReload: startup` (inotify limits). Cold boot takes 3 to 4 minutes; the socket answers 404 while the tree composes.

## Verified by real-model demo (2026-09-07, DeepSeek-V4-Flash)

`si_inspect` → three questions through `ask_user_question` → `si_analyze` on `examples/synthetic/two_uncoupled_lines_odd_even.s4p` as a differential line. Z_c 100 Ω differential and 25 Ω common, insertion loss 0.447 dB at 20 GHz, all 401 points `valid`, ten files written, and the model handed back the `report_url` as a clickable link that opens the report. The `through_convention` card renders with `odd_even` first and the polarity note in the question line.

## Next step

1. Domain-owner review of `select_zc_branch` in `python/dsh_si/line.py`: selector A is positive-real, selector B is continuity, disagreement is labelled `ambiguous` and excluded from the median while keeping B's value in the CSV and plot.
2. Milestone 4 part 2 (interposer): `paths`, per-port return loss, all directed transmission terms grouped by source port, and the mode-conversion plots (`Sdc21`, `Scd21`) deferred from PR #7.
3. Capture a README asset from the demo session. The one attempt was cropped because Chrome was at a non-default zoom; reset zoom first.

## Open questions

- Interpretation of `examples/realdata/QSFPDD IL_NR1.S4P` (non-reciprocal at every point: partial export?).
- Which `examples/realdata` files, if any, are cleared for redistribution.
- Return loss reads 315 to 350 dB on the ideal synthetic fixture, which is floating-point noise in `|S11|` rather than a real number. Consider clamping the reported value above about 120 dB. Measured data never reaches this.

## Gotchas carried forward

See `docs/learning-log.html` page 7 and `docs/deployment.md`.

- `lib/` currently holds the `demo/integration` build, not either branch. Run `scripts/dev-restart.sh` before trusting any UI behaviour: the model only ever sees the built bundle.
- The DSH session cookie is `SameSite=Strict`, so a report link opened by browser automation (Claude in Chrome, Playwright) gets 401 while the same link clicked inside the chat works. Not a product defect; it does block extension-driven checks of `/si-reports`.
- Never print `~/.dsh/dsh-web.log`; it holds the token URL.
- `skrf.network.a2s` is not exported at the `skrf` top level.

## Future planning

For n > 4 ports, the same two through conventions generalize: odd to even (1-2, 3-4, ...) or i to i + n/2 (1-5, 2-6, ... for s8p). The preset question currently appears for 4-port files only.
