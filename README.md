# dsh-signal-integrity

**Unofficial community plugin for [DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness) (DSH), independently developed and maintained. Not a DeepSeek project.**

Turns Touchstone S-parameter files into agent-guided signal-integrity reports: the agent inspects the file, asks for the device type and port topology it cannot infer, runs the matching analysis, and hands back plots, CSV data, and an HTML report.

## Status

Milestone 3 of 5 complete (lumped-element extraction). `si_ready` probes the Python worker; `si_inspect` parses, hashes, and quality-screens a file, returns an |S| overview plot, and hands the agent the questions it must ask; `si_analyze` validates the answers, refuses a changed file, and writes a report directory (PNG, CSV, results.json, HTML). Inductors and capacitors are extracted per frequency (L, Q, R or C, ESR) with the self-resonance located and invalid regions labeled; transmission lines and interposers still report `status: overview_only` until milestone 4. See [the plan](docs/plans/dsh-signal-integrity-plan.md) and the [learning log](docs/learning-log.html).

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
| `si_inspect` | Parse a Touchstone file, hash it, run passivity, reciprocity, and causality screening, and return the interpretation questions (shaped for `ask_user_question`) the agent must ask. |
| `si_analyze` | Validate the interpretation (device, terminal mode, ports, pairs, paths), refuse a changed file by hash, run the device analysis, and write `<outputDir>/analyze/<file>-<hash8>-<stamp>/` with `s_magnitude.png`, `results.json`, `report.html`, plus `lumped.csv` and one PNG per extracted quantity for inductors and capacitors. Returns a bounded summary and the key plot inline. |

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

Then ask the agent to call `si_ready`. The first call runs `uv sync` for the worker, which takes a minute. Next, point it at a file: "Inspect `<repo>/examples/synthetic/lossy_line_20mm.s2p`". The [synthetic examples](examples/synthetic/README.md) list the expected result for each file.

### Model credentials

DSH reads provider keys from the launch environment or from `$DSH_HOME/.env` (default `~/.dsh/.env`). Keep keys out of shell history and chat:

```sh
umask 077
printf 'DEEPSEEK_API_KEY=%s\n' "$YOUR_KEY_VARIABLE" > ~/.dsh/.env
```

The URL `dsh web` prints carries a per-launch browser-trust token. Treat it like a password: do not paste it into issues, chats, or documentation. It is bound to 127.0.0.1 and rotates on every restart.

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

A profile that links this checkout loads `lib/index.js`, so run `pnpm build` and restart `dsh web` after changing TypeScript; the model only sees tools that exist in the built bundle.

The TypeScript tests mount the plugin on a real DSH tool registry and the real local subprocess provider, with no model or API key. Most use a fake worker (`tests/fixtures/fake-worker.mjs`) to exercise framing, error classification, and cancellation; two tests run the real worker through uv and skip when uv is absent.

## Reports and plots

Every `si_analyze` call leaves a directory under `outputDir` (default `~/.dsh/si-reports/analyze/`): the |S| overview PNG, `results.json` (input hash, library versions, settings, quality, warnings, summary), and a self-contained `report.html`. `si_inspect` writes the same overview under `inspect/`. When DSH's attachment service is mounted (it is in the web profile) the plot also comes back inline in the chat as an image; otherwise the path is reported. Plots follow one rule set: one axis, fixed eight-color order (reflections first, then the strongest transmissions), units on every axis, assumptions in the subtitle.

## Lumped-element extraction

Terminal interpretation is asked, never guessed, because the same 2-port file can mean three circuits:

| `terminal_mode` | Impedance used | Circuit |
|---|---|---|
| `one_port` | Z11 | element from port 1 to ground |
| `two_terminal_differential` | Z11 + Z22 − Z12 − Z21 | element floating between the ports (series arms of the T-circuit) |
| `through` | 1 / Y11 | series element in a through fixture (Pi-circuit series arm, ideal fixture) |

From Z(f): L = Im(Z)/ω, Q = Im(Z)/Re(Z), R = Re(Z) for inductors; C = −1/(ω·Im(Z)), ESR = Re(Z) for capacitors. The first sign change of Im(Z) is the self-resonance (linearly interpolated). Every point is labeled `valid`, `near_srf` (within 10 % of the SRF), `beyond_srf`, `wrong_sign`, or `dc`; headline numbers (median, min, max) use valid points only, plots shade the rest, and the CSV carries every point with its label. A wrong-sign point becomes NaN, never a negative component value.

## Quality checks

Two layers are reported together. The IEEE P370 metrics come from scikit-rf's `IEEEP370_FD_QM`, the only open-source Python implementation of the standard's frequency-domain quality checks, and carry the standard's evaluation bands (good, acceptable, inconclusive, poor). The exact per-frequency checks are computed by this plugin and say *where* a problem is.

| Check | IEEE P370 metric (verdict) | Exact detail (location) |
|---|---|---|
| Passivity | PQMi score and band | largest singular value of S per frequency vs `1 + tolerances.passivity`; worst point, violating count |
| Reciprocity | RQMi score and band | max \|Sij − Sji\| per frequency vs `tolerances.reciprocity`; worst point, violating count |
| Causality | CQMi score and band (screening, not a proof) | none: causality has no exact per-frequency form on sampled data |

One-ports get the exact passivity check only; the P370 metrics need off-diagonal terms. References: [scikit-rf IEEE P370 example](https://scikit-rf.readthedocs.io/en/latest/examples/networktheory/IEEEP370%20Deembedding.html), [MATLAB `ieee370QualityCheckFrequencyDomain`](https://www.mathworks.com/help/rf/ref/ieee370qualitycheckfrequencydomain.html) for the reference implementation's behavior.

## Assumptions and limits

- The Python worker is spawned through DSH's subprocess seam, which runs **outside** the agent sandbox and without an approval prompt. The worker reads the Touchstone file it is given and writes only under `outputDir`. Review the source before installing, as with any plugin.
- Memory is capped by the worker itself (`RLIMIT_AS` from `maxMemoryMb`); the tool timeout is DSH's cooperative `timeoutMs`.
- No claim of DSH core contribution, upstream merge, or DeepSeek endorsement is made or implied.

## License

MIT
