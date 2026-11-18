// The audit gate (audit-gate.mjs): which advisories fail it, and how an exception stops holding.
import { describe, expect, it } from 'vitest'
import { gate } from './audit-gate.mjs'

const PICOMATCH = { advisory: 'GHSA-fc5q-39xc-vjpf', package: 'picomatch', until: '2027-01-31', reason: 'no fixed release yet' }
const BREAKING_ONLY = { name: 'vite', version: '6.2.7', isSemVerMajor: true } // what npm offers for picomatch today

/** An `npm audit --json` report, shaped as npm 11 writes it: each advisory on its package, dependents naming it. */
function report(...advisories) {
  const vulnerabilities = {}
  const counts = { info: 0, low: 0, moderate: 0, high: 0, critical: 0 }
  for (const { name, id, severity, fix = false, dependents = [] } of advisories) {
    const via = [{ source: 1, name, dependency: name, title: `${name} is slow`, url: `https://github.com/advisories/${id}`, severity, range: '<=4.0.7' }]
    vulnerabilities[name] = { name, severity, isDirect: false, via, effects: dependents, range: '*', nodes: [], fixAvailable: fix }
    for (const d of dependents) vulnerabilities[d] = { name: d, severity, isDirect: true, via: [name], effects: [], fixAvailable: fix }
    counts[severity] += 1 + dependents.length
  }
  return { auditReportVersion: 2, vulnerabilities, metadata: { vulnerabilities: counts } }
}
const picomatch = (fix = BREAKING_ONLY) =>
  ({ name: 'picomatch', id: 'GHSA-fc5q-39xc-vjpf', severity: 'high', fix, dependents: ['vite', 'vitest'] })

describe('audit gate', () => {
  it('passes an excepted advisory with no fix, up to and including its date', () => {
    const r = gate(report(picomatch()), [PICOMATCH], '2027-01-31')
    expect(r.failing).toEqual([])
    expect(r.excepted.map((a) => a.id)).toEqual(['GHSA-fc5q-39xc-vjpf'])
  })

  it('fails it again the day after the date', () => {
    const r = gate(report(picomatch()), [PICOMATCH], '2027-02-01')
    expect(r.failing.map((a) => a.why)).toEqual(['its exception ran out on 2027-01-31: look at it again'])
  })

  it('fails it as soon as npm audit fix can fix it', () => {
    for (const fix of [true, { name: 'vite', version: '8.3.9', isSemVerMajor: false }]) {
      const r = gate(report(picomatch(fix)), [PICOMATCH], '2026-11-18')
      expect(r.failing).toHaveLength(1)
      expect(r.failing[0].why).toMatch(/npm audit fix/)
    }
  })

  it('fails an advisory nobody excepted, lists moderate ones and names an exception npm no longer reports', () => {
    const r = gate(report({ name: 'vite', id: 'GHSA-new1', severity: 'critical' }, { name: 'glob', id: 'GHSA-mod1', severity: 'moderate' }),
      [PICOMATCH], '2026-11-18')
    expect(r.failing.map((a) => a.id)).toEqual(['GHSA-new1'])
    expect(r.listed.map((a) => a.id)).toEqual(['GHSA-mod1'])
    expect(r.unused).toEqual([PICOMATCH])
    // an exception covers its own package only
    const other = gate(report({ name: 'tinyglobby', id: 'GHSA-fc5q-39xc-vjpf', severity: 'high' }), [PICOMATCH], '2026-11-18')
    expect(other.failing).toHaveLength(1)
  })

  it('passes a clean report', () => {
    expect(gate(report(), [], '2026-11-18')).toEqual({ failing: [], excepted: [], listed: [], unused: [] })
  })

  it('fails what it cannot read', () => {
    const today = '2026-11-18'
    expect(() => gate({ error: { code: 'ENOTFOUND', summary: 'registry unreachable' } }, [], today)).toThrow(/not an npm audit report/)
    expect(() => gate({ ...report(), auditReportVersion: 3 }, [], today)).toThrow(/not an npm audit report/)
    expect(() => gate(report(), [{ ...PICOMATCH, until: '31 January 2027' }], today)).toThrow(/needs advisory/)
    expect(() => gate(report(), [{ ...PICOMATCH, reason: '' }], today)).toThrow(/needs advisory/)
    const unknown = report({ name: 'vite', id: 'GHSA-odd1', severity: 'unrated' })
    expect(gate(unknown, [], today).failing).toHaveLength(1) // an unknown severity fails rather than slipping through
    const untraced = { ...report(), metadata: { vulnerabilities: { high: 2 } } }
    expect(() => gate(untraced, [], today)).toThrow(/could not trace/)
  })
})
