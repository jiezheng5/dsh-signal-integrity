/**
 * dsh-signal-integrity: an unofficial DeepSeek Harness plugin that turns
 * Touchstone S-parameter files into agent-guided signal-integrity reports.
 *
 * The plugin registers model-facing tools and delegates all numerical work to
 * a Python worker (python/dsh_si) launched through `ctx.subprocess`.
 *
 * @module dsh-signal-integrity
 */

import type { Context } from '@deepseek-ai/cordis'
import '@deepseek-ai/dsh-tools'
import '@deepseek-ai/dsh-subprocess'
import '@deepseek-ai/dsh-attachment'
import { Config } from './config.ts'
import { registerAnalyzeTool } from './tools/analyze.ts'
import { registerInspectTool } from './tools/inspect.ts'
import { registerReadyTool } from './tools/ready.ts'
import { registerReportRoute } from './reports.ts'
import { WorkerClient } from './worker.ts'

export const name = 'signal-integrity'
export const inject = ['tools', 'subprocess']
export { Config }
export { WorkerClient, WorkerError, bundledPythonProjectDir } from './worker.ts'
export { PROTOCOL_VERSION, COMMANDS, WORKER_ERROR_CODES } from './protocol.ts'

export function apply(ctx: Context, config: Config): void {
  const worker = new WorkerClient(ctx, config)
  const links = registerReportRoute(ctx, config.outputDir)
  registerReadyTool(ctx, worker, config)
  registerInspectTool(ctx, worker, config)
  registerAnalyzeTool(ctx, worker, config, links)
}
