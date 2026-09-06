import { fileURLToPath } from 'node:url'
import type { Context } from '@deepseek-ai/cordis'
import type { SubprocessHandle, SubprocessOutcome } from '@deepseek-ai/dsh-subprocess'
import '@deepseek-ai/dsh-subprocess'
import type { Config } from './config.ts'
import { PROTOCOL_VERSION, parseWorkerResponse } from './protocol.ts'
import type { Command, JsonObject, WorkerErrorCode, WorkerRequest } from './protocol.ts'

/** Failure classes the plugin distinguishes when the worker does not return a result. */
export type WorkerFailureCode = WorkerErrorCode | 'spawn_failed' | 'cancelled' | 'crashed' | 'protocol'

export class WorkerError extends Error {
  constructor(readonly code: WorkerFailureCode, message: string, readonly detail?: string) {
    super(message)
    this.name = 'WorkerError'
  }
}

/**
 * Location of the bundled Python project. Resolved relative to this module:
 * `lib/index.js` (bundled) and `src/worker.ts` (tests) are both one level
 * below the package root, so `../python` holds from either.
 */
export function bundledPythonProjectDir(): string {
  return fileURLToPath(new URL('../python', import.meta.url))
}

const UV_NOT_FOUND_HINT = 'Install uv (https://docs.astral.sh/uv/) or set `pythonCommand` in the signal-integrity '
  + 'plugin config to an interpreter that already has the dsh_si dependencies installed.'

function tail(text: string, maxChars = 2000): string {
  const trimmed = text.trim()
  return trimmed.length <= maxChars ? trimmed : `…${trimmed.slice(-maxChars)}`
}

/** Spawns one worker process per call and exchanges a single JSON request/response. */
export class WorkerClient {
  constructor(private readonly ctx: Context, private readonly config: Config) {}

  get projectDir(): string {
    return this.config.pythonProjectDir === '' ? bundledPythonProjectDir() : this.config.pythonProjectDir
  }

  /** Human-readable description of how the worker is launched, for diagnostics. */
  get launcher(): string {
    return this.argv().join(' ')
  }

  argv(): string[] {
    if (this.config.pythonCommand.length > 0) {
      return [...this.config.pythonCommand, '-m', 'dsh_si']
    }
    return [
      this.config.uvPath, 'run', '--project', this.projectDir, '--frozen', '--no-dev', '--quiet',
      'python', '-m', 'dsh_si',
    ]
  }

  async call(command: Command, payload: JsonObject, signal: AbortSignal): Promise<JsonObject> {
    const request: WorkerRequest = {
      protocol: PROTOCOL_VERSION,
      command,
      payload,
      limits: this.config.maxMemoryMb > 0 ? { max_memory_mb: this.config.maxMemoryMb } : {},
    }
    if (signal.aborted) throw new WorkerError('cancelled', `${command} cancelled before the worker started`)

    let handle: SubprocessHandle
    try {
      handle = this.ctx.subprocess.spawn({
        argv: this.argv(),
        cwd: this.projectDir,
        stdio: {
          stdin: { data: JSON.stringify(request) },
          stdout: { maxBytes: this.config.maxStdoutBytes },
          stderr: { maxBytes: this.config.maxStderrBytes },
        },
        graceMs: this.config.graceMs,
        signal,
        env: { PYTHONUNBUFFERED: '1', UV_NO_PROGRESS: '1', MPLBACKEND: 'Agg' },
      })
    } catch (error) {
      throw this.spawnFailure(error)
    }

    let outcome: SubprocessOutcome
    try {
      outcome = await handle.done
    } catch (error) {
      throw this.spawnFailure(error)
    }
    const stdout = handle.collected.stdout?.readFrom(0).text ?? ''
    const stderr = handle.collected.stderr?.readFrom(0).text ?? ''

    if (signal.aborted) {
      throw new WorkerError('cancelled', `${command} cancelled; worker terminated`, tail(stderr))
    }
    if (handle.pid === -1) throw this.spawnFailure(new Error(tail(stderr) || 'spawn failed'))
    if (stdout.trim() === '') {
      const how = outcome.signal !== null ? `killed by ${outcome.signal}` : `exit code ${String(outcome.exitCode)}`
      throw new WorkerError('crashed', `worker produced no response (${how})`, tail(stderr))
    }
    let response
    try {
      response = parseWorkerResponse(stdout)
    } catch (error) {
      throw new WorkerError('protocol', (error as Error).message, tail(stderr) || tail(stdout))
    }
    if (!response.ok) {
      throw new WorkerError(response.error.code, response.error.message, response.error.detail ?? tail(stderr))
    }
    return response.result
  }

  private spawnFailure(error: unknown): WorkerError {
    const message = error instanceof Error ? error.message : String(error)
    const program = this.argv()[0] ?? ''
    const notFound = /ENOENT|not found/iu.test(message)
    if (notFound && this.config.pythonCommand.length === 0) {
      return new WorkerError('spawn_failed', `cannot start the Python worker: \`${program}\` was not found. ${UV_NOT_FOUND_HINT}`, message)
    }
    if (notFound) {
      return new WorkerError('spawn_failed', `cannot start the Python worker: \`${program}\` (from pythonCommand) was not found.`, message)
    }
    return new WorkerError('spawn_failed', `cannot start the Python worker: ${message}`)
  }
}
