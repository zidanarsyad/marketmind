// Typed client for the MarketMind API. Every call goes to the same origin: the FastAPI server in production, or the
// Vite dev server, which forwards /api to it.
import type {
  AppConfig,
  ChatAnswer,
  ChatMessage,
  DataAnswer,
  DatasetPreview,
  Decision,
  EvaluationState,
  Finding,
  LlmStatus,
  PlotlyFigure,
  Recommendation,
  RunListItem,
  RunSummary,
  SentimentResult,
  StudyRequest,
  StudySnapshot,
  Swot,
  TablePayload,
  TraceEvent,
} from './types'

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(detail)
    this.name = 'ApiError'
  }
}

async function request<T>(method: 'GET' | 'POST', path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: { Accept: 'application/json' } }
  if (method === 'POST') {
    // the API only accepts changes sent as JSON from this page
    init.headers = { ...init.headers, 'Content-Type': 'application/json' }
    init.body = JSON.stringify(body ?? {})
  }
  let res: Response
  try {
    res = await fetch(path, init)
  } catch {
    throw new ApiError(0, 'The MarketMind server is not reachable. Is `python -m api` running?')
  }
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`
    try {
      const j = await res.json()
      if (typeof j.detail === 'string') detail = j.detail
      else if (Array.isArray(j.detail)) detail = j.detail.map((d: { msg?: string }) => d.msg ?? String(d)).join('; ')
    } catch {
      /* not JSON */
    }
    throw new ApiError(res.status, detail)
  }
  return (await res.json()) as T
}

const get = <T>(path: string) => request<T>('GET', path)
const post = <T>(path: string, body?: unknown) => request<T>('POST', path, body)
const enc = encodeURIComponent

export const api = {
  config: () => get<AppConfig>('/api/config'),
  llm: () => get<LlmStatus>('/api/llm'),
  pingLlm: () => post<{ ok: boolean; message: string }>('/api/llm/ping'),
  generateData: () => post<{ ok: boolean; ready: boolean }>('/api/data/generate'),

  runs: () => get<RunListItem[]>('/api/runs'),
  run: (id: string) => get<RunSummary>(`/api/runs/${enc(id)}`),
  findings: (id: string) => get<Finding[]>(`/api/runs/${enc(id)}/findings`),
  recommendations: (id: string) => get<Recommendation[]>(`/api/runs/${enc(id)}/recommendations`),
  swot: (id: string) => get<Swot>(`/api/runs/${enc(id)}/swot`),
  trace: (id: string) => get<TraceEvent[]>(`/api/runs/${enc(id)}/trace`),
  tables: (id: string) => get<string[]>(`/api/runs/${enc(id)}/tables`),
  table: (id: string, key: string, limit = 5000) =>
    get<TablePayload>(`/api/runs/${enc(id)}/tables/${enc(key)}?limit=${limit}`),
  artefact: <T = unknown>(id: string, key: string) => get<T>(`/api/runs/${enc(id)}/json/${enc(key)}`),
  chart: (id: string, name: string, theme: 'light' | 'dark') =>
    get<PlotlyFigure | null>(`/api/runs/${enc(id)}/charts/${enc(name)}?theme=${theme}`),
  evaluation: (id: string) => get<EvaluationState>(`/api/runs/${enc(id)}/evaluation`),
  evaluate: (id: string) => post<EvaluationState>(`/api/runs/${enc(id)}/evaluation`),
  chat: (id: string, question: string, history: ChatMessage[]) =>
    post<ChatAnswer>(`/api/runs/${enc(id)}/chat`, {
      question,
      history: history.map(({ role, content }) => ({ role, content })),
    }),
  askData: (id: string, question: string) => post<DataAnswer>(`/api/runs/${enc(id)}/ask-data`, { question }),
  sentimentStatus: (id: string) =>
    get<{ available: boolean; has_model_card: boolean; real_text_note: string | null }>(`/api/runs/${enc(id)}/sentiment`),
  sentiment: (id: string, text: string) => post<SentimentResult>(`/api/runs/${enc(id)}/sentiment`, { text }),
  dataset: (id: string, name: string, limit = 2000) =>
    get<DatasetPreview>(`/api/runs/${enc(id)}/datasets/${enc(name)}?limit=${limit}`),
  reportUrl: (id: string, kind: 'html' | 'md', download = false) =>
    `/api/runs/${enc(id)}/report.${kind}${download ? '?download=true' : ''}`,

  studies: () => get<StudySnapshot[]>('/api/studies'),
  study: (id: string) => get<StudySnapshot>(`/api/studies/${enc(id)}`),
  startStudy: (body: StudyRequest) => post<StudySnapshot>('/api/studies', body),
  decide: (id: string, decision: Decision) =>
    post<{ ok: boolean; gate: string }>(`/api/studies/${enc(id)}/approval`, decision),
  eventsUrl: (id: string) => `/api/studies/${enc(id)}/events`,
}

export function errorText(e: unknown): string {
  if (e instanceof ApiError) return e.detail
  if (e instanceof Error) return e.message
  return String(e)
}
