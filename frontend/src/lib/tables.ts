import type { TablePayload } from '@/types'

/** Turn the API's {columns, data} into rows keyed c0, c1, ... (a column name with a dot would read as a nested path). */
export function toGrid(t: TablePayload | null | undefined) {
  if (!t) return { columns: [], rows: [] as Record<string, unknown>[] }
  const columns = t.columns.map((name, i) => ({ field: `c${i}`, header: name }))
  const rows = t.data.map((r) => Object.fromEntries(r.map((v, i) => [`c${i}`, v])))
  return { columns, rows }
}

/** Rows as plain objects keyed by column name, for views that read named values. */
export function toRecords(t: TablePayload | null | undefined): Record<string, unknown>[] {
  if (!t) return []
  return t.data.map((r) => Object.fromEntries(t.columns.map((c, i) => [c, r[i]])))
}
