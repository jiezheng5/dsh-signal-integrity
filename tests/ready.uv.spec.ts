import { execFileSync } from 'node:child_process'
import { afterEach, describe, expect, it } from 'vitest'
import type { Context } from '@deepseek-ai/cordis'
import { callTool, mountPlugin, textOf } from './harness.ts'

function uvAvailable(): boolean {
  try {
    execFileSync('uv', ['--version'], { stdio: 'ignore' })
    return true
  } catch {
    return false
  }
}

let ctx: Context | undefined
afterEach(async () => {
  await ctx?.fiber.dispose()
  ctx = undefined
})

/** End-to-end through uv and the real worker; skipped where uv is not installed. */
describe.skipIf(!uvAvailable())('si_ready through uv', () => {
  it('reports the real worker as ready with default config', async () => {
    ctx = await mountPlugin()
    const result = await callTool(ctx, 'si_ready')
    expect(result.isError).toBe(false)
    const text = textOf(result)
    expect(text).toContain('Signal-integrity plugin ready.')
    expect(text).toMatch(/skrf=\d+\.\d+/u)
    expect(text).toMatch(/Worker launcher: uv run --project .* --frozen --no-dev --quiet python -m dsh_si/u)
  })
})
