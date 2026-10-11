import { execFileSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
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

const EXAMPLE_LINE = fileURLToPath(new URL('../examples/synthetic/lossy_line_20mm.s2p', import.meta.url))
const EXAMPLE_RL = fileURLToPath(new URL('../examples/synthetic/series_rl_10nH.s1p', import.meta.url))

describe('si_inspect with the fake worker', () => {
  it('renders metadata, quality, warnings, and the questions block', async () => {
    const ctx = await mount({ pythonCommand: fakeWorker('inspect'), tolerances: { passivity: 0.001, reciprocity: 1e-6, singularC: 1e-9 } })
    const result = await callTool(ctx, 'si_inspect', { path: '/data/fake.s2p' })
    expect(result.isError).toBe(false)
    const text = textOf(result)
    expect(text).toContain('Inspected fake.s2p (sha256 aaaaaaaaaaaa…)')
    expect(text).toContain('Ports: 2 · Points: 401 · 10 MHz to 20 GHz · Format: S RI (Touchstone 1.0)')
    expect(text).toContain('Reference impedance: 50 Ω (all ports)')
    expect(text).toContain('  Passivity:   PASS · P370 good (100.0%) · max singular value 0.9991 at 10 MHz · 0/401 points over tolerance 0.001')
    expect(text).toContain('  Reciprocity: FAIL · P370 acceptable (91.2%) · max |Sij-Sji| 1.23e-2 at 5 GHz · 7/401 points over tolerance 0.000001')
    expect(text).toContain('  Causality:   P370 good (CQMi 100.0%) · screening only')
    expect(text).toContain('  Method: IEEE P370 via scikit-rf')
    expect(text).toContain('Warning: header comments mention mixed-mode terms')
    expect(text).toContain('ask_user_question')
    expect(text).toContain('[{"id":"device","question":"What device?","options":[{"label":"inductor"}]}]')
    expect(text).toContain(`Pass hash ${'a'.repeat(64)} to si_analyze`)
  })

  it('rejects a relative path before spawning', async () => {
    const ctx = await mount({ pythonCommand: fakeWorker('inspect') })
    const result = await callTool(ctx, 'si_inspect', { path: 'relative/file.s2p' })
    expect(result.isError).toBe(true)
    expect(textOf(result)).toContain('needs an absolute path')
  })

  it('rejects a missing path argument', async () => {
    const ctx = await mount({ pythonCommand: fakeWorker('inspect') })
    const result = await callTool(ctx, 'si_inspect', {})
    expect(result.isError).toBe(true)
  })

  it('surfaces a worker domain error as the tool error', async () => {
    const ctx = await mount({ pythonCommand: fakeWorker('domain-error') })
    const result = await callTool(ctx, 'si_inspect', { path: '/data/fake.s2p' })
    expect(result.isError).toBe(true)
    expect(textOf(result)).toContain('fake.s2p: cannot parse Touchstone header/data (ValueError: boom)')
  })

  it('points at si_ready when the worker itself fails', async () => {
    const ctx = await mount({ pythonCommand: fakeWorker('crash') })
    const result = await callTool(ctx, 'si_inspect', { path: '/data/fake.s2p' })
    expect(result.isError).toBe(true)
    expect(textOf(result)).toContain('signal-integrity worker failed (crashed)')
    expect(textOf(result)).toContain('Call si_ready')
  })
})

function uvAvailable(): boolean {
  try {
    execFileSync('uv', ['--version'], { stdio: 'ignore' })
    return true
  } catch {
    return false
  }
}

describe.skipIf(!uvAvailable())('si_inspect through uv on the shipped examples', () => {
  it('inspects the synthetic lossy line', async () => {
    const ctx = await mount()
    const result = await callTool(ctx, 'si_inspect', { path: EXAMPLE_LINE })
    expect(result.isError).toBe(false)
    const text = textOf(result)
    expect(text).toContain('Ports: 2 · Points: 401 · 10 MHz to 20 GHz')
    expect(text).toContain('  Passivity:   PASS · P370 good (100.0%)')
    expect(text).toContain('  Reciprocity: PASS · P370 good (100.0%)')
    expect(text).toContain('  Causality:   P370 good (CQMi 100.0%)')
    expect(text).toContain('"id":"terminal_mode"')
  })

  it('inspects the one-port RL and skips inapplicable checks', async () => {
    const ctx = await mount()
    const text = textOf(await callTool(ctx, 'si_inspect', { path: EXAMPLE_RL }))
    expect(text).toContain('Ports: 1')
    expect(text).toContain('  Reciprocity: not applicable (one-port)')
    expect(text).toContain('  Causality:   not applicable (one-port)')
  })

  it('reports a missing file', async () => {
    const ctx = await mount()
    const result = await callTool(ctx, 'si_inspect', { path: '/definitely/missing.s2p' })
    expect(result.isError).toBe(true)
    expect(textOf(result)).toContain('no such file')
  })
})
