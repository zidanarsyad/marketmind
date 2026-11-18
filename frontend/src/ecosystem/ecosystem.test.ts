// The ecosystem dashboards' helpers: labels and figures, identity colours, negotiation threads from a message log.
import { describe, expect, it } from 'vitest'
import { initials, rgba, scale } from './identity'
import { byChain, idr, kpiLabel, kpiValue, payloadSummary, taskLabel, typeTone } from './labels'
import { threadsFrom } from './negotiation'
import type { EcoMessage } from './types'

describe('labels', () => {
  it('reads KPIs in rupiah, shares and counts', () => {
    expect(kpiValue('profit_idr', 11_830_000_000)).toBe('Rp 11.8 bn')
    expect(kpiValue('revenue_idr', 986_800_000)).toBe('Rp 986.8 M')
    expect(kpiValue('fill_rate', 0.9643)).toBe('96.4%')
    expect(kpiValue('lost_units', 9011)).toBe('9,011')
    expect(kpiValue('source', 'MarketMind study 20261110')).toBe('MarketMind study 20261110')
    expect(kpiValue('profit_idr', null)).toBe('n/a')
    expect(idr(18_450_000)).toBe('Rp 18.5 M')
    expect(kpiLabel('defect_ppm_shipped')).toBe('Defects, ppm')
    expect(kpiLabel('some_new_figure_idr')).toBe('Some new figure')
  })

  it('names tasks and gives performatives a tone', () => {
    expect(taskLabel('reroute_options')).toBe('Flood reroute')
    expect(taskLabel('brand_new_task')).toBe('Brand new task')
    expect(typeTone('ACCEPT_PROPOSAL')).toBe('good')
    expect(typeTone('REJECT_PROPOSAL')).toBe('bad')
    expect(typeTone('COUNTER_PROPOSAL')).toBe('accent')
    expect(typeTone('INFORM')).toBe('')
  })

  it('summarises a payload in one line', () => {
    expect(payloadSummary({ week: 5, units: 10_000, probability: 0.82, extra: 'x' })).toBe('week 5; units 10,000; probability 82.0%; 1 more')
    expect(payloadSummary({})).toBe('')
  })

  it('lists enterprises along the supply chain', () => {
    const keys = byChain([{ key: 'research' }, { key: 'pasarnusa' }, { key: 'kirana' }, { key: 'maklonnusa' }]).map((e) => e.key)
    expect(keys).toEqual(['kirana', 'maklonnusa', 'pasarnusa', 'research'])
  })
})

describe('identity', () => {
  it('makes a seal and a palette from the enterprise colour', () => {
    expect(initials('Kirana Beauty')).toBe('KB')
    expect(initials('MaklonNusa')).toBe('MN')
    expect(initials('KirimCepat Logistics')).toBe('KC')
    const s = scale('#b4235f', '#d6578f')
    expect(s[600]).toBe('#b4235f')
    expect(s[400]).toBe('#d6578f')
    expect(Object.keys(s)).toHaveLength(11)
    expect(rgba('#0b6e5f', 0.5)).toBe('rgba(11, 110, 95, 0.5)')
  })
})

describe('negotiation threads', () => {
  const msg = (id: string, sender: string, receiver: string, type: string, payload: Record<string, unknown>): EcoMessage => ({
    message_id: id,
    conversation_id: 'KIR-0001',
    sender,
    receiver,
    message_type: type,
    task: 'production_contract',
    payload,
    in_reply_to: null,
    week: 0,
  })

  it('rebuilds the offers and the agreement from the messages', () => {
    const log = [
      msg('KIR-0001', 'kirana.procurement', 'maklonnusa.quotation', 'REQUEST_PROPOSAL', { volume_units: 200_000 }),
      msg('MAK-0001', 'maklonnusa.quotation', 'kirana.procurement', 'PROPOSE', { unit_price: 25_000 }),
      msg('KIR-0002', 'kirana.procurement', 'maklonnusa.quotation', 'COUNTER_PROPOSAL', { unit_price: 22_400 }),
      msg('MAK-0002', 'maklonnusa.quotation', 'kirana.procurement', 'PROPOSE', { unit_price: 24_400 }),
      msg('KIR-0003', 'kirana.procurement', 'maklonnusa.quotation', 'ACCEPT_PROPOSAL', { unit_price: 24_400 }),
      { ...msg('KIR-0004', 'kirana.supply_planner', 'maklonnusa.capacity_planner', 'REQUEST', { units: 5000 }), task: 'production_order' },
    ]
    const [t, ...rest] = threadsFrom(log)
    expect(rest).toHaveLength(0)
    expect(t.parties).toEqual(['kirana', 'maklonnusa'])
    expect(t.offers.map((o) => [o.by, o.value])).toEqual([
      ['maklonnusa', 25_000],
      ['kirana', 22_400],
      ['maklonnusa', 24_400],
    ])
    expect(t.outcome).toBe('agreed')
    expect(t.agreed).toBe(24_400)
    expect(t.accepted_by).toBe('kirana')
  })
})
