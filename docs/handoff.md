# Handoff

Short, committed state for the next session (human or agent). Keep it under a screen; history lives in git and `docs/learning-log.html`.

## State (2026-09-06)

- `main`: milestone 1 merged (scaffold, `si_ready`, CI).
- PR #2 `feat/touchstone-inspection`: `si_inspect`, IEEE P370 quality via scikit-rf, synthetic examples, labeled quality output. CI green. Awaiting merge.
- PR #3 `feat/lumped-extraction` (stacked on PR #2): `si_analyze` tool, interpretation validator, report directory (PNG/results.json/HTML), inline images via `ctx.attachments`, `lumped.py` contract with strict-xfail tests, learning log, `CLAUDE.md`, docs budget in CI.
- Dev profile `~/.dsh/profiles/web` links this checkout; `patchReload: startup` because of inotify exhaustion on this host. Credentials in `~/.dsh/.env`.

## Next step

Merge PR #2 then PR #3. Then: real-model demo of inspect → questions → analyze with inline plot (rebuild + restart first). When `lumped.py` lands: CSV per-frequency export and L/Q/C plots in `analyze.py` (`_summarize_lumped` is the hook), then milestone 4 (`line.py`, `multiport.py`, `se2gmm` pairing).

## Waiting on the domain owner

- Equations in `python/dsh_si/lumped.py` (remove each `@PENDING` marker in `python/tests/test_lumped.py` as it lands).
- Interpretation of `examples/realdata/QSFPDD IL_NR1.S4P` (non-reciprocal at every point: partial export?).
- Which `examples/realdata` files, if any, are cleared for redistribution.
- Whether `through` terminal mode for lumped elements is supported now or deferred to fixture de-embedding.

## Gotchas carried forward

See `docs/learning-log.html` page 7. Top three: rebuild + restart before demos; `pkill -f 'bin\.ts web --port 309[9]'`; shell `cd` persists between tool calls.
