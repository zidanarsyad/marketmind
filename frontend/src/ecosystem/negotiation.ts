// Negotiation threads rebuilt from a message log, the same way the engine does (marketmind/ecosystem/engine.py).
import { entOf } from './labels'
import type { EcoMessage, NegotiationThread } from './types'

export const NEGOTIATION_TASKS = ['production_contract', 'campaign_terms', 'quality_compensation', 'reroute_options']
const ISSUES = ['unit_price', 'brand_share', 'discount']

/** ``log`` in the order the messages were sent (oldest first). */
export function threadsFrom(log: EcoMessage[]): NegotiationThread[] {
  const threads = new Map<string, NegotiationThread>()
  for (const m of log) {
    if (!NEGOTIATION_TASKS.includes(m.task)) continue
    let t = threads.get(m.conversation_id)
    if (!t) {
      t = { conversation_id: m.conversation_id, task: m.task, week: m.week, parties: [entOf(m.sender), entOf(m.receiver)], offers: [], outcome: 'open' }
      threads.set(m.conversation_id, t)
    }
    const issue = ISSUES.find((k) => k in m.payload)
    if ((m.message_type === 'PROPOSE' || m.message_type === 'COUNTER_PROPOSAL') && issue) {
      t.offers.push({ by: entOf(m.sender), type: m.message_type, value: Number(m.payload[issue]), issue })
    }
    if (m.message_type === 'PROPOSE' && Array.isArray(m.payload.options)) t.options = m.payload.options as Record<string, unknown>[]
    if (m.message_type === 'ACCEPT_PROPOSAL') {
      t.outcome = 'agreed'
      t.agreed = (issue ? m.payload[issue] : m.payload.option) as number | string
      t.accepted_by = entOf(m.sender)
    } else if (m.message_type === 'REJECT_PROPOSAL') {
      t.outcome = 'no agreement'
    }
  }
  return [...threads.values()]
}
