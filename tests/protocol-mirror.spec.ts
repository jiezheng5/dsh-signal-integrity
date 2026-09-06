import { execFileSync } from 'node:child_process'
import { describe, expect, it } from 'vitest'
import { COMMANDS, PROTOCOL_VERSION, WORKER_ERROR_CODES } from '../src/protocol.ts'
import { bundledPythonProjectDir } from '../src/worker.ts'

function uvAvailable(): boolean {
  try {
    execFileSync('uv', ['--version'], { stdio: 'ignore' })
    return true
  } catch {
    return false
  }
}

const probe = 'import json; from dsh_si import protocol as p; '
  + 'print(json.dumps({"version": p.PROTOCOL_VERSION, "commands": list(p.COMMANDS), "errors": list(p.ERROR_CODES)}))'

/** Drift guard: the Python worker's copy of the wire constants must equal this package's. */
describe.skipIf(!uvAvailable())('protocol mirror', () => {
  it('matches the Python worker constants', () => {
    const out = execFileSync(
      'uv',
      ['run', '--project', bundledPythonProjectDir(), '--frozen', '--no-dev', '--quiet', 'python', '-c', probe],
      { encoding: 'utf8' },
    )
    const python = JSON.parse(out.trim()) as { version: number; commands: string[]; errors: string[] }
    expect(python.version).toBe(PROTOCOL_VERSION)
    expect(python.commands).toEqual([...COMMANDS])
    expect(python.errors).toEqual([...WORKER_ERROR_CODES])
  })
})
