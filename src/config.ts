import { homedir } from 'node:os'
import { join } from 'node:path'
import Schema from '@deepseek-ai/schemastery'

export interface Config {
  /** Path or name of the `uv` executable used to launch the Python worker. */
  uvPath: string
  /**
   * Explicit interpreter command (e.g. `['/opt/venv/bin/python']`). When set,
   * uv is not used and the interpreter must already have the dsh_si
   * dependencies installed. Empty means "launch through uv".
   */
  pythonCommand: string[]
  /** Directory holding the worker's pyproject.toml; empty means the bundled copy. */
  pythonProjectDir: string
  /** Cooperative per-call budget enforced by the tool pipeline's timeout policy. */
  timeoutMs: number
  /** SIGTERM to SIGKILL escalation grace for the worker process tree. */
  graceMs: number
  /** Address-space cap the worker applies to itself (RLIMIT_AS); 0 disables. */
  maxMemoryMb: number
  /** Retained bytes of worker stdout (the JSON response). */
  maxStdoutBytes: number
  /** Retained bytes of worker stderr (attached to error messages). */
  maxStderrBytes: number
  /** Root directory for generated report folders. */
  outputDir: string
  /** Numerical tolerances for the quality checks. */
  tolerances: {
    /** Allowed excess of the largest singular value of S over 1. */
    passivity: number
    /** Allowed |Sij - Sji| before a sample is flagged non-reciprocal. */
    reciprocity: number
  }
  /** Return the key plot of each analysis inline as an image block. */
  inlinePlots: boolean
}

function defaultOutputDir(): string {
  const home = process.env['DSH_HOME'] ?? join(homedir(), '.dsh')
  return join(home, 'si-reports')
}

export const Config: Schema<Config> = Schema.object({
  uvPath: Schema.string().default('uv').description('uv executable used to launch the Python worker'),
  pythonCommand: Schema.array(Schema.string()).default([])
    .description('Explicit interpreter command; bypasses uv when non-empty'),
  pythonProjectDir: Schema.string().default('').description('Worker project dir; empty = bundled'),
  timeoutMs: Schema.number().min(1000).default(120_000).description('Per-call budget in ms'),
  graceMs: Schema.number().min(100).max(60_000).default(5_000).description('SIGTERM→SIGKILL grace in ms'),
  maxMemoryMb: Schema.number().min(0).default(2048).description('Worker RLIMIT_AS cap in MiB; 0 disables'),
  maxStdoutBytes: Schema.number().min(1024).default(4 * 1024 * 1024),
  maxStderrBytes: Schema.number().min(1024).default(64 * 1024),
  outputDir: Schema.string().default(defaultOutputDir()).description('Root for generated report folders'),
  tolerances: Schema.object({
    passivity: Schema.number().min(0).default(1e-6),
    reciprocity: Schema.number().min(0).default(1e-6),
  }).default({ passivity: 1e-6, reciprocity: 1e-6 }),
  inlinePlots: Schema.boolean().default(true),
})
