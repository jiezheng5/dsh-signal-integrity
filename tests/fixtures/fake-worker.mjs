// Stand-in for `python -m dsh_si` so the TypeScript tests exercise spawning,
// stdin/stdout framing, error classification, and cancellation without uv.
// Usage: node fake-worker.mjs <mode>   (the plugin appends `-m dsh_si`, ignored)
import { stdin, stdout, stderr, exit } from 'node:process'

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
      },
    })
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
