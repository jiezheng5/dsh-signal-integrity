/**
 * Wire contract shared with the Python worker (python/dsh_si/protocol.py).
 * A mirror test spawns the worker and asserts both copies agree.
 */

export const PROTOCOL_VERSION = 1

export const COMMANDS = ['ready', 'inspect', 'analyze'] as const
export type Command = typeof COMMANDS[number]

/** Domain error codes the worker reports; the plugin turns them into tool errors or results. */
export const WORKER_ERROR_CODES = [
  'bad_request',
  'unsupported_command',
  'file_not_found',
  'parse_error',
  'unsupported_format',
  'interpretation_invalid',
  'hash_mismatch',
  'numerical_error',
  'report_write_failed',
  'internal',
] as const
export type WorkerErrorCode = typeof WORKER_ERROR_CODES[number]

/** Plain JSON, structurally identical to DSH's `JsonValue` (no imports needed). */
export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue }
export type JsonObject = { [key: string]: JsonValue }

export interface WorkerRequest {
  protocol: typeof PROTOCOL_VERSION
  command: Command
  payload: JsonObject
  limits: { max_memory_mb?: number }
}

export interface WorkerErrorInfo {
  code: WorkerErrorCode
  message: string
  detail?: string
}

export type WorkerResponse =
  | { protocol: number; ok: true; result: JsonObject }
  | { protocol: number; ok: false; error: WorkerErrorInfo }

/** Narrow a JSON.parse result: parsed JSON is JSON by construction. */
function isObject(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * Parse the worker's single stdout line into a response.
 * @throws Error with a short reason when the text is not a well-formed response.
 */
export function parseWorkerResponse(text: string): WorkerResponse {
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch (error) {
    throw new Error(`worker stdout is not valid JSON (${(error as Error).message})`)
  }
  if (!isObject(parsed)) throw new Error('worker response is not a JSON object')
  if (parsed['protocol'] !== PROTOCOL_VERSION) {
    throw new Error(`worker speaks protocol v${String(parsed['protocol'])}, plugin expects v${PROTOCOL_VERSION}`)
  }
  if (parsed['ok'] === true) {
    if (!isObject(parsed['result'])) throw new Error('worker success response lacks a result object')
    return { protocol: PROTOCOL_VERSION, ok: true, result: parsed['result'] }
  }
  if (parsed['ok'] === false) {
    const error = parsed['error']
    if (!isObject(error) || typeof error['code'] !== 'string' || typeof error['message'] !== 'string') {
      throw new Error('worker error response lacks code/message')
    }
    const code = (WORKER_ERROR_CODES as readonly string[]).includes(error['code'])
      ? error['code'] as WorkerErrorCode
      : 'internal'
    return {
      protocol: PROTOCOL_VERSION,
      ok: false,
      error: {
        code,
        message: error['message'],
        ...typeof error['detail'] === 'string' ? { detail: error['detail'] } : {},
      },
    }
  }
  throw new Error('worker response lacks an ok flag')
}
