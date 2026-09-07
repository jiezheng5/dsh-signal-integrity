# Handoff

Short, committed state for the next session (human or agent). Keep it under a screen; history lives in git and `docs/learning-log.html`.

## State (2026-09-07)

- `main`: milestones 1 to 3 merged (PR #5 landed the lumped equations, through-mode split, CSV, per-quantity PNGs).
- Branch `feat/report-link` (PR #6): `si_analyze` returns `report_url` and the plugin serves `outputDir` under `/si-reports` on the DSH web server (`ctx.inject(['connection','webServer'])`, cookie auth via `requestRejection`, realpath containment, extension allowlist). Also `scripts/dev-restart.sh` and a rewritten `docs/deployment.md`.
- Dev profile `~/.dsh/profiles/web` links this checkout; `patchReload: startup` because of inotify exhaustion on this host. Credentials in `~/.dsh/.env`. Cold boot 3 to 4 minutes; the socket answers 404 while composing.
- Milestone 4 scope agreed: first PR is `line.py` only (2-port single-ended and 4-port differential IL, RL, Z_c); interposer multiport is a second PR.

## Next step

1. Real-model demo in the browser (Claude-in-Chrome was not connected): inspect → questions → analyze `examples/synthetic/series_rl_10nH.s1p`; confirm the final answer carries the `http://127.0.0.1:3080/si-reports/...` link and the tool card shows the inline plot; capture for README.
2. Milestone 4 brainstorm, remaining questions: Z_c branch selection contract (`select_zc_branch` is the domain owner's), which port-mapping question `si_inspect` asks for 4-port (odd/even vs i, i+n/2 pairing), and whether IL/RL for differential use `Sdd21`/`Sdd11` only.

## Waiting on the domain owner

- Interpretation of `examples/realdata/QSFPDD IL_NR1.S4P` (non-reciprocal at every point: partial export?).
- Which `examples/realdata` files, if any, are cleared for redistribution.

## Gotchas carried forward

See `docs/learning-log.html` page 7 and `docs/deployment.md`. Top three: rebuild + restart before demos (`scripts/dev-restart.sh`); never print `~/.dsh/dsh-web.log` (token URL); shell `cd` persists between tool calls.

## Future planning

For n > 2 ports, ask whether to treat ports as single-ended or differential pairs; common through topologies: odd to even (1-2, 3-4, ...) or i to i + n/2 (1-5, 2-6, ... for s8p).
