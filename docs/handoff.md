# Handoff

Short, committed state for the next session (human or agent). Keep it under a screen; history lives in git and `docs/learning-log.html`.

## State (2026-09-06)

- `main`: milestone 1 merged (scaffold, `si_ready`, CI).
- PR #2 `feat/touchstone-inspection`: `si_inspect`, IEEE P370 quality via scikit-rf, synthetic examples, labeled quality output. CI green. Awaiting merge.
- `feat/lumped-extraction` (stacked on PR #2): `python/dsh_si/lumped.py` contract with strict-xfail tests; `.gitignore` for `examples/realdata`; learning log; `CLAUDE.md`.
- Dev profile `~/.dsh/profiles/web` links this checkout; `patchReload: startup` because of inotify exhaustion on this host. Credentials in `~/.dsh/.env`.

## Next step

Milestone 3 on `feat/lumped-extraction`: `si_analyze` skeleton (interpretation validation, hash check, report dir, `results.json`), `python/dsh_si/report.py` (Matplotlib PNG, HTML, CSV), inline image return through `ctx.attachments.saveImage`, an |S| overview plot for `si_inspect`. Then wire `lumped.py` once the domain owner fills it.

## Waiting on the domain owner

- Equations in `python/dsh_si/lumped.py` (remove each `@PENDING` marker in `python/tests/test_lumped.py` as it lands).
- Interpretation of `examples/realdata/QSFPDD IL_NR1.S4P` (non-reciprocal at every point: partial export?).
- Which `examples/realdata` files, if any, are cleared for redistribution.
- Whether `through` terminal mode for lumped elements is supported now or deferred to fixture de-embedding.

## Gotchas carried forward

See `docs/learning-log.html` page 7. Top three: rebuild + restart before demos; `pkill -f 'bin\.ts web --port 309[9]'`; shell `cd` persists between tool calls.
