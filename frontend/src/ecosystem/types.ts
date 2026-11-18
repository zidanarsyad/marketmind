// What the ecosystem servers send (marketmind/ecosystem/server.py and control.py).

export type Mode = 'local' | 'ecosystem'

export interface Role {
  name: string
  description: string
  can_approve: boolean
}

export interface Module {
  module: string
  description: string
}

export interface Governance {
  public: string[]
  shared_with_partners: string[]
  shared_with_control_center: string[]
  private_datasets: string[]
  policies: Record<string, unknown>
  approval_threshold_idr: number | null
}

export interface AgentCard {
  name: string
  title: string
  kind: string
  description: string
  model: string | null
  status: string
  last_action: string
  last_week: number | null
}

export interface EnterpriseNode {
  kind: 'enterprise'
  key: string
  name: string
  industry: string
  description: string
  city: string
  accent: string
  accent_dark: string
  product: { sku: string; name: string; price_idr: number }
  roles: Role[]
  modules: Module[]
  platform: Record<string, string>
  governance: Governance
  url: string
  control_center: string
  peers: Record<string, string>
  directory: EnterpriseRef[]
}

export interface EnterpriseRef {
  key: string
  name: string
  industry: string
  accent: string
  accent_dark: string
  city: string
  url: string
  port: number
}

export interface ScenarioEvent {
  key: string
  title: string
  start: number
  end: number
  target: string
  detail: string
}

export interface Scenario {
  key: string
  title: string
  description: string
  events: ScenarioEvent[]
}

export interface SchemaMappingRow {
  enterprise: string
  local: string
  unit: string
  shared: string
  conversion: string
}

export interface ControlNode {
  kind: 'control'
  name: string
  url: string
  description: string
  enterprises: EnterpriseRef[]
  scenarios: Scenario[]
  modes: Mode[]
  weeks: number
  schema_mapping: SchemaMappingRow[]
  campaigns: { name: string; weeks: number[] }[]
  week_starts: Record<string, string>
}

export type EcoNode = EnterpriseNode | ControlNode

export type Kpis = Record<string, number | string | null>

export interface EnterpriseStatus {
  key: string
  name: string
  industry: string
  city: string
  accent: string
  accent_dark: string
  mode: Mode
  scenario: string
  week: number
  agents: AgentCard[]
  kpis: Kpis
  online?: boolean
  url?: string
  error?: string
}

export interface DatasetInfo {
  name: string
  rows: number
  open_to_role: boolean
  private: boolean
}

export interface DatasetPage {
  name: string
  total: number
  offset: number
  rows: Record<string, unknown>[]
  role: string
}

export interface EcoMessage {
  message_id: string
  conversation_id: string
  sender: string
  receiver: string
  message_type: string
  task: string
  payload: Record<string, unknown>
  reply_required?: boolean
  in_reply_to: string | null
  week: number
  direction?: 'in' | 'out'
}

export interface EnterpriseDecision {
  week: number
  agent: string
  decision: string
  reasoning: string
  inputs: Record<string, unknown>
  outputs: Record<string, unknown>
  messages: string[]
}

export interface OwnNegotiation {
  conversation_id: string
  issue: string
  history: { round: number; by: string; value: number }[]
}

// ------------------------------------------------------------------ the Control Center's runs
export interface PlanWeek {
  week: number
  batches: number | null
  production: number
  factory_stock: number
  express: number
  ship_JKT: number
  ship_SBY: number
  surge_JKT: number
  surge_SBY: number
  sales_JKT: number
  sales_SBY: number
  lost_JKT: number
  lost_SBY: number
  stock_JKT: number
  stock_SBY: number
}

export interface PlanResult {
  status: string
  objective: number
  terms: { cost: number; time: number; risk: number; quality: number }
  weeks: PlanWeek[]
  totals: Record<string, number>
  planned_fill_rate: number
  commitment_shortfall: Record<string, number>
  constraints: { max_batches: Record<string, number> }
}

export interface PlanDiff {
  week: number
  field: string
  before: number
  after: number
}

export interface PlanRevision {
  revision: number
  week: number
  label: string
  reason: string
  rounds: number
  result: PlanResult
  diff: PlanDiff[]
}

export interface ControlDecision {
  week: number
  agent: string
  decision: string
  reasoning: string
  [extra: string]: unknown
}

export interface RunEvent {
  week: number
  kind: 'disruption' | 'recovery' | 'campaign'
  key: string
  title: string
  detail: string
  target: string
  start?: number
  end?: number
}

export interface NegotiationThread {
  conversation_id: string
  task: string
  week: number
  parties: string[]
  offers: { by: string; type: string; value: number; issue: string }[]
  options?: Record<string, unknown>[]
  outcome: 'open' | 'agreed' | 'no agreement'
  agreed?: number | string
  accepted_by?: string
}

export interface WeekRecord {
  week: number
  label: string
  demand: number
  served: number
  lost: number
  fill_rate: number
  messages: number
}

export interface EcosystemKpis {
  demand_units: number
  served_units: number
  lost_units: number
  fill_rate: number
  total_profit_idr: number
  profit_by_enterprise: Record<string, number>
  messages: number
  messages_by_type: Record<string, number>
  negotiations: number
  agreements: number
  plan_revisions: number
  replans: number
  stockout_weeks: number
  defective_returns_idr: number
}

export interface SeasonResult {
  scenario: string
  title: string
  description: string
  mode: Mode
  seed: number
  weeks: number
  ecosystem: EcosystemKpis
  kpis: Record<string, Kpis>
  weekly: WeekRecord[]
  events: RunEvent[]
  plans: PlanRevision[]
  decisions: ControlDecision[]
  negotiations: NegotiationThread[]
}

export interface ComparisonRow {
  kpi: string
  label: string
  local: number
  ecosystem: number
  better: 'higher' | 'lower' | 'info'
  delta: number | null
}

export interface Comparison {
  scenario: string
  title: string
  rows: ComparisonRow[]
  enterprises: { enterprise: string; local_profit_idr: number; ecosystem_profit_idr: number }[]
}

export interface RunRecord {
  id: string
  scenario: string
  title: string
  mode: Mode | 'compare'
  seed: number
  status: 'running' | 'done' | 'failed'
  started: number
  finished?: number
  error?: string
  phase?: Mode
  progress?: { week: number; of: number; note?: string; phase?: Mode }
  results?: Partial<Record<Mode, SeasonResult>>
  comparison?: Comparison | null
}

export interface MessagePage {
  total: number
  rows: EcoMessage[]
  tasks: string[]
}
