// Headline tiles. A study that skipped a module has no value for its tile: the tile is left out, never shown as
// "None", "n/a" or "Rp 0" (a pitfall from the Streamlit dry run). Forecast labels use the plan's horizon.
import type { Kpis, Scalar } from '@/types'
import { fmtIdr, fmtInt, pct } from './format'

export interface Tile {
  label: string
  value: string
  note: string
}

const has = (v: Scalar | undefined): boolean => v !== null && v !== undefined && v !== ''
const num = (v: Scalar | undefined): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)
const str = (v: Scalar | undefined, fallback = 'n/a'): string => (has(v) ? String(v) : fallback)

export function overviewTiles(k: Kpis, client: string, horizon: number): Tile[] {
  const elasticity = num(k.elasticity)
  const candidates: [Scalar | undefined, Tile][] = [
    [
      k.market_size_idr_bn,
      {
        label: `Market size ${has(k.market_year) ? k.market_year : ''}`.trim(),
        value: fmtIdr((num(k.market_size_idr_bn) ?? 0) * 1e9),
        note: `CAGR ${pct(k.market_cagr, false)} since 2019`,
      },
    ],
    [
      k.client_share,
      {
        label: `${client} panel share`,
        value: pct(k.client_share, false) + (has(k.client_rank) ? ` (#${k.client_rank})` : ''),
        note: `growth ${pct(k.client_growth)} vs panel ${pct(k.panel_growth)}`,
      },
    ],
    [
      k.forecast_client_growth,
      {
        label: `Forecast growth, next ${horizon} months`,
        value: pct(k.forecast_client_growth),
        note: `market ${pct(k.forecast_market_growth)}`,
      },
    ],
    [
      k.top_threat,
      { label: 'Top competitive threat', value: str(k.top_threat), note: `weakest channel: ${str(k.weakest_channel)}` },
    ],
    [
      k.target_segment,
      {
        label: 'Concept target segment',
        value: str(k.target_segment),
        note: `purchase intent ${pct(k.concept_t2b, false)}`,
      },
    ],
    [
      k.recommended_price_idr,
      {
        label: 'Recommended launch price',
        value: fmtIdr(k.recommended_price_idr),
        note: elasticity !== null ? `elasticity ${elasticity.toFixed(2)}` : '',
      },
    ],
  ]
  return candidates.filter(([v]) => has(v)).map(([, tile]) => tile)
}

// ------------------------------------------------------------------------------------------------ sentiment model
export const MODEL_NAMES: Record<string, string> = {
  bigru: 'BiGRU + attention',
  linear: 'TF-IDF + LogReg',
  ensemble: 'BiGRU + TF-IDF ensemble',
}

export const SENTIMENT_DATA: Record<string, string> = {
  study: "The study's reviews",
  'study+real': "The study's reviews + real reviews",
  real: 'Real reviews only',
}

interface Metrics {
  accuracy: number
  macro_f1: number
}

export interface ModelCard {
  selected: string
  vocab_size?: number
  n_train: number
  n_test: number
  test_metrics: Record<string, Metrics>
  test_metrics_by_source?: Record<string, Record<string, Metrics>>
  study_reviews_check?: Metrics
  training_data?: { mode?: string; model_dir?: string } | null
  transfer_metrics?: Record<string, Metrics>
  transfer_model?: string
  transfer_n?: number
  real_text_note?: string
  data_hash?: string
}

/** The score on the study's own reviews, whichever data the models were trained on (as in finding CON-01). */
export function studyScore(card: ModelCard): [Metrics, string] {
  const sel = card.selected
  const bySource = card.test_metrics_by_source ?? {}
  if (bySource.study) return [bySource.study[sel], 'held-out study reviews']
  if (card.study_reviews_check) return [card.study_reviews_check, 'all study reviews, unseen in training']
  return [card.test_metrics[sel], 'held-out reviews']
}

export function modelTiles(card: ModelCard): Tile[] {
  const [head, basis] = studyScore(card)
  const transfer = card.transfer_metrics?.[card.transfer_model ?? '']
  const mode = card.training_data?.mode ?? 'study'
  return [
    {
      label: 'Selected model (validation)',
      value: MODEL_NAMES[card.selected] ?? card.selected,
      note: `vocabulary ${fmtInt(card.vocab_size ?? 0)} tokens`,
    },
    { label: 'Test macro-F1', value: head.macro_f1.toFixed(3), note: `accuracy ${head.accuracy.toFixed(3)} · ${basis}` },
    {
      label: 'Training data',
      value: `${fmtInt(card.n_train)} reviews`,
      note: `${SENTIMENT_DATA[mode] ?? mode} · test set ${fmtInt(card.n_test)}`,
    },
    {
      label: 'Social transfer macro-F1',
      value: transfer ? transfer.macro_f1.toFixed(3) : 'n/a',
      note: transfer ? `${card.transfer_model} on ${card.transfer_n ?? 0} hand-labelled posts` : '',
    },
  ]
}

// ------------------------------------------------------------------------------------------------ price simulator
export interface PriceOutcome {
  volumeChange: number
  revenue: number
  revenueChange: number
  grossProfitChange: number
}

/** Constant-elasticity demand: a list-price move of `pricePct` percent at gross margin `margin` (0-1). */
export function simulatePrice(elasticity: number, baseRevenue: number, pricePct: number, margin: number): PriceOutcome {
  const m = 1 + pricePct / 100
  const vol = m ** elasticity
  return {
    volumeChange: vol - 1,
    revenue: baseRevenue * m * vol,
    revenueChange: m * vol - 1,
    grossProfitChange: ((m - (1 - margin)) / margin) * vol - 1,
  }
}
