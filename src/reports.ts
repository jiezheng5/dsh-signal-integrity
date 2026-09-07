/**
 * Serve generated report directories over the DSH web server so the chat can
 * carry a clickable link. The Web client turns only http(s) hrefs into anchors;
 * a `file://` path is rendered as inert text. The route binds late through
 * `ctx.inject`: without `webServer` and `connection` (CLI or ACP deployments)
 * nothing is registered and `reportUrl` answers undefined.
 */

import { createReadStream } from 'node:fs'
import { realpath, stat } from 'node:fs/promises'
import type { IncomingMessage, ServerResponse } from 'node:http'
import { extname, relative, resolve, sep } from 'node:path'
import type { Context } from '@deepseek-ai/cordis'
import type {} from '@deepseek-ai/dsh-host-webserver'
import type {} from '@deepseek-ai/dsh-client-connection'

/** URL prefix the route claims on the web server. */
export const REPORT_ROUTE = '/si-reports'

/** Only report artifacts are served; anything else under the root is a 404. */
const CONTENT_TYPES: Readonly<Record<string, string>> = {
  '.html': 'text/html; charset=utf-8',
  '.png': 'image/png',
  '.csv': 'text/csv; charset=utf-8',
  '.json': 'application/json',
  '.txt': 'text/plain; charset=utf-8',
}

/** Answers "where can the browser open this report?" for the tools. */
export interface ReportLinks {
  /** http URL of a file inside `outputDir`, or undefined when no web server is live. */
  reportUrl(filePath: string): string | undefined
}

/**
 * Register the report route whenever the web services are available.
 * @param ctx - plugin context.
 * @param outputDir - report root; files outside it are never served.
 */
export function registerReportRoute(ctx: Context, outputDir: string): ReportLinks {
  const root = resolve(outputDir)
  let base: string | undefined

  ctx.inject(['connection', 'webServer'], (webCtx) => {
    const { webServer, connection } = webCtx
    // The all-interfaces bind has no single browser-facing host; localhost is the honest default.
    const host = webServer.host === '0.0.0.0' ? 'localhost' : webServer.host
    base = `http://${host}:${webServer.port}`
    webCtx.effect(() => {
      const dispose = webServer.register({
        kind: 'prefix',
        path: REPORT_ROUTE,
        handler: (req, res) => serve(req, res, root, () => connection.requestRejection(req)),
      })
      return () => {
        dispose()
        base = undefined
      }
    }, 'signal-integrity: report route')
  })

  return {
    reportUrl(filePath) {
      if (base === undefined) return undefined
      const rel = relative(root, resolve(filePath))
      if (rel === '' || rel.startsWith('..') || rel.includes(sep + '..')) return undefined
      return `${base}${REPORT_ROUTE}/${rel.split(sep).map(encodeURIComponent).join('/')}`
    },
  }
}

async function serve(
  req: IncomingMessage,
  res: ServerResponse,
  root: string,
  rejection: () => 401 | 403 | undefined,
): Promise<void> {
  if (req.method !== 'GET' && req.method !== 'HEAD') return end(res, 405)
  const denied = rejection()
  if (denied !== undefined) return end(res, denied)

  const target = await resolveInsideRoot(req.url ?? '/', root)
  if (target === undefined) return end(res, 404)
  const type = CONTENT_TYPES[extname(target).toLowerCase()]
  if (type === undefined) return end(res, 404)

  let size: number
  try {
    const info = await stat(target)
    if (!info.isFile()) return end(res, 404)
    size = info.size
  } catch {
    return end(res, 404)
  }
  res.writeHead(200, { 'content-type': type, 'content-length': size, 'cache-control': 'no-store' })
  if (req.method === 'HEAD') {
    res.end()
    return
  }
  createReadStream(target).on('error', () => { res.destroy() }).pipe(res)
}

/**
 * Map a request URL to a real file path under `root`, or undefined. `resolve`
 * collapses `..`; `realpath` then defeats symlinks that point outside.
 */
async function resolveInsideRoot(url: string, root: string): Promise<string | undefined> {
  let pathname: string
  try {
    pathname = decodeURIComponent(new URL(url, 'http://x').pathname)
  } catch {
    return undefined
  }
  if (!pathname.startsWith(REPORT_ROUTE + '/')) return undefined
  const candidate = resolve(root, '.' + pathname.slice(REPORT_ROUTE.length))
  try {
    const [realRoot, realTarget] = await Promise.all([realpath(root), realpath(candidate)])
    return realTarget.startsWith(realRoot + sep) ? realTarget : undefined
  } catch {
    return undefined
  }
}

function end(res: ServerResponse, status: number): void {
  res.writeHead(status)
  res.end()
}
