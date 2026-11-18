// Calls to this page's own server: an enterprise (server.py) or the Global Control Center (control.py). The page never
// calls another node's server: the Control Center reaches the enterprises itself, through their APIs.
import { getJson, postJson } from '@/api'
import type {
  ControlNode,
  DatasetInfo,
  DatasetPage,
  EcoMessage,
  EcoNode,
  EnterpriseDecision,
  EnterpriseStatus,
  Kpis,
  MessagePage,
  Mode,
  OwnNegotiation,
  RunRecord,
  Scenario,
} from './types'

const enc = encodeURIComponent
const q = (params: Record<string, string | number | undefined | null>) => {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${k}=${enc(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}

/** Which kind of server this page came from. An enterprise and the Control Center answer /api/node; the MarketMind
 * research API does not (404), and then this page is the research app. */
export async function detectNode(): Promise<EcoNode | null> {
  try {
    const res = await fetch('/api/node', { headers: { Accept: 'application/json' } })
    if (!res.ok) return null
    const node = await res.json()
    return node && (node.kind === 'enterprise' || node.kind === 'control') ? (node as EcoNode) : null
  } catch {
    return null
  }
}

export const enterpriseApi = {
  status: () => getJson<EnterpriseStatus>('/api/status'),
  kpis: () => getJson<Kpis>('/api/kpis'),
  datasets: (role: string) => getJson<{ role: string; store: string; datasets: DatasetInfo[] }>(`/api/data${q({ role })}`),
  dataset: (table: string, role: string, limit = 100, offset = 0) =>
    getJson<DatasetPage>(`/api/data/${enc(table)}${q({ role, limit, offset })}`),
  messages: (limit = 500) => getJson<{ total: number; rows: EcoMessage[] }>(`/api/messages${q({ limit })}`),
  decisions: (limit = 500) => getJson<{ total: number; rows: EnterpriseDecision[] }>(`/api/decisions${q({ limit })}`),
  negotiations: () => getJson<{ threads: OwnNegotiation[] }>('/api/negotiations'),
  shared: (audience: 'partner' | 'control') =>
    getJson<{ enterprise: string; audience: string; mode: Mode; view: Record<string, unknown> }>(
      `/api/a2a/shared${q({ audience })}`,
    ),
  agentCard: () => getJson<Record<string, unknown>>('/api/a2a/agent-card'),
}

export const controlApi = {
  node: () => getJson<ControlNode>('/api/node'),
  enterprises: () => getJson<{ enterprises: EnterpriseStatus[] }>('/api/control/enterprises'),
  scenarios: () => getJson<{ scenarios: Scenario[] }>('/api/control/scenarios'),
  runs: () => getJson<{ runs: RunRecord[]; busy: string | null }>('/api/control/runs'),
  run: (id: string) => getJson<RunRecord>(`/api/control/runs/${enc(id)}`),
  start: (scenario: string, mode: Mode | 'compare', seed: number) =>
    postJson<{ id: string; status: string }>('/api/control/runs', { scenario, mode, seed }),
  messages: (id: string, mode: Mode, opts: { enterprise?: string; task?: string; limit?: number; offset?: number } = {}) =>
    getJson<MessagePage>(`/api/control/runs/${enc(id)}/messages${q({ mode, ...opts })}`),
}
