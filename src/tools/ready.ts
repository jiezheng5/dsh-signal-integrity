import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import type { Config } from '../config.ts'
import type { JsonObject } from '../protocol.ts'
import { WorkerClient, WorkerError } from '../worker.ts'

const description = 'Check that the signal-integrity plugin and its Python worker (uv, scikit-rf, NumPy, SciPy, '
  + 'Matplotlib) are ready. Call this first when another si_* tool fails to start, and relay any remedy to the user.'

export interface ReadyValue {
  ready: boolean
  launcher: string
  worker_version?: string
  python?: JsonObject
  packages?: JsonObject
  problems: string[]
}

export function renderReady(value: ReadyValue): string {
  const lines: string[] = []
  lines.push(value.ready ? 'Signal-integrity plugin ready.' : 'Signal-integrity plugin NOT ready.')
  lines.push(`Worker launcher: ${value.launcher}`)
  if (value.python !== undefined) {
    lines.push(`Python: ${String(value.python['version'])} (${String(value.python['implementation'])}) at ${String(value.python['executable'])}`)
  }
  if (value.worker_version !== undefined) lines.push(`Worker: dsh_si ${value.worker_version}`)
  if (value.packages !== undefined) {
    const parts = Object.entries(value.packages).map(([name, version]) => `${name}=${version === null ? 'MISSING' : String(version)}`)
    lines.push(`Packages: ${parts.join(', ')}`)
  }
  for (const problem of value.problems) lines.push(`Problem: ${problem}`)
  return lines.join('\n')
}

export function registerReadyTool(ctx: Context, worker: WorkerClient, config: Config): void {
  ctx.tools.register(defineTool({
    name: 'si_ready',
    description,
    parameters: {},
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          ready: { type: 'boolean', required: true },
          launcher: { type: 'string', required: true },
          worker_version: { type: 'string' },
          python: { type: 'object', additionalProperties: true },
          packages: { type: 'object', additionalProperties: true },
          problems: { type: 'array', required: true, items: { type: 'string' } },
        },
      },
      render: (_args, value) => [{ type: 'text', text: renderReady(value as ReadyValue) }],
    },
    timeoutMs: config.timeoutMs,
    async execute(_args, exec): Promise<ReadyValue> {
      const launcher = worker.launcher
      try {
        const result = await worker.call('ready', {}, exec.signal)
        const packages = isRecord(result['packages']) ? result['packages'] : {}
        const missing = Object.entries(packages).filter(([, v]) => v === null).map(([name]) => name)
        const problems = missing.length > 0
          ? [`missing Python packages: ${missing.join(', ')}. Run \`uv sync --frozen\` in ${worker.projectDir}, or fix pythonCommand.`]
          : []
        return {
          ready: result['ready'] === true && missing.length === 0,
          launcher,
          ...typeof result['worker_version'] === 'string' ? { worker_version: result['worker_version'] } : {},
          ...isRecord(result['python']) ? { python: result['python'] } : {},
          packages,
          problems,
        }
      } catch (error) {
        // A broken environment is this tool's domain outcome, not an infrastructure failure.
        if (error instanceof WorkerError && error.code !== 'cancelled') {
          const detail = error.detail !== undefined && error.detail !== '' ? ` [${error.detail}]` : ''
          return { ready: false, launcher, problems: [`${error.code}: ${error.message}${detail}`] }
        }
        throw error
      }
    },
  }))
}

function isRecord(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
