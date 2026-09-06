# dsh-signal-integrity

**Unofficial community plugin for [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) (DSH), independently developed and maintained. Not a DeepSeek project.**

Turns Touchstone S-parameter files into agent-guided signal-integrity reports: the agent inspects the file, asks for the device type and port topology it cannot infer, runs the matching analysis, and hands back plots, CSV data, and an HTML report.

## Status

Milestone 1 of 5 (plugin scaffold). The `si_ready` tool loads into DSH and probes the Python worker. Inspection, lumped-element extraction, and interconnect analysis follow in later pull requests; see [the plan](docs/plans/dsh-signal-integrity-plan.md).

## How it works

```
DSH (web profile)
 └─ dsh-signal-integrity        TypeScript: tool schemas, config, worker client
      │  ctx.subprocess.spawn(uv run --project <plugin>/python python -m dsh_si)
      │  stdin: one JSON request      stdout: one JSON response      stderr: log
      ▼
    dsh_si                       Python: scikit-rf, NumPy, SciPy, Matplotlib
```

Tools (model-facing):

| Tool | Purpose |
|---|---|
| `si_ready` | Probe uv, the Python interpreter, and the scientific packages; explain any missing piece with the exact remedy. |
| `si_inspect` | *(milestone 2)* Parse a Touchstone file, hash it, run passivity, reciprocity, and causality screening, and list the interpretation questions the agent must ask. |
| `si_analyze` | *(milestones 3–4)* Run the device-specific extraction once the interpretation is complete, and write the report. |

## Install

Requirements: Node 22.19+ (or 24+), [uv](https://docs.astral.sh/uv/) on `PATH`. DSH itself runs with `npx @deepseek-ai/dsh`.

From a local checkout (developer path):

```sh
cd dsh-signal-integrity
pnpm install && pnpm build
npx @deepseek-ai/dsh plugin --profile web add /absolute/path/to/dsh-signal-integrity
npx @deepseek-ai/dsh --profile web --dump-config   # shows the signal-integrity row
npx @deepseek-ai/dsh web
```

Then ask the agent to call `si_ready`. The first call runs `uv sync` for the worker, which takes a minute.

Release tarball and GitHub installs are documented with the `v0.1.0` release.

## Configuration

Override in the profile's `cordis.patch.yml` (a patch replaces the row's whole `config`):

```yaml
- id: signal-integrity
  config:
    timeoutMs: 120000
    maxMemoryMb: 2048
    outputDir: ~/.dsh/si-reports
    pythonCommand: []        # e.g. ['/opt/venv/bin/python'] to bypass uv
```

All fields and defaults: [`src/config.ts`](src/config.ts).

## Development

```sh
pnpm install
uv sync --project python --frozen --group dev
pnpm check          # typecheck, vitest, ruff, pytest
```

The TypeScript tests mount the plugin on a real DSH tool registry and the real local subprocess provider, with no model or API key. Most use a fake worker (`tests/fixtures/fake-worker.mjs`) to exercise framing, error classification, and cancellation; two tests run the real worker through uv and skip when uv is absent.

## Assumptions and limits

- The Python worker is spawned through DSH's subprocess seam, which runs **outside** the agent sandbox and without an approval prompt. The worker reads the Touchstone file it is given and writes only under `outputDir`. Review the source before installing, as with any plugin.
- Memory is capped by the worker itself (`RLIMIT_AS` from `maxMemoryMb`); the tool timeout is DSH's cooperative `timeoutMs`.
- No claim of DSH core contribution, upstream merge, or DeepSeek endorsement is made or implied.

## License

MIT
