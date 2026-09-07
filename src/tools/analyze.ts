import type { Context } from '@deepseek-ai/cordis'
import { defineTool } from '@deepseek-ai/dsh-tools'
import { isAbsolute } from 'node:path'
import type { Config } from '../config.ts'
import { formatHz } from '../format.ts'
import { imageBlocks, isSavedImage, saveInlineImages } from '../images.ts'
import type { JsonObject, JsonValue } from '../protocol.ts'
import { WorkerClient, WorkerError } from '../worker.ts'

const description = 'Run the device-specific signal-integrity analysis on a Touchstone file that si_inspect already inspected. '
  + 'Requires the absolute path, the sha256 `hash` from si_inspect (refused if the file changed), and the `interpretation` '
  + 'object assembled from the user\'s answers: { device: inductor|capacitor|transmission_line|interposer, '
  + 'terminal_mode?: one_port|two_terminal_differential|through (lumped), ports?: {in:[..], out:[..]} (line), '
  + 'topology?: single_ended_paths|differential_pairs|mixed_mode_already (interposer), pairs?: [{name?, p, n}], '
  + 'paths?: [{from, to}], input_is_mixed_mode?: bool }. Writes a report directory (PNG, CSV, results.json, report.html) '
  + 'and returns a bounded summary plus the key plot.'

const DOMAIN_CODES = new Set([
  'bad_request', 'file_not_found', 'parse_error', 'unsupported_format', 'interpretation_invalid', 'hash_mismatch', 'report_write_failed',
])

export interface AnalyzeValue {
  path: string
  hash: string
  device: string
  status: string
  report_dir: string
  files: string[]
  plots: JsonObject[]
  summary: JsonObject
  warnings: string[]
  images: JsonObject[]
  image_notes: string[]
}

function obj(value: JsonValue | undefined): JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? value : {}
}

function strings(value: JsonValue | undefined): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
}

export function renderAnalyze(value: AnalyzeValue): string {
  const lines: string[] = []
  lines.push(`Analysis of ${value.path.split('/').pop() ?? value.path} as ${value.device}: status ${value.status}`)
  lines.push(`Report directory: ${value.report_dir}`)
  for (const file of value.files) lines.push(`  ${file.split('/').pop() ?? file}`)
  const entries = Object.entries(value.summary)
  if (entries.length > 0) {
    lines.push('Summary:')
    for (const [key, raw] of entries) {
      if (typeof raw === 'object' && raw !== null && !Array.isArray(raw) && 'median' in raw) {
        const median = raw['median']
        lines.push(`  ${key}: median ${median === null ? 'undefined' : String(median)} over ${String(raw['n_valid'])} valid points`)
      } else if (key.endsWith('_hz') && typeof raw === 'number') {
        lines.push(`  ${key}: ${formatHz(raw)}`)
      } else {
        lines.push(`  ${key}: ${JSON.stringify(raw)}`)
      }
    }
  }
  for (const warning of value.warnings) lines.push(`Warning: ${warning}`)
  for (const note of value.image_notes) lines.push(`Plot note: ${note}`)
  if (value.images.length > 0) lines.push(`Inline plots: ${value.images.map(i => i.title).join('; ')}`)
  return lines.join('\n')
}

export function registerAnalyzeTool(ctx: Context, worker: WorkerClient, config: Config): void {
  ctx.tools.register(defineTool({
    name: 'si_analyze',
    description,
    parameters: {
      path: { type: 'string', required: true, description: 'Absolute path to the Touchstone file (same as given to si_inspect).' },
      hash: { type: 'string', required: true, description: 'sha256 returned by si_inspect for this file.' },
      interpretation: {
        type: 'object',
        required: true,
        additionalProperties: true,
        description: 'Device and port interpretation assembled from the user\'s answers (see tool description).',
      },
    },
    output: {
      schema: {
        type: 'object',
        additionalProperties: false,
        properties: {
          path: { type: 'string', required: true },
          hash: { type: 'string', required: true },
          device: { type: 'string', required: true },
          status: { type: 'string', required: true, description: 'complete for inductors and capacitors; overview_only for lines and interposers until milestone 4.' },
          report_dir: { type: 'string', required: true },
          files: { type: 'array', required: true, items: { type: 'string' } },
          plots: { type: 'array', required: true, items: { type: 'object', additionalProperties: true } },
          summary: { type: 'object', required: true, additionalProperties: true },
          warnings: { type: 'array', required: true, items: { type: 'string' } },
          images: { type: 'array', required: true, items: { type: 'object', additionalProperties: true } },
          image_notes: { type: 'array', required: true, items: { type: 'string' } },
        },
      },
      render: (_args, value) => {
        const v = value as AnalyzeValue
        return [{ type: 'text', text: renderAnalyze(v) }, ...imageBlocks(v.images.filter(isSavedImage))]
      },
    },
    timeoutMs: config.timeoutMs,
    async execute(args, exec): Promise<AnalyzeValue> {
      if (!isAbsolute(args.path)) throw new Error(`si_analyze needs an absolute path; got "${args.path}".`)
      let result: JsonObject
      try {
        result = await worker.call('analyze', {
          path: args.path,
          hash: args.hash,
          interpretation: args.interpretation as JsonObject,
          output_dir: config.outputDir,
          tolerances: config.tolerances,
        }, exec.signal)
      } catch (error) {
        if (error instanceof WorkerError && DOMAIN_CODES.has(error.code)) {
          throw new Error(`${error.message}${error.detail ? ` (${error.detail})` : ''}`, { cause: error })
        }
        if (error instanceof WorkerError && error.code !== 'cancelled') {
          throw new Error(`signal-integrity worker failed (${error.code}): ${error.message}. Call si_ready to diagnose the environment.`, { cause: error })
        }
        throw error
      }
      const plots = Array.isArray(result['plots']) ? result['plots'].map(obj) : []
      const saved = await saveInlineImages(ctx, plots, config.inlinePlots)
      return {
        path: String(result['path'] ?? args.path),
        hash: String(result['hash'] ?? args.hash),
        device: String(result['device'] ?? ''),
        status: String(result['status'] ?? 'unknown'),
        report_dir: String(result['report_dir'] ?? ''),
        files: strings(result['files']),
        plots,
        summary: obj(result['summary']),
        warnings: strings(result['warnings']),
        images: saved.images,
        image_notes: saved.skipped,
      }
    },
  }))
}
