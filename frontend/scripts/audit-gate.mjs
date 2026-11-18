// The front end's audit gate. `npm run audit:gate`, which the audit workflow runs, pipes `npm audit --json` into it.
//
// Like `npm audit --audit-level=high`, it fails on any high or critical advisory, with one difference: an advisory
// listed in audit-exceptions.json does not fail it while `npm audit fix` cannot fix it, and only until the date given
// there. An advisory with no fixed release can wait for one without keeping the gate red, and the gate still fails on
// a new advisory, as soon as a fix can be installed, and once the date has passed. Moderate and low advisories are
// listed, as npm audit lists them. A report it cannot read fails the gate.
import { readFileSync } from 'node:fs'
import { pathToFileURL } from 'node:url'

const LISTED = new Set(['info', 'low', 'moderate']) // any other severity, unknown ones included, fails
const DATE = /^\d{4}-\d{2}-\d{2}$/

/** Whether `npm audit fix` can fix a vulnerable package without a breaking change (npm's `fixAvailable`). */
const fixable = (fix) => fix === true || (typeof fix === 'object' && fix !== null && !fix.isSemVerMajor)

/**
 * Sorts the advisories of an `npm audit --json` report into those that fail the gate, those excepted and those only
 * listed; `unused` are exceptions npm no longer reports. `today` is an ISO date: an exception holds up to and
 * including its `until` date.
 */
export function gate(report, exceptions, today) {
  if (report?.auditReportVersion !== 2 || typeof report.vulnerabilities !== 'object' || report.vulnerabilities === null) {
    throw new Error(`not an npm audit report: ${String(JSON.stringify(report?.error ?? report)).slice(0, 300)}`)
  }
  if (!Array.isArray(exceptions)) throw new Error('audit-exceptions.json must hold a list')
  for (const e of exceptions) {
    if (!e?.advisory || !e.package || !DATE.test(e.until ?? '') || !e.reason) {
      throw new Error(`an exception needs advisory, package, until (YYYY-MM-DD) and reason: ${JSON.stringify(e)}`)
    }
  }

  // the advisories themselves; a package vulnerable only through another one names it with a string in `via`
  const advisories = new Map()
  for (const pkg of Object.values(report.vulnerabilities)) {
    for (const via of pkg.via ?? []) {
      if (typeof via !== 'object' || via === null) continue
      const id = via.url?.split('/').pop() || `npm-${via.source}`
      if (!advisories.has(id)) {
        advisories.set(id, {
          id, package: via.name, severity: via.severity, title: via.title, range: via.range, url: via.url,
          fixable: fixable(report.vulnerabilities[via.name]?.fixAvailable),
        })
      }
    }
  }

  const result = { failing: [], excepted: [], listed: [], unused: [] }
  for (const a of advisories.values()) {
    const e = exceptions.find((x) => x.advisory === a.id && x.package === a.package)
    if (LISTED.has(a.severity)) result.listed.push(a)
    else if (!e) result.failing.push({ ...a, why: 'not excepted' })
    else if (a.fixable) result.failing.push({ ...a, why: '`npm audit fix` can fix it now: run it, then drop the exception' })
    else if (today > e.until) result.failing.push({ ...a, why: `its exception ran out on ${e.until}: look at it again` })
    else result.excepted.push({ ...a, until: e.until, reason: e.reason })
  }
  result.unused = exceptions.filter((e) => !advisories.has(e.advisory))

  // npm counts vulnerable packages; if it counts high or critical ones, some advisory must explain them
  const counts = report.metadata?.vulnerabilities ?? {}
  if ((counts.high ?? 0) + (counts.critical ?? 0) > 0 && !result.failing.length && !result.excepted.length) {
    throw new Error('npm reports high or critical vulnerabilities that the gate could not trace to an advisory')
  }
  return result
}

async function main() {
  let raw = ''
  for await (const chunk of process.stdin) raw += chunk
  const exceptions = JSON.parse(readFileSync(new URL('../audit-exceptions.json', import.meta.url), 'utf8'))
  const { failing, excepted, listed, unused } = gate(JSON.parse(raw), exceptions, new Date().toISOString().slice(0, 10))
  const line = (a) => `${a.severity} ${a.id}, ${a.package} ${a.range}: ${a.title}`
  for (const a of failing) console.log(`FAILS     ${line(a)} (${a.why})`)
  for (const a of excepted) console.log(`excepted  ${line(a)}; until ${a.until}: ${a.reason}`)
  for (const a of listed) console.log(`listed    ${line(a)}`)
  for (const e of unused) console.log(`unused    the exception for ${e.advisory} (${e.package}): npm no longer reports it, drop it`)
  const n = failing.length
  console.log(n ? `audit gate: ${n} ${n === 1 ? 'advisory fails' : 'advisories fail'}` : 'audit gate: passed')
  process.exitCode = n ? 1 : 0
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((err) => {
    console.error(`audit gate: ${err.message}`)
    process.exitCode = 1
  })
}
