// Shapes of the MarketMind API responses (api/ in the repository root).

export type Scalar = string | number | boolean | null

export interface LlmStatus {
  available: boolean
  provider: string
  model: string | null
  description: string
}

export interface AppConfig {
  data: { ready: boolean; kind: string; source: string | null; licence: string | null }
  brands: string[]
  default_client: string
  default_brief: string
  sentiment_options: { value: string; label: string }[]
  datasets: { name: string; file: string; description: string; source: string }[]
  llm: LlmStatus
}

export interface RunListItem {
  run_id: string
  started: string | null
  status: string | null
  qa_score: number | null
  qa_passed: boolean | null
  client: string | null
  llm: string | null
  seconds: number | null
  use_llm: boolean
  review: boolean
}

export interface Finding {
  id: string
  agent: string
  area: string
  title: string
  statement: string
  metrics: Record<string, unknown>
  evidence: string[]
  impact: number
  confidence: number
  swot: 'S' | 'W' | 'O' | 'T' | null
  tags: string[]
  priority: number
}

export interface Recommendation {
  id: string
  title: string
  action: string
  rationale: string
  evidence: string[]
  kpi: string
  timeline: string
  owner: string
  effort: string
  value_idr: number | null
  impact: number
  confidence: number
  priority: number
  horizon: string
}

export interface SwotItem {
  id: string
  title: string
  statement: string
  priority: number
}

export type Swot = Record<string, SwotItem[]>

export type Kpis = Record<string, Scalar>

export interface AgentResult {
  agent: string
  status: string
  summary: string | null
  seconds: number
  findings: number
  tool_calls: number
  llm_calls: number
  error: string | null
  attempts?: number
}

export interface Approval {
  gate: string
  time: string
  approved: boolean
  reviewer: string
  comment: string
  drop: string[]
}

export interface RunMeta {
  run_id: string
  status: string
  started: string
  seconds: number
  brief: string
  client: string
  plan: Record<string, unknown> & { horizon_months?: number; modules?: Record<string, boolean> }
  options: Record<string, unknown> & { use_llm?: boolean; approval?: string; data_dir?: string }
  llm: { provider: string; model: string | null; description: string; stats: Record<string, number>; last_error: string | null }
  agents: Record<string, AgentResult>
  agent_roster: { name: string; role: string; goal: string; ml: string }[]
  workflow: { layers: string[][]; edges: [string, string][]; tasks: Record<string, string> }
  qa: { score: number | null; passed: boolean | null; revisions: number; history: Record<string, Scalar>[] }
  approvals: Approval[]
  adaptations: { agent: string; action: string; reason: string; outcome: string }[]
  messages: { sender: string; recipient: string; content: string }[]
}

export interface RunSummary {
  run_id: string
  meta: RunMeta
  kpis: Kpis
  horizon_months: number
  counts: { findings: number; recommendations: number }
  tables: string[]
  has_report: boolean
  has_markdown: boolean
  has_ground_truth: boolean
  evaluated: boolean
}

export interface TablePayload {
  key?: string
  columns: string[]
  data: Scalar[][]
  total: number
  offset: number
  truncated: boolean
}

export interface DatasetPreview extends TablePayload {
  name: string
  file: string
  description: string
  source: string
  available: boolean
}

export interface TraceEvent {
  ts: number
  time: string
  agent: string
  kind: string
  message: string
  data: Record<string, unknown>
}

export interface PlanProposal {
  client: string
  modules: string[]
  questions: { id: string; area: string; question: string }[]
  objectives: string[]
  horizon_months: number
  concept: string | null
}

export interface RecommendationsProposal {
  recommendations: { id: string; title: string; priority: number; horizon: string; evidence: string[] }[]
}

export type Pending =
  | { gate: 'plan'; proposal: PlanProposal }
  | { gate: 'recommendations'; proposal: RecommendationsProposal }

export interface StudySnapshot {
  id: string
  state: 'starting' | 'running' | 'waiting' | 'completed' | 'unverified' | 'failed' | 'rejected' | 'error' | string
  client: string | null
  created: number
  finished: number | null
  options: Record<string, unknown>
  brief: string
  review: boolean
  pending: Pending | null
  result: { status: string; seconds: number; qa_score: number | null; qa_passed: boolean | null } | null
  error: string | null
  saved: boolean
  decisions: (Approval & { gate: string })[]
}

export interface Decision {
  gate: 'plan' | 'recommendations'
  approved: boolean
  comment: string
  drop: string[]
}

export interface StudyRequest {
  brief: string
  client: string | null
  use_llm: boolean
  sentiment_data: string
  retrain: boolean
  parallel: boolean
  review: boolean
}

export interface ChatSource {
  id: string
  kind: string
  title: string
  area: string
  source: string
  score: number
}

export interface ChatAnswer {
  answer: string
  sources: ChatSource[]
  mode: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  sources?: string
}

export interface SentimentResult {
  label: string
  probabilities: Record<'negative' | 'neutral' | 'positive', number>
  attention: [string, number][]
  aspects: { clause: string; aspect: string; score: number; polarity: string }[]
}

export interface EvaluationCheck {
  area: string
  check: string
  expected: string
  found: string
  passed: boolean
  detail: string
}

export interface EvaluationState {
  available: boolean
  evaluated: boolean
  result: { score: number | null; passed: number; total: number; checks: EvaluationCheck[]; note?: string } | null
}

export interface PlotlyFigure {
  data: unknown[]
  layout: Record<string, unknown> & {
    title?: { text?: string } | string
    height?: number
    margin?: Record<string, number>
  }
}
