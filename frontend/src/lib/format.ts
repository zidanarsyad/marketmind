// Number and date formatting shared by the views (the same conventions as the Streamlit dashboard and the report).
import type { Scalar } from '@/types'

const isNum = (x: unknown): x is number => typeof x === 'number' && Number.isFinite(x)

/** Rupiah: trillions and billions abbreviated ("Rp 38.30 tn", "Rp 74.5 bn"), smaller amounts in full. */
export function fmtIdr(x: unknown): string {
  if (!isNum(x)) return 'n/a'
  const a = Math.abs(x)
  if (a >= 1e12) return `Rp ${(x / 1e12).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} tn`
  if (a >= 1e9) return `Rp ${(x / 1e9).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} bn`
  return `Rp ${Math.round(x).toLocaleString('en-US')}`
}

/** A share or growth rate: 0.0953 -> "+9.5%" (or "9.5%" without the sign). */
export function pct(x: unknown, sign = true): string {
  if (!isNum(x)) return 'n/a'
  const v = (x * 100).toFixed(1)
  return sign && x >= 0 ? `+${v}%` : `${v}%`
}

export function fmtInt(x: unknown): string {
  return isNum(x) ? Math.round(x).toLocaleString('en-US') : 'n/a'
}

/** A table cell: thousands separators for large numbers, at most four decimals for small ones. */
export function fmtCell(v: Scalar | undefined): string {
  if (v === null || v === undefined) return ''
  if (typeof v === 'boolean') return v ? 'yes' : 'no'
  if (typeof v === 'number') {
    if (!Number.isFinite(v)) return ''
    if (Number.isInteger(v)) return v.toLocaleString('en-US')
    const a = Math.abs(v)
    const digits = a >= 1000 ? 0 : a >= 100 ? 1 : a >= 1 ? 2 : 4
    return v.toLocaleString('en-US', { maximumFractionDigits: digits })
  }
  return String(v)
}

/** "20261110-222212" -> "10 Nov 2026, 22:22" (run ids are their start time). */
export function runDate(runId: string, started?: string | null): string {
  const m = /^(\d{4})(\d{2})(\d{2})-(\d{2})(\d{2})/.exec(runId)
  const d = started ? new Date(started.replace(' ', 'T')) : m ? new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5]) : null
  if (!d || Number.isNaN(d.getTime())) return runId
  return d.toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function seconds(x: unknown): string {
  if (!isNum(x)) return ''
  return x >= 90 ? `${Math.floor(x / 60)} min ${Math.round(x % 60)} s` : `${x.toFixed(x < 10 ? 1 : 0)} s`
}

export function titleCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}
