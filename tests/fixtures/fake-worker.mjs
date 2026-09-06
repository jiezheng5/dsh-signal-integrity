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
