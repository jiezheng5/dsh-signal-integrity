import { fileURLToPath } from 'node:url'
import { Context } from '@deepseek-ai/cordis'
import { ToolCallId } from '@deepseek-ai/dsh-llm'
import LocalSubprocessRuntime from '@deepseek-ai/dsh-subprocess-local'
import SystemPrompt from '@deepseek-ai/dsh-system-prompt'
import ToolRuntime from '@deepseek-ai/dsh-tools'
import type { ToolResult } from '@deepseek-ai/dsh-tools'
import * as SignalIntegrity from '../src/index.ts'
import type { Config } from '../src/index.ts'

export const FAKE_WORKER = fileURLToPath(new URL('./fixtures/fake-worker.mjs', import.meta.url))

/** Command that launches the fake worker in the given mode. */
export function fakeWorker(mode: string): string[] {
  return [process.execPath, FAKE_WORKER, mode]
}

/**
 * Mount the plugin on a bare Context with the real tool registry and the real
 * local subprocess provider: keyless, no model, no uv unless the config asks.
 */
export async function mountPlugin(config: Partial<Config> = {}): Promise<Context> {
  const ctx = new Context()
  await ctx.plugin(SystemPrompt, {})
  await ctx.plugin(ToolRuntime)
  await ctx.plugin(LocalSubprocessRuntime)
  // The exported Schemastery `Config` fills defaults at load, so a partial is valid input.
  await ctx.plugin(SignalIntegrity, config as Config)
  return ctx
}

let callCounter = 0

export async function callTool(
  ctx: Context,
  name: string,
  args: Record<string, unknown> = {},
  signal: AbortSignal = new AbortController().signal,
): Promise<ToolResult> {
  callCounter += 1
  return ctx.tools.execute({ signal, callId: ToolCallId(`test-${callCounter}`), name, arguments: args })
}

export function textOf(result: ToolResult): string {
  return result.content.map(block => block.type === 'text' ? block.text : `[${block.type}]`).join('\n')
}
