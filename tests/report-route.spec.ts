import { mkdtempSync, rmSync, symlinkSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'
import { Context, Service } from '@deepseek-ai/cordis'
import WebServer from '@deepseek-ai/dsh-host-webserver'
import type { ConnectionRequestRejection } from '@deepseek-ai/dsh-client-connection'
import '@deepseek-ai/dsh-client-connection'
import { callTool, fakeWorker, mountPlugin, textOf } from './harness.ts'

/**
 * Stand-in for the browser-auth half of `ctx.connection`: the route only asks
 * one question of it (may this request proceed?), so that is all it answers.
 */
class FakeConnection extends Service {
  rejection: ConnectionRequestRejection = undefined
  constructor(ctx: Context) {
    super(ctx, 'connection')
  }

  requestRejection(): ConnectionRequestRejection {
    return this.rejection
  }
}

const contexts: Context[] = []
const dirs: string[] = []
afterEach(async () => {
  for (const ctx of contexts.splice(0)) await ctx.fiber.dispose()
  for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true })
})

interface Mounted {
  ctx: Context
  outputDir: string
  connection: FakeConnection
  base: string
}

/**
 * Plugin plus a real loopback WebServer on an OS-assigned port and the fake
 * connection guard. `servicesFirst` mounts the web services before the plugin
 * (the bundle order); the default mounts them afterwards, so the route must
 * bind late through `ctx.inject`.
 */
async function mountWithWeb(servicesFirst = false): Promise<Mounted> {
  const outputDir = mkdtempSync(join(tmpdir(), 'si-route-'))
  dirs.push(outputDir)
  const services = async (ctx: Context): Promise<void> => {
    await ctx.plugin(FakeConnection)
    await ctx.plugin(WebServer, { host: '127.0.0.1', port: 0 })
  }
  let ctx: Context
  if (servicesFirst) {
    ctx = new Context()
    await services(ctx)
    await mountPlugin({ outputDir, pythonCommand: fakeWorker('analyze') }, ctx)
  } else {
    ctx = await mountPlugin({ outputDir, pythonCommand: fakeWorker('analyze') })
    await services(ctx)
  }
  contexts.push(ctx)
  const connection = ctx.get('connection') as unknown as FakeConnection
  const base = `http://127.0.0.1:${ctx.webServer.port}`
  return { ctx, outputDir, connection, base }
}

const HASH = 'a'.repeat(64)

/** Run si_analyze with the fake worker and return what the model reads. */
async function analyze(ctx: Context): Promise<string> {
  const result = await callTool(ctx, 'si_analyze', { path: '/data/fake.s2p', hash: HASH, interpretation: { device: 'inductor', terminal_mode: 'one_port' } })
  expect(result.isError).toBe(false)
  return textOf(result)
}

const LINK_LINE = 'Report (open in browser): '

describe('report route over the DSH web server', () => {
  it('returns an http report_url that serves the report directory', async () => {
    const { ctx, base } = await mountWithWeb()
    const text = await analyze(ctx)
    expect(text).toContain(`${LINK_LINE}${base}/si-reports/fake/report.html`)

    const html = await fetch(`${base}/si-reports/fake/report.html`)
    expect(html.status).toBe(200)
    expect(html.headers.get('content-type')).toBe('text/html; charset=utf-8')
    expect(await html.text()).toContain('<html')

    const png = await fetch(`${base}/si-reports/fake/s_magnitude.png`)
    expect(png.status).toBe(200)
    expect(png.headers.get('content-type')).toBe('image/png')

    const json = await fetch(`${base}/si-reports/fake/results.json`)
    expect(json.headers.get('content-type')).toBe('application/json')
  })

  it('serves nothing outside the report root: traversal, symlink escape, unknown type, missing file', async () => {
    const { ctx, outputDir, base } = await mountWithWeb(true)
    await analyze(ctx)
    const outside = mkdtempSync(join(tmpdir(), 'si-outside-'))
    dirs.push(outside)
    writeFileSync(join(outside, 'secret.html'), '<html>secret</html>')
    symlinkSync(join(outside, 'secret.html'), join(outputDir, 'fake', 'escape.html'))
    writeFileSync(join(outputDir, 'fake', 'notes.exe'), 'x')

    expect((await fetch(`${base}/si-reports/%2e%2e/package.json`)).status).toBe(404)
    expect((await fetch(`${base}/si-reports/fake/escape.html`)).status).toBe(404)
    expect((await fetch(`${base}/si-reports/fake/notes.exe`)).status).toBe(404)
    expect((await fetch(`${base}/si-reports/fake/missing.html`)).status).toBe(404)
    expect((await fetch(`${base}/si-reports/fake`)).status).toBe(404)
    expect((await fetch(`${base}/si-reports/fake/report.html`, { method: 'POST' })).status).toBe(405)
  })

  it('applies the connection guard before reading any file', async () => {
    const { ctx, connection, base } = await mountWithWeb(true)
    await analyze(ctx)
    connection.rejection = 401
    const denied = await fetch(`${base}/si-reports/fake/report.html`)
    expect(denied.status).toBe(401)
    connection.rejection = 403
    expect((await fetch(`${base}/si-reports/fake/report.html`)).status).toBe(403)
  })

  it('binds the route when the web services load before the plugin', async () => {
    const { ctx, base } = await mountWithWeb(true)
    const text = await analyze(ctx)
    expect(text).toContain(`${LINK_LINE}${base}/si-reports/fake/report.html`)
    expect((await fetch(`${base}/si-reports/fake/report.html`)).status).toBe(200)
  })

  it('omits report_url without a web server and stays silent about it', async () => {
    const outputDir = mkdtempSync(join(tmpdir(), 'si-noweb-'))
    dirs.push(outputDir)
    const ctx = await mountPlugin({ outputDir, pythonCommand: fakeWorker('analyze') })
    contexts.push(ctx)
    const text = await analyze(ctx)
    expect(text).not.toContain(LINK_LINE)
    expect(text).toContain('Report directory: ')
  })
})
