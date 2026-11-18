// Words and numbers for the ecosystem views: task and KPI labels, message tones, payload summaries, week labels.
import { fmtIdr, fmtInt } from '@/lib/format'

export const ENTERPRISE_NAMES: Record<string, string> = {
  kirana: 'Kirana Beauty',
  maklonnusa: 'MaklonNusa',
  kemasprima: 'KemasPrima',
  kirimcepat: 'KirimCepat',
  pasarnusa: 'PasarNusa',
  research: 'MarketMind Research',
  control: 'Control Center',
}

export const entName = (key: string) => ENTERPRISE_NAMES[key] ?? key

export const SCENARIO_TITLES: Record<string, string> = {
  normal: 'Normal operations',
  packaging_defect: 'Packaging defect spike',
  warehouse_flood: 'Jakarta flood',
  demand_surge: '12.12 traffic surge',
  line_breakdown: 'Filling line breakdown',
  stress: 'Every disruption',
}

/** The supply chain from brand to market, the order the views list enterprises in. */
export const DISPLAY_ORDER = ['kirana', 'maklonnusa', 'kemasprima', 'kirimcepat', 'pasarnusa', 'research']
export const byChain = <T extends { key: string }>(xs: T[]) =>
  [...xs].sort((a, b) => DISPLAY_ORDER.indexOf(a.key) - DISPLAY_ORDER.indexOf(b.key))
export const entOf = (address: string) => address.split('.')[0]
export const agentOf = (address: string) => address.split('.').slice(1).join('.').replace(/_/g, ' ')

const TASKS: Record<string, string> = {
  production_contract: 'Production contract',
  campaign_terms: 'Campaign terms',
  quality_compensation: 'Quality compensation',
  reroute_options: 'Flood reroute',
  plan: 'Ecosystem plan',
  shared_view: 'Shared view',
  market_intelligence: 'Market intelligence',
  production_order: 'Production order',
  packaging_order: 'Packaging order',
  packaging_delivery: 'Packaging delivery',
  shipment_booking: 'Shipment booking',
  customer_orders: 'Customer orders',
  fulfil_orders: 'Fulfil orders',
  goods_ready: 'Goods ready',
  defect_risk: 'Defect risk',
  defect_claim: 'Defect claim',
  flood_risk: 'Flood risk',
  capacity_risk: 'Capacity risk',
  capacity_change: 'Capacity change',
  forecast_revision: 'Forecast revision',
  demand_signal: 'Demand signal',
  environment_change: 'Environment change',
  campaign_announcement: 'Campaign announcement',
  join_campaign: 'Join campaign',
  price_list: 'Price list',
  sla_report: 'SLA report',
  express_used: 'Express used',
}

export function taskLabel(task: string): string {
  const t = TASKS[task] ?? task.replace(/_/g, ' ')
  return t.charAt(0).toUpperCase() + t.slice(1)
}

/** The chip tone of a performative: offers in the accent, agreement good, refusal bad, the rest plain. */
export function typeTone(type: string): string {
  if (['PROPOSE', 'COUNTER_PROPOSAL', 'REQUEST_PROPOSAL'].includes(type)) return 'accent'
  if (['ACCEPT_PROPOSAL', 'AGREE', 'CONFIRM'].includes(type)) return 'good'
  if (['REJECT_PROPOSAL', 'REFUSE', 'FAILURE'].includes(type)) return 'bad'
  return ''
}

export const typeLabel = (type: string) => type.replace(/_/g, ' ').toLowerCase()

// ------------------------------------------------------------------ KPIs
const KPI_LABELS: Record<string, string> = {
  demand_units: 'Orders received',
  served_units: 'Orders served',
  lost_units: 'Orders lost',
  fill_rate: 'Fill rate',
  stockout_weeks: 'Stock-out weeks',
  revenue_idr: 'Revenue',
  cogs_idr: 'Cost of goods',
  logistics_idr: 'Logistics',
  marketplace_fees_idr: 'Marketplace fees',
  returns_idr: 'Defective returns',
  holding_idr: 'Holding cost',
  research_fee_idr: 'Research fee',
  unit_price_idr: 'Unit price',
  ending_stock_units: 'Ending stock',
  profit_idr: 'Profit',
  units_produced: 'Units filled',
  shortfall_units: 'Shortfall',
  utilization: 'Line utilisation',
  costs_idr: 'Costs',
  sets_scrapped: 'Sets scrapped at QC',
  defects_passed_on: 'Defects passed on',
  sets_delivered: 'Sets delivered',
  defects_shipped: 'Defective sets shipped',
  defect_ppm_shipped: 'Defects, ppm',
  defects_caught_by_inspection: 'Caught by inspection',
  discount: 'Quality discount',
  units_moved: 'Units moved',
  units_delayed: 'Units delayed',
  on_time_rate: 'On time',
  express_units: 'Express units',
  jakarta_lane_utilisation: 'Jakarta lane utilisation',
  gmv_idr: 'GMV',
  units_sold: 'Units sold',
  fees_idr: 'Fees earned',
  platform_voucher_idr: 'Platform vouchers',
  campaign_fill_rate: 'Campaign fill rate',
  visibility_penalties: 'Visibility penalties',
  requests_served: 'Requests served',
  source: 'Study used',
  total_profit_idr: 'Ecosystem profit',
  defective_returns_idr: 'Defective returns',
  messages: 'Messages exchanged',
  negotiations: 'Negotiations',
  replans: 'Replans',
}

