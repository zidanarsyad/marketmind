import { describe, expect, it } from 'vitest'
import { fmtCell, fmtIdr, pct, runDate } from './format'
import { type ModelCard, modelTiles, overviewTiles, simulatePrice, studyScore } from './kpis'

const FULL = {
  market_size_idr_bn: 38300,
  market_year: 2025,
  market_cagr: 0.0856,
  client_share: 0.1389,
  client_rank: 4,
  client_growth: 0.0953,
  panel_growth: 0.1171,
  forecast_client_growth: 0.1721,
  forecast_market_growth: 0.1522,
  top_threat: 'Lumière Lab',
  weakest_channel: 'TikTok Shop',
  target_segment: 'Gentle Glow Seekers',
  concept_t2b: 0.826,
  recommended_price_idr: 79900,
  elasticity: -1.291,
  horizon_months: 12,
}

describe('overview tiles', () => {
  it('shows one tile per headline, formatted', () => {
    const tiles = overviewTiles(FULL, 'Kirana Beauty', 12)
    expect(tiles.map((t) => t.label)).toEqual([
      'Market size 2025',
      'Kirana Beauty panel share',
      'Forecast growth, next 12 months',
      'Top competitive threat',
      'Concept target segment',
      'Recommended launch price',
    ])
    expect(tiles[0]).toEqual({ label: 'Market size 2025', value: 'Rp 38.30 tn', note: 'CAGR 8.6% since 2019' })
    expect(tiles[1].value).toBe('13.9% (#4)')
    expect(tiles[5]).toMatchObject({ value: 'Rp 79,900', note: 'elasticity -1.29' })
  })

  it('leaves out the tiles of modules the study skipped, never showing None or Rp 0', () => {
    const skipped = { ...FULL, target_segment: null, concept_t2b: null, recommended_price_idr: null, elasticity: null }
    delete (skipped as Record<string, unknown>).forecast_client_growth
    const tiles = overviewTiles(skipped, 'Kirana Beauty', 12)
    expect(tiles.map((t) => t.label)).toEqual(['Market size 2025', 'Kirana Beauty panel share', 'Top competitive threat'])
    for (const t of tiles) expect(`${t.value} ${t.note}`).not.toMatch(/None|null|undefined|Rp 0\b/)
  })

  it("labels the forecast with the plan's horizon, not a fixed 12 months", () => {
    const tiles = overviewTiles({ ...FULL, horizon_months: 6 }, 'Kirana Beauty', 6)
    expect(tiles.find((t) => t.label.startsWith('Forecast'))?.label).toBe('Forecast growth, next 6 months')
  })
})

describe('price simulator', () => {
  it('applies constant-elasticity demand', () => {
    const out = simulatePrice(-1.291, 1.04e12, 10, 0.6)
    expect(out.volumeChange).toBeCloseTo(-0.1158, 3)
    expect(out.revenueChange).toBeCloseTo(-0.0274, 3)
    expect(out.grossProfitChange).toBeCloseTo(0.0316, 3)
    expect(simulatePrice(-1.291, 100, 0, 0.6)).toEqual({ volumeChange: 0, revenue: 100, revenueChange: 0, grossProfitChange: 0 })
  })
})

describe('sentiment model card', () => {
  const card: ModelCard = {
    selected: 'ensemble',
    vocab_size: 445,
    n_train: 13668,
    n_test: 2929,
    test_metrics: { ensemble: { accuracy: 0.9, macro_f1: 0.817 } },
    transfer_metrics: { ensemble: { accuracy: 0.92, macro_f1: 0.91 } },
    transfer_model: 'ensemble',
    transfer_n: 400,
    training_data: { mode: 'study' },
  }

  it('scores the study reviews, whichever data the model was trained on', () => {
    expect(studyScore(card)).toEqual([{ accuracy: 0.9, macro_f1: 0.817 }, 'held-out reviews'])
    const mixed = { ...card, test_metrics_by_source: { study: { ensemble: { accuracy: 0.8, macro_f1: 0.7 } } } }
    expect(studyScore(mixed)[1]).toBe('held-out study reviews')
    expect(modelTiles(card).map((t) => t.value)).toEqual(['BiGRU + TF-IDF ensemble', '0.817', '13,668 reviews', '0.910'])
  })
})

describe('formatting', () => {
  it('formats rupiah, percentages, cells and run dates', () => {
    expect(fmtIdr(74_461_000_000)).toBe('Rp 74.5 bn')
    expect(fmtIdr(null)).toBe('n/a')
    expect(pct(0.0953)).toBe('+9.5%')
    expect(pct(-0.025)).toBe('-2.5%')
    expect(pct(0.139, false)).toBe('13.9%')
    expect(fmtCell(1831802908184)).toBe('1,831,802,908,184')
    expect(fmtCell(0.2879779154)).toBe('0.288')
    expect(fmtCell(null)).toBe('')
    expect(runDate('20261110-222212')).toBe('10 Nov 2026, 22:22')
  })
})
