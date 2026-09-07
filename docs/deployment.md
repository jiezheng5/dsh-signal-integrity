# Deployment (dev runtime)

How this checkout is run inside a local DeepSeek Harness (DSH) checkout for demos and manual testing. End-user installation is a milestone 5 topic (release tarball, `npx @deepseek-ai/dsh web`).

## Layout

| Path | Role |
|---|---|
| `../deepseek-harness` | DSH source checkout, built once; provides the `dsh` CLI (`pnpm dsh`) |
| `~/.dsh/profiles/web` | the `web` profile; its `package.json` lists this plugin as a `link:` dependency and `patchReload: startup` |
| `~/.dsh/.env` (mode 600) | `DEEPSEEK_API_KEY`; DSH loads it itself, never export it in a shell you paste from |
| `~/.dsh/si-reports/` | report directories written by `si_analyze` (config `outputDir`) |

## One-time setup

```bash
source ~/.nvm/nvm.sh && nvm use 22.19.0          # Node 22.19+; pnpm 11.7.0 via corepack
cd ../deepseek-harness && pnpm install && pnpm run build
pnpm dsh plugin --profile web add ../dsh-signal-integrity   # links the checkout into the profile
pnpm dsh --profile web --dump-config | grep -n signal-integrity   # row present?
```

`--profile` follows `plugin`; `--dump-config` never follows `plugin`. On this host the profile uses `patchReload: startup` because the live watcher exhausts inotify (`ENOSPC`); do not switch it back to `live`.

## Routine redeploy

```bash
scripts/dev-restart.sh                 # build, stop old dsh web, start new, open browser
scripts/dev-restart.sh --no-open       # headless
scripts/dev-restart.sh --no-build      # Python or docs changes only
scripts/dev-restart.sh --fg            # foreground, Ctrl-C stops it
```

What it does, and why each step exists:

1. `pnpm build` here. The model only sees `lib/index.js`; an unbuilt `src/` change makes it improvise around missing tools.
2. Stop every `dsh web` started from the source checkout (pattern `apps/cli/src/bin.ts web`, any port). The profile loads plugins at startup, so a running server keeps the old bundle.
3. Start `pnpm dsh web` from the harness checkout, detached, log at `~/.dsh/dsh-web.log` (mode 600 because the log contains the token URL). Waits until the port answers.

## Verify

1. In the Web UI, ask "is the signal-integrity tool ready?" The model must call `si_ready` and report the worker's Python and package versions.
2. Analyze `examples/synthetic/series_rl_10nH.s1p` as an inductor. The final answer should carry an `http://127.0.0.1:3080/si-reports/...` link that opens `report.html`; the tool card shows the inductance plot inline.

## Gotchas

- Never paste the token URL, the log, or `.env` into chat, docs, or commits.
- Manual stop: `pkill -f 'apps/cli/src/bin.ts we[b]'`. Without the brackets the pattern also matches the shell that runs it.
- `dsh web` alone means `--profile web`; the CLI hardcodes that alias.
