/** Small formatting helpers shared by tool renderers. */

export function formatHz(hz: number): string {
  const abs = Math.abs(hz)
  if (abs >= 1e9) return `${trim(hz / 1e9)} GHz`
  if (abs >= 1e6) return `${trim(hz / 1e6)} MHz`
  if (abs >= 1e3) return `${trim(hz / 1e3)} kHz`
  return `${trim(hz)} Hz`
}

function trim(value: number): string {
  return Number.parseFloat(value.toPrecision(4)).toString()
}

export function formatComplex(value: { re: number; im: number }): string {
  if (Math.abs(value.im) < 1e-12) return `${trim(value.re)}`
  const sign = value.im < 0 ? '-' : '+'
  return `${trim(value.re)} ${sign} j${trim(Math.abs(value.im))}`
}
