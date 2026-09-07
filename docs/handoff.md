# Handoff

Short, committed state for the next session (human or agent). Keep it under a screen; history lives in git and `docs/learning-log.html`.

## State (2026-09-07)

- `main`: milestone 1 merged (scaffold, `si_ready`, CI).
- `main` also has PR #2 (milestone 2 + milestone 3 pipeline). PR #4 merged into the wrong base 19 s after PR #2 merged, so its commits never reached `main`.
- PR #5 `feat/lumped-to-main` (against `main`): everything from PR #4 (equations in `lumped.py`, SRF and region labels, `lumped.csv`, per-quantity PNGs, valid-region summary), plus the through mode split into `through_port2_grounded` = 1/Y11 (V2 = 0) and `through_port2_open` = Z11 (I2 = 0), both exact, plus resume/deployment docs. Merge this one; do not stack on it.
- Dev profile `~/.dsh/profiles/web` links this checkout; `patchReload: startup` because of inotify exhaustion on this host. Credentials in `~/.dsh/.env`.

## Next step

Rebuild + restart, then a real-model demo: inspect → questions → analyze on `examples/synthetic` inductor/capacitor files with the inline L or C plot; capture for README. Then milestone 4: `line.py` (IL, RL, `Z_c = sqrt(B/C)` with the user's `select_zc_branch`; their docstring also gives `Z_c = Z_ref * sqrt(((1+S11)^2 - S12 S21)/((1-S11)^2 - S12 S21))`), `multiport.py`, `se2gmm` pairing.

## Waiting on the domain owner

- Interpretation of `examples/realdata/QSFPDD IL_NR1.S4P` (non-reciprocal at every point: partial export?).
- Which `examples/realdata` files, if any, are cleared for redistribution.

## Gotchas carried forward

See `docs/learning-log.html` page 7. Top three: rebuild + restart before demos; `pkill -f 'bin\.ts web --port 309[9]'`; shell `cd` persists between tool calls.

## Future Planning
maybe for snp, n > 2 ports, asking user whether it should be modified as single-ended or differential paris, if yes, through topology, industry common practice are either:
- odd to even, e.g. s8p: 1 - 2, 3 - 4, 5 - 6, 7 - 8, ...
- i to i + n / 2, e.g.s8p: 1 - 5, 2 - 6, 3 - 7, 4 - 8, ... 
