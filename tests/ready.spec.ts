import { execFileSync } from 'node:child_process'
import { afterEach, describe, expect, it } from 'vitest'
import type { Context } from '@deepseek-ai/cordis'
import type { Config } from '../src/index.ts'
import { callTool, fakeWorker, mountPlugin, textOf } from './harness.ts'

const contexts: Context[] = []
async function mount(config: Partial<Config> = {}): Promise<Context> {
  const ctx = await mountPlugin(config)
  contexts.push(ctx)
  return ctx
}
afterEach(async () => {
  for (const ctx of contexts.splice(0)) await ctx.fiber.dispose()
})

describe('si_ready with the fake worker', () => {
  it('reports a ready environment', async () => {
    const ctx = await mount({ pythonCommand: fakeWorker('ok') })
    const result = await callTool(ctx, 'si_ready')
    expect(result.isError).toBe(false)
    const text = textOf(result)
    expect(text).toContain('Signal-integrity plugin ready.')
    expect(text).toContain('skrf=2.1.0')
    expect(text).toContain('Worker: dsh_si 0.0.0-fake')
  })

  it('lists missing packages with a remedy', async () => {
    const ctx = await mount({ pythonCommand: fakeWorker('missing') })
    const result = await callTool(ctx, 'si_ready')
    expect(result.isError).toBe(false)
    const text = textOf(result)
    expect(text).toContain('NOT ready')
    expect(text).toContain('skrf=MISSING')
    expect(text).toContain('missing Python packages: skrf, matplotlib')
    expect(text).toContain('uv sync --frozen')
  })

  it('turns a structured worker error into a not-ready result', async () => {
    const ctx = await mount({ pythonCommand: fakeWorker('error') })
    const text = textOf(await callTool(ctx, 'si_ready'))
    expect(text).toContain('NOT ready')
    expect(text).toContain('parse_error: bad touchstone [line 3]')
  })

  it('reports a crash with exit code and stderr', async () => {
    const ctx = await mount({ pythonCommand: fakeWorker('crash') })
    const text = textOf(await callTool(ctx, 'si_ready'))
    expect(text).toContain('crashed: worker produced no response (exit code 3)')
    expect(text).toContain('Traceback: boom')
  })

  it('reports non-JSON output as a protocol problem', async () => {
    const ctx = await mount({ pythonCommand: fakeWorker('garbage') })
    const text = textOf(await callTool(ctx, 'si_ready'))
    expect(text).toContain('protocol: worker stdout is not valid JSON')
  })

  it('reports a protocol version mismatch', async () => {
    const ctx = await mount({ pythonCommand: fakeWorker('wrong-protocol') })
    const text = textOf(await callTool(ctx, 'si_ready'))
    expect(text).toContain('protocol: worker speaks protocol v42, plugin expects v1')
  })

  it('explains a missing interpreter', async () => {
    const ctx = await mount({ pythonCommand: ['definitely-not-a-real-binary-xyz'] })
    const text = textOf(await callTool(ctx, 'si_ready'))
    expect(text).toContain('NOT ready')
    expect(text).toMatch(/spawn_failed: cannot start the Python worker: `definitely-not-a-real-binary-xyz` \(from pythonCommand\) was not found/u)
  })

  it('explains a missing uv with the install hint', async () => {
    const ctx = await mount({ uvPath: 'definitely-not-uv-xyz' })
    const text = textOf(await callTool(ctx, 'si_ready'))
    expect(text).toContain('`definitely-not-uv-xyz` was not found')
    expect(text).toContain('https://docs.astral.sh/uv/')
  })

  it('cancels a hung worker and rejects the call', async () => {
    const ctx = await mount({ pythonCommand: fakeWorker('hang'), graceMs: 500 })
    const controller = new AbortController()
    const pending = callTool(ctx, 'si_ready', {}, controller.signal)
    await new Promise(resolve => setTimeout(resolve, 300))
    controller.abort()
    const result = await pending
    expect(result.isError).toBe(true)
    expect(textOf(result)).toMatch(/cancel/iu)
    // No fake-worker process may survive the abort.
    let survivors: string[] = []
    try {
      survivors = execFileSync('pgrep', ['-f', 'fake-worker.mjs hang'], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).split('\n').filter(Boolean)
    } catch {
      // pgrep exits 1 when nothing matches: the desired outcome.
    }
    expect(survivors).toEqual([])
  })
})
