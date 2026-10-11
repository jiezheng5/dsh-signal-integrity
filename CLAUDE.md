# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Unofficial community plugin for DeepSeek Harness (DSH): TypeScript tools (`src/`) that spawn a Python worker (`python/dsh_si/`) to analyze Touchstone S-parameter files. Never describe it as official or merged upstream. Plan and milestones: `docs/plans/dsh-signal-integrity-plan.md`. Narrative of decisions and lessons: `docs/learning-log.html`. Session hand-off: `docs/handoff.md`.

## Commands

```sh
source ~/.nvm/nvm.sh && nvm use 22.19.0      # Node 22.19+ required; pnpm 11.7.0 via corepack
pnpm install && uv sync --project python --frozen --group dev
pnpm check                                    # typecheck + vitest + ruff + pytest (run before every push)
pnpm typecheck                                # tsc --noEmit over src and tests
pnpm test                                     # vitest; uv-dependent tests self-skip without uv
pnpm vitest run tests/inspect.spec.ts -t "relative path"   # one TS test
pnpm test:py                                  # pytest in python/
uv run --project python --frozen --group dev pytest tests/test_inspect.py -k oneport   # one Python test
pnpm lint:py                                  # ruff (formatter owns line length; E501 ignored)
uv run --project python --frozen ruff format dsh_si tests
pnpm build                                    # tsc -> lib/types, tsdown -> lib/index.js
uv run --project python --frozen --group dev python scripts/gen_examples.py   # regenerate examples/synthetic
```

Dev runtime is the sibling checkout `../deepseek-harness` (built once with `pnpm install && pnpm run build`). From there: `pnpm dsh plugin --profile web add ../dsh-signal-integrity`, `pnpm dsh --profile web --dump-config`, `pnpm dsh web --no-open`. `--profile` follows `plugin`; `--dump-config` never follows `plugin`.

## Architecture in one paragraph

DSH loads `lib/index.js` by package name through the profile's bundle list (`cordis.patch.yml` inserts row `signal-integrity`). `src/index.ts` exports `name`, `inject = ['tools','subprocess']`, a Schemastery `Config`, and `apply`, which registers `defineTool` tools. Each tool call spawns one worker process via `ctx.subprocess.spawn` (`src/worker.ts`): argv `uv run --project <pkg>/python --frozen --no-dev python -m dsh_si`, one JSON request on stdin, one JSON response on stdout, stderr capped. `src/protocol.ts` and `python/dsh_si/protocol.py` are the same contract; `tests/protocol-mirror.spec.ts` fails CI if they drift. The worker (`python/dsh_si/__main__.py`) dispatches `ready` / `inspect` / `analyze`, applies `RLIMIT_AS` to itself, and answers structured errors with codes from `protocol.py`. Tools turn file-domain codes into tool errors and infrastructure codes into "call `si_ready`".

## Invariants that are easy to break

- **The model only sees the built bundle.** After any `src/` change: `pnpm build`, then restart `dsh web`. Otherwise the model improvises around missing tools.
- `Config` is Schemastery (`import Schema from '@deepseek-ai/schemastery'`), never zod: Cordis validates through Standard Schema at load.
- Every `@deepseek-ai/*` import is a `peerDependency` + `devDependency` and stays external in `tsdown.config.ts`, so the plugin shares the installation's Cordis instance.
- Object nodes in `defineTool` `parameters` and `output.schema` must declare `additionalProperties`.
- `ctx.subprocess.spawn` has no timeout, no rlimits, no sandbox. Deadlines come from `timeoutMs` + `exec.signal`; memory from the worker's own `setrlimit`.
- Tool contract: throw only for infrastructure failures; a not-ready environment or a bad file is a *result* (`si_ready`) or a domain error with the worker's message (`si_inspect`).
- `si_inspect` returns `questions` shaped exactly for `ask_user_question`; tools must not call `ctx.userQuestions.ask` themselves (fails under subagents).
- `python/dsh_si/lumped.py` and `line.py` carry the domain owner's equations (the module docstrings are their spec). Change a formula only when they ask; keep the closed-form fixtures in `python/tests/` in step.
- `examples/realdata/` is gitignored measured data; never `git add -f` it. Examples for the public repo live in `examples/synthetic/`.

## Testing pattern

TS tests mount the plugin on a bare `Context` with `SystemPrompt`, `ToolRuntime`, and the real `LocalSubprocessRuntime` (`tests/harness.ts`) and call `ctx.tools.execute`; no model, no key. Most use `tests/fixtures/fake-worker.mjs` via `pythonCommand` to exercise framing, error routing, and cancellation; `*.uv.spec.ts` and the uv blocks run the real worker and `describe.skipIf(!uvAvailable())`. Python tests build networks in `python/tests/fixtures.py` and write Touchstone files to `tmp_path`.

## Working agreements

- Small commits with conventional-commit subjects; push the feature branch and open a PR per milestone with problem, behavior, assumptions, tests run.
- Never paste the `dsh web` token URL, API keys, or `.env` contents into chat, docs, or commits. Credentials go in `~/.dsh/.env` (mode 600).
- Use `superpowers:brainstorming` before new features, `superpowers:test-driven-development` while implementing, `superpowers:verification-before-completion` before claiming green.
- End of session: run `/remember` (Remember plugin, writes `.remember/`, gitignored) and overwrite `docs/handoff.md` (committed) with state, next step, and open questions.
- Maintenance of this file: replace, never append. Keep only what a fresh session cannot derive from the repo; delete lessons once the code makes them obvious. CI fails above 80 lines here and 60 in `docs/handoff.md`. Audit at milestone boundaries with `claude-md-management:claude-md-improver`.
