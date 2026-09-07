# Handoff

Short, committed state for the next session (human or agent). Keep it under a screen; history lives in git and `docs/learning-log.html`.

## State (2026-09-07)

- `main`: milestone 1 merged (scaffold, `si_ready`, CI).
- PR #2 `feat/touchstone-inspection` (open, against `main`): now carries milestone 2 and, since PR #3 merged into it, milestone 3's pipeline.
- PR #4 `feat/lumped-equations` (stacked on `feat/touchstone-inspection`): the domain owner's equations implemented in `lumped.py` (one_port, two_terminal_differential, through = 1/Y11), SRF and region labels, `lumped.csv`, one PNG per quantity with shaded invalid regions, headline summary over valid points only. README section "Lumped-element extraction".
- Dev profile `~/.dsh/profiles/web` links this checkout; `patchReload: startup` because of inotify exhaustion on this host. Credentials in `~/.dsh/.env`.
- `docs/resume-project.tex`: three resume variants for this project (untracked until the user decides whether it belongs in the repo).

## Next step

Merge PR #2, then PR #4. Rebuild + restart, then a real-model demo: inspect → questions → analyze on `examples/synthetic` inductor/capacitor files with the inline L or C plot; capture for README. Then milestone 4: `line.py` (IL, RL, `Z_c = sqrt(B/C)` with the user's `select_zc_branch`; their docstring also gives `Z_c = Z_ref * sqrt(((1+S11)^2 - S12 S21)/((1-S11)^2 - S12 S21))`), `multiport.py`, `se2gmm` pairing.

## Waiting on the domain owner

- Confirm `through` = 1/Y11 (Pi-circuit series arm plus port-1 shunt leg, ideal fixture) is the intended reading, or whether -1/Y12 is preferred.
- Confirm the 10 % near-SRF band and "first crossing only" SRF policy.
- Interpretation of `examples/realdata/QSFPDD IL_NR1.S4P` (non-reciprocal at every point: partial export?).
- Which `examples/realdata` files, if any, are cleared for redistribution.

## Gotchas carried forward

See `docs/learning-log.html` page 7. Top three: rebuild + restart before demos; `pkill -f 'bin\.ts web --port 309[9]'`; shell `cd` persists between tool calls.
