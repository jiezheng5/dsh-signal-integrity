import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { isAbsolute } from 'node:path'
import type { Config } from '../config.ts'
import { formatComplex, formatHz } from '../format.ts'
import type { JsonObject, JsonValue } from '../protocol.ts'
import { WorkerClient, WorkerError } from '../worker.ts'

const description = 'Inspect a Touchstone S-parameter file before any analysis: returns its content hash, header metadata '
  + '(ports, frequency span, reference impedance, format), passivity/reciprocity/causality screening, warnings, and '
  + 'the `questions` you must ask the user (pass them to ask_user_question verbatim) before calling si_analyze. '
  + 'Requires an absolute path.'

/** Codes that describe the user's file rather than the plugin's environment. */
const DOMAIN_CODES = new Set(['bad_request', 'file_not_found', 'parse_error', 'unsupported_format'])

export interface InspectValue {
  path: string
  hash: string
  metadata: JsonObject
  quality: JsonObject
  warnings: string[]
  questions: JsonObject[]
  required_by_device: JsonObject
}

function obj(value: JsonValue | undefined): JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value : {}
}

function num(value: JsonValue | undefined): number | undefined {
  return typeof value === 'number' ? value : undefined
}

export function renderInspect(value: InspectValue): string {
  const md = value.metadata
  const lines: string[] = []
  lines.push(`Inspected ${String(md['file_name'] ?? value.path)} (sha256 ${value.hash.slice(0, 12)}…)`)
  const fMin = num(md['f_min_hz'])
  const fMax = num(md['f_max_hz'])
  lines.push(
    `Ports: ${String(md['n_ports'])} · Points: ${String(md['n_freq'])}`
    + (fMin !== undefined && fMax !== undefined ? ` · ${formatHz(fMin)} to ${formatHz(fMax)}` : '')
    + ` · Format: ${String(md['parameter'] ?? 's').toUpperCase()} ${String(md['format'] ?? '').toUpperCase()}`
    + (md['touchstone_version'] ? ` (Touchstone ${String(md['touchstone_version'])})` : ''),
  )
  const z0 = md['reference_impedance']
  if (Array.isArray(z0)) {
    const labels = z0.map(entry => formatComplex(obj(entry) as { re: number; im: number }))
    const unique = [...new Set(labels)]
    lines.push(`Reference impedance: ${unique.length === 1 ? `${unique[0]} Ω (all ports)` : labels.map((l, i) => `P${i + 1}=${l}`).join(', ')}`)
  }
  const passivity = obj(value.quality['passivity'])
  const reciprocity = obj(value.quality['reciprocity'])
  const causality = obj(value.quality['causality'])
  lines.push(
    `Passivity: ${passivity['passive'] === true ? 'pass' : 'FAIL'}`
    + ` (max σ ${Number(passivity['sigma_max_worst'] ?? Number.NaN).toFixed(4)} at ${formatHz(num(passivity['worst_freq_hz']) ?? 0)},`
    + ` ${String(passivity['violation_count'] ?? 0)} violating points, tol ${String(passivity['tolerance'])})`,
  )
  if (reciprocity['applicable'] === true) {
    lines.push(
      `Reciprocity: ${reciprocity['reciprocal'] === true ? 'pass' : 'FAIL'}`
      + ` (max |Sij-Sji| ${Number(reciprocity['max_abs_diff_worst'] ?? Number.NaN).toExponential(2)} at ${formatHz(num(reciprocity['worst_freq_hz']) ?? 0)},`
      + ` ${String(reciprocity['violation_count'] ?? 0)} violating points)`,
    )
  } else {
    lines.push('Reciprocity: not applicable (one-port)')
  }
  const score = num(causality['score_percent'])
  lines.push(
    `Causality screening: ${String(causality['verdict'])}`
    + (score !== undefined ? ` (CQMi ${score.toFixed(1)}%)` : '')
    + ` — ${String(causality['note'] ?? '')}`,
  )
  lines.push(`Method: ${String(causality['method'] ?? '')}`)
  for (const warning of value.warnings) lines.push(`Warning: ${warning}`)
  lines.push('')
  lines.push('Before calling si_analyze, ask the user these questions with ask_user_question (pass the array as-is):')
  lines.push(JSON.stringify(value.questions))
  lines.push(`si_analyze requires per device: ${JSON.stringify(value.required_by_device)}`)
  lines.push(`Pass hash ${value.hash} to si_analyze; it refuses if the file changed.`)
  return lines.join('\n')
}

export function registerInspectTool(ctx: Context, worker: WorkerClient, config: Config): void {
  ctx.tools.register(defineTool({
    name: 'si_inspect',
    description,
    parameters: {
      path: { type: 'string', required: true, description: 'Absolute path to a Touchstone file (.s1p, .s2p, …, .sNp, or .ts).' },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          path: { type: 'string', required: true },
          hash: { type: 'string', required: true, description: 'sha256 of the file content; required by si_analyze.' },
          metadata: { type: 'object', required: true, additionalProperties: true },
          quality: { type: 'object', required: true, additionalProperties: true },
          warnings: { type: 'array', required: true, items: { type: 'string' } },
          questions: { type: 'array', required: true, items: { type: 'object', additionalProperties: true } },
          required_by_device: { type: 'object', required: true, additionalProperties: true },
        },
      },
      render: (_args, value) => [{ type: 'text', text: renderInspect(value as InspectValue) }],
    },
    timeoutMs: config.timeoutMs,
    async execute(args, exec): Promise<InspectValue> {
      if (!isAbsolute(args.path)) {
        throw new Error(`si_inspect needs an absolute path; got "${args.path}". Resolve it against the workspace first.`)
      }
      let result: JsonObject
      try {
        result = await worker.call('inspect', { path: args.path, tolerances: config.tolerances }, exec.signal)
      } catch (error) {
        if (error instanceof WorkerError && DOMAIN_CODES.has(error.code)) {
          throw new Error(`${error.message}${error.detail ? ` (${error.detail})` : ''}`, { cause: error })
        }
        if (error instanceof WorkerError && error.code !== 'cancelled') {
          throw new Error(`signal-integrity worker failed (${error.code}): ${error.message}. Call si_ready to diagnose the environment.`, { cause: error })
        }
        throw error
      }
      const warnings = Array.isArray(result['warnings']) ? result['warnings'].filter((w): w is string => typeof w === 'string') : []
      const questions = Array.isArray(result['questions']) ? result['questions'].map(obj) : []
      return {
        path: String(result['path'] ?? args.path),
        hash: String(result['hash'] ?? ''),
        metadata: obj(result['metadata']),
        quality: obj(result['quality']),
        warnings,
        questions,
        required_by_device: obj(result['required_by_device']),
      }
    },
  }))
}
