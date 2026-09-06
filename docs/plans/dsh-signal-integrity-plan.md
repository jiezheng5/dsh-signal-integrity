# Build, publish, and showcase `dsh-signal-integrity`

## Goal

Build an unofficial, standalone community plugin for DeepSeek Harness that analyzes Touchstone files and generates signal-integrity reports. The finished public project must give hiring managers and recruiters concrete evidence of strength in:

- **Agent development:** typed DSH tools, stateful clarification of device type and port topology, structured tool results, cancellation, and error handling.
- **Signal integrity and computational electromagnetics:** defensible S-parameter interpretation, mixed-mode conversion, network-quality diagnostics, and device-specific extraction.
- **Software engineering:** TypeScript/Python integration, reproducible numerical tests, CI, packaging, versioned releases, and clear technical documentation.
- **AI for EDA:** an agent workflow that collects missing engineering context before selecting and running the correct analysis.

Success does not depend on merging code into `deepseek-ai/deepseek-harness`. It means another person can discover the plugin, install a pinned release into DSH, reproduce the examples, inspect the validation evidence, and understand its engineering assumptions.

## 1. Contribution route and project location

Build a **standalone community plugin**, using the existing DSH clone only as the development runtime and API reference.

The project currently does not accept external pull requests and explicitly encourages independent plugin repositories. The recent local merge commits name branches such as `deepseek-harness/release/...` and `deepseek-harness/fix/...`; these are same-repository branches and therefore come from maintainers or other collaborators with write access. Public Git history does not prove whether each contributor is a DeepSeek employee. [Current contribution guide](https://github.com/deepseek-ai/deepseek-harness/blob/master/CONTRIBUTING.md)

Use this layout:

```text
/media/brittany/internal_drive_d/AIProjects/
├── deepseek-harness/         # Existing upstream clone and development runtime
└── dsh-signal-integrity/     # Your own Git repository
    ├── src/                 # TypeScript plugin and Python process adapter
    ├── python/              # RF calculations and report generation
    ├── tests/               # Numerical and integration tests
    ├── examples/            # Synthetic Touchstone files and sample reports
    ├── package.json         # npm package, build, dependencies, bundle declaration
    ├── pyproject.toml       # Python package and dependencies
    ├── cordis.patch.yml     # Enables the installed plugin
    └── README.md            # Installation, demonstration, assumptions
```

The two repositories have separate histories and remotes:

| Local repository | `origin` | Main branch | Purpose |
|---|---|---|---|
| `deepseek-harness` | `https://github.com/deepseek-ai/deepseek-harness.git` | `master` | Read-only upstream runtime and reference checkout |
| `dsh-signal-integrity` | `https://github.com/<username>/dsh-signal-integrity.git` | `main` | Public portfolio project, releases, issues, and PRs |

Do not place the community plugin under DSH's `packages/` or `.agents/`. The plugin is loaded by DSH but is not merged into the DSH Git history.

Create the plugin repository before using `dsh plugin add`:

```bash
cd /media/brittany/internal_drive_d/AIProjects
mkdir dsh-signal-integrity
cd dsh-signal-integrity
git init -b main
git remote add origin https://github.com/jiezheng5/dsh-signal-integrity.git
```

For each milestone, synchronize `main`, create a feature branch, implement and validate the change, push it, and open a PR back to the plugin's own `main`:

```bash
git switch main
git pull --ff-only origin main
git switch -c feat/plugin-scaffold

# Implement and test the milestone.

git add .
git commit -m "feat: scaffold signal integrity plugin"
git push -u origin feat/plugin-scaffold
```

Describe the result as an **unofficial community plugin for DeepSeek Harness, independently developed and maintained**. Do not claim a DSH core contribution or upstream merge unless DeepSeek later accepts and merges a separate PR.

## 2. Setup and first working plugin

DSH requires Node `^22.19.0 || >=24.0.0` and pnpm `11.7.0` (`corepack enable && corepack prepare pnpm@11.7.0 --activate`). End users do not need this checkout: the published CLI runs as `npx @deepseek-ai/dsh web`. For development, build the checkout once (the build is a precondition for `pnpm dsh web`):

```bash
cd /media/brittany/internal_drive_d/AIProjects/deepseek-harness
pnpm install
pnpm run build
pnpm dsh web
```

Configure the model credentials using the existing harness setup. Numerical tests will work without an API key.

Start with one small tool in your plugin repository to prove loading:

```ts
import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'signal-integrity'
export const inject = ['tools']

export function apply(ctx: Context) {
  ctx.tools.register(defineTool({
    name: 'si_ready',
    description: 'Check whether the signal integrity plugin is loaded.',
    parameters: {},
    output: {
      schema: { type: 'string' },
      // Convert the tool's value into text the model can read.
      render: (_args, value) => [{ type: 'text', text: value }],
    },
    async execute() {
      return 'Signal integrity plugin loaded.'
    },
  }))
}
```

Build TypeScript to ESM JavaScript. Declare a `dsh.bundle` patch in the package manifest; its patch inserts the plugin by package name. Every `@deepseek-ai/*` import is a `peerDependency` (plus `devDependency`) and stays external in the bundle, so the plugin shares the DSH installation's single Cordis instance. Export `Config` as a Schemastery schema, not zod: Cordis validates it through the Standard Schema interface at load. Object-typed `output.schema` nodes and nested parameter objects must declare `additionalProperties` explicitly.

Once the separate plugin project exists and its package builds, install it from the DSH clone:

```bash
pnpm dsh plugin --profile web add ../dsh-signal-integrity
pnpm dsh --profile web --dump-config
pnpm dsh web
```

`--profile` must follow `plugin`, and `--dump-config` is a launcher flag that must never follow `plugin` (it would be forwarded to pnpm). Adding a bundle requires a profile restart; live patch reload covers only `cordis.patch.yml` edits. Ask the model to call `si_ready`. This is the first acceptance checkpoint. The repository’s [tool tutorial](deepseek-harness/docs/user/develop/basic/tool.md) and [packaging tutorial](deepseek-harness/docs/user/develop/basic/publish.md) supply the integration pattern.

## 3. Full analysis workflow

Use **TypeScript for harness integration** and **Python with scikit-rf, NumPy/SciPy, and Matplotlib for numerical work**.

```text
User supplies local Touchstone path
    → inspect file and run quality checks
    → ask for device, topology, and port mapping
    → calculate applicable quantities
    → generate HTML report, PNG plots, and CSV data
    → explain results in chat
```

Expose two model-facing tools:

- `si_inspect`: accepts a file path; returns metadata, a content hash, quality diagnostics, and missing interpretation information.
- `si_analyze`: accepts the path, inspected hash, device settings, and port mapping; returns summaries and report paths. Refuse changed inputs and incomplete settings.

Use the existing `ask_user_question` tool for missing device information: `si_inspect` returns a `questions` array already shaped as that tool's `questions` parameter, so the model passes it straight through. Tool execution must also reject incomplete mappings; instructions to the model alone are insufficient. Do not call `ctx.userQuestions.ask` from inside the tools: it fails with `DELEGATED_CALLER` when the tool runs under a subagent.

### Device outputs

| Device | Required interpretation | First-release plots |
|---|---|---|
| Inductor | One-port impedance or explicitly identified two-terminal differential impedance | Effective series inductance and Q |
| Capacitor | Same terminal interpretation | Effective series capacitance |
| Transmission line | Input/output ports; single-ended or differential; uniform-line assumption | Insertion loss, return loss, complex characteristic impedance |
| Interposer / connector | Intended through paths; differential pairs and polarity where applicable | Every port’s return loss and all directed transmission terms, grouped by source port |

Use these conventions:

- \(L=\operatorname{Im}(Z)/\omega\), \(Q=\operatorname{Im}(Z)/\operatorname{Re}(Z)\), and series \(C=-1/[\omega\operatorname{Im}(Z)]\).
- For two-terminal differential excitation, use \(Z_{11}+Z_{22}-Z_{12}-Z_{21}\). Fixture-mounted series/shunt extraction requires a separate fixture model and is deferred.
- Define positive loss as \(IL=-20\log_{10}|S_{out,in}|\) and \(RL=-20\log_{10}|S_{in,in}|\).
- Extract \(Z_c=\sqrt{B/C}\) only for a valid reciprocal, symmetric uniform-line equivalent. Select the physically consistent, frequency-continuous branch; report ambiguous or singular samples.
- Differential analysis requires explicit pairing and polarity. Preserve the converted reference impedances; scikit-rf distinguishes differential and common-mode normalization. [Mixed-mode conversion documentation](https://scikit-rf.readthedocs.io/en/latest/api/generated/skrf.network.Network.se2gmm.html)

Label invalid extraction regions and resonance behavior. Do not silently convert negative or undefined values into apparently valid component parameters. Characteristic impedance extraction does not require line length; RLGC and distance-based TDR remain deferred.

### Quality checks

- **Parsing:** preserve frequency units, reference impedances, matrix ordering, and format metadata; reject malformed or unsupported data explicitly. Use the [Touchstone specification](https://ibis.org/touchstone_ver2.1/touchstone_ver2_1.pdf) for fixtures.
- **Passivity:** evaluate the largest singular value of the power-normalized S matrix at each sampled frequency. Report violations and the applied tolerance.
- **Reciprocity:** compare complex \(S_{ij}\) and \(S_{ji}\) under the supported normalization; one-port reciprocity is not applicable.
- **Causality:** use scikit-rf’s IEEE P370 frequency-domain initial causality metric as a screening diagnostic. Report its method and score; degenerate or insufficient data are inconclusive. Do not label this a mathematical proof or standards certification. [Implementation reference](https://scikit-rf.readthedocs.io/en/latest/_modules/skrf/calibration/deembedding.html)

Support standard single-ended Touchstone S data first, including conversion to mixed mode after mapping. Already mixed-mode inputs require explicit supported interpretation; never convert them twice.

## 4. Integration, reports, and validation

Launch the Python worker through `ctx.subprocess`, using structured arguments and JSON input/output, one process per tool call. The subprocess seam has no timeout or resource-limit fields and runs **outside** the agent sandbox without an approval prompt: the tool's `timeoutMs` and the forwarded abort signal own the deadline (SIGTERM, then SIGKILL after `graceMs`), and the worker caps its own address space with `RLIMIT_AS` from `maxMemoryMb`. The Python side is a uv project shipped inside the npm package; the worker is launched as `uv run --project <plugin>/python --frozen python -m dsh_si`, so `uv.lock` pins every numerical dependency, and `pythonCommand` overrides uv for a hand-managed interpreter. Validate worker responses against a shared protocol (mirror-tested on both sides) and propagate cancellation.

Keep the original file unchanged. Generate each report in a separate output directory containing:

- HTML summary with embedded plots and links to CSV data.
- PNG plots with units, port names, normalization, and extraction assumptions.
- Machine-readable results recording input hash, software versions, settings, and warnings.

Return bounded summaries to the model and retain report metadata in logged tool results. The Web client's Deliverables panel only tracks files written by the built-in `write`/`edit` tools, so return each analysis's key plot inline as an image content block through `ctx.attachments.saveImage` and echo the report directory in the rendered text. Use existing generic tool presentation; no custom Web upload interface or chart components are required.

Test before release:

- Analytic resistor–inductor, resistor–capacitor, and uniform-line fixtures recover known values.
- Passive, active, reciprocal, and nonreciprocal networks produce expected diagnostics.
- Delayed, advanced, undersampled, and degenerate data exercise causality limitations.
- Port permutations and reversed pair polarity produce correctly mapped differential results.
- Malformed files, singular conversions, changed input files, missing Python, cancellation, and report-write failures produce actionable errors.
- A real Loader composition loads both tools, records results, requests missing information, and produces reports.
- A built package installs and runs without a sibling source checkout.
- Keyless conversation fixtures verify orchestration; one real-model demonstration verifies the complete user workflow.

## 5. Portfolio PR milestones

Deliver the complete scope through reviewable PRs in `dsh-signal-integrity`:

1. **`feat/plugin-scaffold`:** installable DSH bundle, `si_ready`, build, and CI.
2. **`feat/touchstone-inspection`:** Touchstone parsing, metadata, content hash, passivity, reciprocity, and qualified causality diagnostics.
3. **`feat/lumped-extraction`:** inductor L/Q and capacitor C extraction with analytic reference fixtures.
4. **`feat/interconnect-analysis`:** single-ended/differential IL, RL, characteristic impedance, and interposer multiport reports.
5. **`release/v0.1.0`:** packaged installation, example reports, demonstration media, and reproducibility documentation.

Each PR must include the engineering problem, final behavior, relevant assumptions, tests run, and a generated output or screenshot. Keep review discussion public. Request an external RF or software review for at least one substantive PR when possible; do not present self-review as independent validation.

## 6. Publication and career showcase

### Public evidence

The repository landing page must make the result assessable within a few minutes:

- A one-sentence problem statement and an explicit **unofficial community plugin** label.
- A 30–60 second GIF or video of a real DSH conversation: inspect file → ask topology questions → analyze → open report.
- One architecture diagram showing DSH, the typed TypeScript tools, the managed Python worker, and generated artifacts.
- Redistributable or synthetic examples for an inductor, capacitor, transmission line, and interposer.
- Analytic expected values, numerical tolerances, CI results, known limitations (unconfined worker process, no RLGC or TDR, no fixture de-embedding), and the exact commands needed to reproduce them.
- Direct links to one substantial PR, the `v0.1.0` release, and a generated HTML report.

### Release and discovery

Publish a pinned `v0.1.0` release with built artifacts so a user does not need the sibling DSH source checkout. The primary documented path is the release tarball, which needs no build permission:

```bash
npx @deepseek-ai/dsh plugin --profile web add https://github.com/jiezheng5/dsh-signal-integrity/releases/download/v0.1.0/dsh-signal-integrity-0.1.0.tgz
npx @deepseek-ai/dsh --profile web --dump-config
npx @deepseek-ai/dsh web
```

A GitHub source install (`github:jiezheng5/dsh-signal-integrity#<commit-sha>`) additionally requires a `prepare` build script and an `allowBuilds` entry in the profile's `pnpm-workspace.yaml`; pin a commit sha, not a tag.

Add the GitHub topics `dsh-plugin`, `deepseek-harness`, `signal-integrity`, `touchstone`, `s-parameters`, `scikit-rf`, and `ai-agent`.

After the release is reproducible, publish one post in DSH's GitHub Discussions plugin category. The DSH repository itself only asks for the `dsh-plugin` topic; verify the category and its title format live before posting, and include the repository URL, introduction, screenshots or demo, real DSH integration, installation command, and unofficial status.

Use this title:

```text
DSH | Signal Integrity | Agent-guided Touchstone analysis and reporting
```

The post should ask for feedback on both the DSH integration and RF methodology. Community upvotes and comments are useful ecosystem evidence but do not imply official DeepSeek endorsement.

### Portfolio claims

Use wording that can be verified from the public artifacts:

> Built and released an unofficial DeepSeek Harness plugin that converts Touchstone S-parameter data into agent-guided signal-integrity workflows, including topology clarification, mixed-mode analysis, network-quality diagnostics, and reproducible reports.

Add measured claims only after the tests exist, such as supported port counts, fixture coverage, numerical error, test count, release downloads, or community adoption. Never describe the plugin as merged into or officially endorsed by DeepSeek Harness unless that later occurs.

If DSH changes its policy or a maintainer explicitly invites an upstream change, first agree on scope, then fork DSH and create a separate feature branch from `upstream/master`. That optional future PR is not a dependency of this portfolio plan. [GitHub fork PR workflow](https://docs.github.com/en/pull-requests/how-tos/create-pull-requests/creating-a-pull-request-from-a-fork)

## 7. Verified DSH integration facts (checkout `0.1.3-alpha.1`, published `0.1.2-rc.1`)

Facts checked against the DSH source on 2026-09-06 that shape this plugin's code:

- `defineTool` parameters use DSH's own flat property spec, compiled to JSON Schema internally; `output.render` receives the validated canonical value. Errors are thrown; a successful domain outcome (such as "environment not ready") is a canonical value, not an error.
- `ctx.subprocess.spawn` takes `argv`, `cwd`, explicit `stdio`, `graceMs`, `signal`, and `env`; output is read back through `handle.collected.<stream>.readFrom(0)`. It applies no sandbox and no rlimits.
- The `ask_user_question` tool's `questions` parameter is `[{ id, question, header?, options?: [{ label, description? }], multi_select? }]`.
- The published CLI is `@deepseek-ai/dsh`; the published library packages lag the checkout by one prerelease, so peer ranges are `>=0.1.2-rc.1 <0.2.0` and the tests run against the published versions.
- Unit tests mount a bare `Context` with `SystemPrompt`, `ToolRuntime`, and `LocalSubprocessRuntime` and call `ctx.tools.execute` directly, keyless. Integration tests will boot the shipped `web` profile with a `.patch.yml` overlay and a scripted `LlmAdapter`.
