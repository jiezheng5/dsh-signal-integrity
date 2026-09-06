import { execFileSync } from 'node:child_process'
import { mkdtempSync, existsSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'
import type { Context } from '@deepseek-ai/cordis'
import type { Config } from '../src/index.ts'
import { callTool, fakeWorker, mountPlugin, textOf } from './harness.ts'

const contexts: Context[] = []
const dirs: string[] = []
function outDir(): string {
  const dir = mkdtempSync(join(tmpdir(), 'si-analyze-'))
  dirs.push(dir)
  return dir
}
async function mount(config: Partial<Config> = {}): Promise<Context> {
  const ctx = await mountPlugin({ outputDir: outDir(), ...config })
  contexts.push(ctx)
  return ctx
}
afterEach(async () => {
  for (const ctx of contexts.splice(0)) await ctx.fiber.dispose()
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true })
})

const EXAMPLE_LINE = fileURLToPath(new URL('../examples/synthetic/lossy_line_20mm.s2p', import.meta.url))
const HASH = 'a'.repeat(64)

describe('si_analyze with the fake worker', () => {
  it('renders status, report files, summary, and notes the missing attachment service', async () => {
    const ctx = await mount({ pythonCommand: fakeWorker('analyze') })
    const result = await callTool(ctx, 'si_analyze', { path: '/data/fake.s2p', hash: HASH, interpretation: { device: 'inductor', terminal_mode: 'one_port' } })
    expect(result.isError).toBe(false)
    const text = textOf(result)
    expect(text).toContain('Analysis of fake.s2p as inductor: status complete')
    expect(text).toContain('Report directory: ')
    expect(text).toContain('  s_magnitude.png')
    expect(text).toContain('  L_h: median 1e-8 over 400 valid points')
    expect(text).toContain('  srf_hz: 1.59 GHz')
    expect(text).toContain('Plot note: no attachment service mounted; plots are on disk only')
    expect(result.content.filter(b => b.type === 'image')).toHaveLength(0)
  })

  it('does not touch the attachment path when inlinePlots is off', async () => {
    const ctx = await mount({ pythonCommand: fakeWorker('analyze'), inlinePlots: false })
    const text = textOf(await callTool(ctx, 'si_analyze', { path: '/data/fake.s2p', hash: HASH, interpretation: { device: 'inductor' } }))
    expect(text).not.toContain('Plot note')
  })

  it('surfaces hash mismatch as the tool error', async () => {
    const ctx = await mount({ pythonCommand: fakeWorker('hash-mismatch') })
    const result = await callTool(ctx, 'si_analyze', { path: '/data/fake.s2p', hash: HASH, interpretation: { device: 'inductor' } })
    expect(result.isError).toBe(true)
    expect(textOf(result)).toContain('run si_inspect again')
  })

  it('rejects missing required arguments before spawning', async () => {
    const ctx = await mount({ pythonCommand: fakeWorker('analyze') })
    const result = await callTool(ctx, 'si_analyze', { path: '/data/fake.s2p' })
    expect(result.isError).toBe(true)
  })

  it('si_inspect reports the overview plot location', async () => {
    const ctx = await mount({ pythonCommand: fakeWorker('inspect') })
    const text = textOf(await callTool(ctx, 'si_inspect', { path: '/data/fake.s2p' }))
    expect(text).toMatch(/Overview plot: .*\/fake\/s_magnitude\.png/u)
    expect(text).toContain('Plot note: no attachment service mounted')
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

describe.skipIf(!uvAvailable())('si_analyze through uv on the shipped example', () => {
  it('inspects, then analyzes the line as overview_only with a real report directory', async () => {
    const ctx = await mount()
    const inspected = textOf(await callTool(ctx, 'si_inspect', { path: EXAMPLE_LINE }))
    const hash = /Pass hash ([0-9a-f]{64}) to si_analyze/u.exec(inspected)?.[1]
    expect(hash).toBeDefined()
    const result = await callTool(ctx, 'si_analyze', {
      path: EXAMPLE_LINE,
      hash,
      interpretation: { device: 'transmission_line', ports: { in: [1], out: [2] } },
    })
    expect(result.isError).toBe(false)
    const text = textOf(result)
    expect(text).toContain('as transmission_line: status overview_only')
    expect(text).toContain('Warning: transmission_line analysis arrives in milestone 4')
    const dir = /Report directory: (.+)/u.exec(text)?.[1]
    expect(dir).toBeDefined()
    for (const name of ['s_magnitude.png', 'results.json', 'report.html']) expect(existsSync(join(dir!, name))).toBe(true)
  })

  it('refuses a wrong hash and an incomplete interpretation with actionable text', async () => {
    const ctx = await mount()
    const wrong = await callTool(ctx, 'si_analyze', { path: EXAMPLE_LINE, hash: HASH, interpretation: { device: 'transmission_line' } })
    expect(wrong.isError).toBe(true)
    expect(textOf(wrong)).toContain('run si_inspect again')
    const inspected = textOf(await callTool(ctx, 'si_inspect', { path: EXAMPLE_LINE }))
    const hash = /Pass hash ([0-9a-f]{64})/u.exec(inspected)?.[1]
    const incomplete = await callTool(ctx, 'si_analyze', { path: EXAMPLE_LINE, hash, interpretation: { device: 'inductor' } })
    expect(incomplete.isError).toBe(true)
    expect(textOf(incomplete)).toContain('terminal_mode: expected one of')
  })
})