export function kpiLabel(key: string): string {
  if (KPI_LABELS[key]) return KPI_LABELS[key]
  const s = key.replace(/_idr$/, '').replace(/_/g, ' ')
  return s.charAt(0).toUpperCase() + s.slice(1)
}

const isPct = (key: string) => /rate|utili[sz]ation|discount|share/.test(key)

/** Rupiah for a KPI: billions and millions abbreviated, so a figure fits its cell. */
export function idr(v: number): string {
  if (Math.abs(v) >= 1e9) return fmtIdr(v)
  if (Math.abs(v) >= 1e6) return `Rp ${(v / 1e6).toLocaleString('en-US', { maximumFractionDigits: 1 })} M`
  return fmtIdr(v)
}

export function kpiValue(key: string, v: unknown): string {
  if (v === null || v === undefined || v === '') return 'n/a'
  if (typeof v !== 'number') return String(v)
  if (key.endsWith('_idr')) return idr(v)
  if (isPct(key)) return `${(v * 100).toFixed(1)}%`
  return Number.isInteger(v) ? fmtInt(v) : v.toLocaleString('en-US', { maximumFractionDigits: 2 })
}

/** The KPIs an enterprise's overview leads with; the rest sit in the full table below. */
export const HEADLINE_KPIS: Record<string, string[]> = {
  kirana: ['fill_rate', 'lost_units', 'profit_idr', 'revenue_idr', 'unit_price_idr', 'returns_idr'],
  maklonnusa: ['units_produced', 'utilization', 'unit_price_idr', 'shortfall_units', 'defects_passed_on', 'profit_idr'],
  kemasprima: ['sets_delivered', 'defect_ppm_shipped', 'defects_caught_by_inspection', 'discount', 'revenue_idr', 'profit_idr'],
  kirimcepat: ['units_moved', 'on_time_rate', 'jakarta_lane_utilisation', 'express_units', 'revenue_idr', 'profit_idr'],
  pasarnusa: ['gmv_idr', 'units_sold', 'campaign_fill_rate', 'fees_idr', 'visibility_penalties', 'profit_idr'],
  research: ['requests_served', 'revenue_idr', 'profit_idr', 'source'],
}

// ------------------------------------------------------------------ weeks
const START = new Date(2026, 10, 23) // Monday 23 November 2026, week 1

export function weekDate(w: number): string {
  const d = new Date(START)
  d.setDate(d.getDate() + (Math.max(w, 1) - 1) * 7)
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

export const weekLabel = (w: number) => (w <= 0 ? 'Setup' : `W${w}`)

// ------------------------------------------------------------------ payloads
function short(v: unknown): string {
  if (v === null || v === undefined) return '–'
  if (typeof v === 'number') {
    if (Math.abs(v) < 1 && v !== 0 && !Number.isInteger(v)) return `${(v * 100).toFixed(1)}%`
    return fmtInt(v)
  }
  if (typeof v === 'boolean') return v ? 'yes' : 'no'
  if (typeof v === 'string') return v.length > 40 ? `${v.slice(0, 38)}…` : v
  if (Array.isArray(v)) return `${v.length} item${v.length === 1 ? '' : 's'}`
  const keys = Object.keys(v as object)
  return keys.length <= 3
    ? `{${keys.map((k) => `${k}: ${short((v as Record<string, unknown>)[k])}`).join(', ')}}`
    : `${keys.length} fields`
}

/** One line for a payload: its first few fields, numbers formatted, nested values abbreviated. */
export function payloadSummary(payload: Record<string, unknown>, max = 3): string {
  const keys = Object.keys(payload ?? {})
  if (!keys.length) return ''
  const shown = keys.slice(0, max).map((k) => `${k.replace(/_/g, ' ')} ${short(payload[k])}`)
  return shown.join('; ') + (keys.length > max ? `; ${keys.length - max} more` : '')
}
