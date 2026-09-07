// Stand-in for `python -m dsh_si` so the TypeScript tests exercise spawning,
// stdin/stdout framing, error classification, and cancellation without uv.
// Usage: node fake-worker.mjs <mode>   (the plugin appends `-m dsh_si`, ignored)
import { stdin, stdout, stderr, exit } from 'node:process'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

// 1x1 white PNG so image tests have real bytes to attach.
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII=', 'base64')
function writePlot(payload) {
  if (typeof payload.output_dir !== 'string') return []
  const dir = join(payload.output_dir, 'fake')
  mkdirSync(dir, { recursive: true })
  const path = join(dir, 's_magnitude.png')
  writeFileSync(path, PNG)
  return [{ name: 's_magnitude', path, title: '|S| overview of fake.s2p' }]
}

const mode = process.argv[2] ?? 'ok'
let raw = ''
stdin.setEncoding('utf8')
for await (const chunk of stdin) raw += chunk
const request = JSON.parse(raw)

const reply = (doc) => { stdout.write(JSON.stringify(doc) + '\n') }

switch (mode) {
  case 'ok':
    reply({
      protocol: 1,
      ok: true,
      result: {
        worker_version: '0.0.0-fake',
        python: { version: '3.13.0', implementation: 'CPython', executable: '/fake/python' },
        packages: { skrf: '2.1.0', numpy: '2.5.3', scipy: '1.18.1', matplotlib: '3.11.1' },
        ready: true,
        echo: request,
      },
    })
    break
  case 'missing':
    reply({
      protocol: 1,
      ok: true,
      result: {
        worker_version: '0.0.0-fake',
        python: { version: '3.13.0', implementation: 'CPython', executable: '/fake/python' },
        packages: { skrf: null, numpy: '2.5.3', scipy: '1.18.1', matplotlib: null },
        ready: false,
      },
    })
    break
  case 'inspect':
    reply({
      protocol: 1,
      ok: true,
      result: {
        path: request.payload.path,
        hash: 'a'.repeat(64),
        metadata: {
          file_name: 'fake.s2p', n_ports: 2, n_freq: 401, f_min_hz: 1e7, f_max_hz: 2e10,
          frequency_unit: 'ghz', parameter: 's', format: 'ri', touchstone_version: '1.0',
          reference_impedance: [{ re: 50, im: 0 }, { re: 50, im: 0 }], port_names: null, comments: '',
          mixed_mode_hint: false, size_bytes: 1234,
        },
        quality: {
          passivity: { passive: true, tolerance: request.payload.tolerances?.passivity ?? -1, sigma_max_worst: 0.9991, worst_freq_hz: 1e7, violation_count: 0, violation_freqs_hz: [], method: 'svd', p370: { score_percent: 100, evaluation: 'good' } },
          reciprocity: { applicable: true, reciprocal: false, tolerance: 1e-6, max_abs_diff_worst: 0.0123, worst_freq_hz: 5e9, violation_count: 7, violation_freqs_hz: [], method: 'diff', p370: { score_percent: 91.2, evaluation: 'acceptable' } },
          causality: { applicable: true, score_percent: 100, verdict: 'good', note: 'screening only', method: 'P370', p370: { score_percent: 100, evaluation: 'good' } },
          p370_method: 'IEEE P370 via scikit-rf',
        },
        warnings: ['header comments mention mixed-mode terms'],
        questions: [{ id: 'device', question: 'What device?', options: [{ label: 'inductor' }] }],
        required_by_device: { inductor: ['terminal_mode'] },
        report_dir: typeof request.payload.output_dir === 'string' ? join(request.payload.output_dir, 'fake') : null,
        plots: writePlot(request.payload),
      },
    })
    break
  case 'analyze':
    reply({
      protocol: 1,
      ok: true,
      result: {
        path: request.payload.path,
        hash: request.payload.hash,
        device: request.payload.interpretation?.device ?? 'unknown',
        interpretation: request.payload.interpretation,
        status: 'complete',
        report_dir: join(request.payload.output_dir, 'fake'),
        files: [join(request.payload.output_dir, 'fake', 's_magnitude.png'), join(request.payload.output_dir, 'fake', 'results.json')],
        plots: writePlot(request.payload),
        summary: { terminal_mode: 'one_port', srf_hz: 1.59e9, L_h: { median: 1e-8, n_valid: 400 } },
        warnings: [],
      },
    })
    break
  case 'hash-mismatch':
    reply({ protocol: 1, ok: false, error: { code: 'hash_mismatch', message: 'fake.s2p changed since it was inspected; run si_inspect again' } })
    exit(1)
    break
  case 'domain-error':
    reply({ protocol: 1, ok: false, error: { code: 'parse_error', message: 'fake.s2p: cannot parse Touchstone header/data', detail: 'ValueError: boom' } })
    exit(1)
    break
  case 'error':
    reply({ protocol: 1, ok: false, error: { code: 'parse_error', message: 'bad touchstone', detail: 'line 3' } })
    exit(1)
    break
  case 'crash':
    stderr.write('Traceback: boom\n')
    exit(3)
    break
  case 'garbage':
    stdout.write('this is not json\n')
    break
  case 'wrong-protocol':
    reply({ protocol: 42, ok: true, result: {} })
    break
  case 'hang':
    stderr.write('hanging\n')
    setTimeout(() => {}, 120_000)
    break
  default:
    stderr.write(`unknown mode ${mode}\n`)
    exit(2)
}
