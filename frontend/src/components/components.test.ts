// Component tests: the KPI tiles, the approval form and Ask the analyst, mounted in jsdom.
import { flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { SUGGESTIONS } from '@/lib/chat'
import { overviewTiles } from '@/lib/kpis'
import type { Pending } from '@/types'
import AnalystChat from './AnalystChat.vue'
import ApprovalForm from './ApprovalForm.vue'
import KpiTiles from './KpiTiles.vue'

vi.mock('@/api', () => ({
  api: { chat: vi.fn() },
  errorText: (e: unknown) => String(e),
}))
const { api } = await import('@/api')
const chat = api.chat as unknown as ReturnType<typeof vi.fn>

const global = { plugins: [[PrimeVue, { unstyled: true }]] as [typeof PrimeVue, object][] }

describe('KpiTiles', () => {
  it('renders only the tiles a study produced', () => {
    const tiles = overviewTiles({ market_size_idr_bn: 38300, market_year: 2025, market_cagr: 0.0856, target_segment: null }, 'Kirana Beauty', 12)
    const w = mount(KpiTiles, { props: { tiles } })
    expect(w.findAll('.tile')).toHaveLength(1)
    expect(w.text()).toContain('Rp 38.30 tn')
    expect(w.text()).not.toMatch(/None|null/)
  })
})

describe('ApprovalForm', () => {
  const plan: Pending = {
    gate: 'plan',
    proposal: {
      client: 'Kirana Beauty',
      modules: ['market', 'competition', 'forecast'],
      questions: [{ id: 'Q1', area: 'market', question: 'How large is the market?' }],
      objectives: [],
      horizon_months: 12,
      concept: null,
    },
  }

  it('approves with the unticked modules left out', async () => {
    const w = mount(ApprovalForm, { props: { pending: plan }, global })
    expect(w.text()).toContain('Research plan for Kirana Beauty')
    await w.find('#keep-forecast').trigger('change')
    await w.find('form').trigger('submit')
    expect(w.emitted('decide')).toEqual([[{ gate: 'plan', approved: true, comment: '', drop: ['forecast'] }]])
  })

  it('refuses to approve with nothing left, and can reject instead', async () => {
    const w = mount(ApprovalForm, { props: { pending: plan }, global })
    for (const m of plan.proposal.modules) await w.find(`#keep-${m}`).trigger('change')
    await w.find('form').trigger('submit')
    expect(w.emitted('decide')).toBeUndefined()
    expect(w.text()).toContain('Nothing would be left')
    await w.find('input[type="text"]').setValue('Wrong client')
    const reject = w.findAll('button').find((b) => b.text().includes('Reject the study'))!
    await reject.trigger('click')
    expect(w.emitted('decide')).toEqual([[{ gate: 'plan', approved: false, comment: 'Wrong client', drop: [] }]])
  })

  it('lists the recommendations at the second gate', async () => {
    const recs: Pending = {
      gate: 'recommendations',
      proposal: {
        recommendations: [
          { id: 'R1', title: 'Fix the packaging', priority: 3.87, horizon: 'Quick win', evidence: ['CON-03'] },
          { id: 'R2', title: 'Grow TikTok Shop', priority: 3.61, horizon: 'Core move', evidence: ['CMP-02'] },
        ],
      },
    }
    const w = mount(ApprovalForm, { props: { pending: recs }, global })
    expect(w.text()).toContain('R1. Fix the packaging')
    await w.find('#keep-R2').trigger('change')
    await w.find('form').trigger('submit')
    expect(w.emitted('decide')).toEqual([[{ gate: 'recommendations', approved: true, comment: '', drop: ['R2'] }]])
  })
})

describe('AnalystChat', () => {
  beforeEach(() => {
    localStorage.clear()
    chat.mockReset()
  })

  it('asks a suggested question once and keeps the answer with its sources', async () => {
    chat.mockResolvedValue({
      answer: 'Packaging complaints spiked `[CON-03]`',
      sources: [{ id: 'CON-03', kind: 'finding', title: 'Complaint spike', area: 'consumer', source: 'x', score: 1 }],
      mode: 'retrieval (offline)',
    })
    const w = mount(AnalystChat, { props: { runId: 'run-1', llm: 'offline' }, global })
    const suggestion = w.findAll('button.suggestion').find((b) => b.text() === SUGGESTIONS[0])!
    await suggestion.trigger('click')
    await flushPromises()
    expect(chat).toHaveBeenCalledTimes(1)
    expect(chat).toHaveBeenCalledWith('run-1', SUGGESTIONS[0], [])
    expect(w.findAll('.msg')).toHaveLength(2)
    expect(w.text()).toContain('Sources: CON-03 (finding) · retrieval (offline)')
    expect(JSON.parse(localStorage.getItem('mm-chat-run-1') as string)).toHaveLength(2)
  })

  it('shows the saved conversation after a reload without asking again', async () => {
    localStorage.setItem(
      'mm-chat-run-1',
      JSON.stringify([
        { role: 'user', content: SUGGESTIONS[0] },
        { role: 'assistant', content: 'Packaging.', sources: 'Sources: CON-03 (finding)' },
      ]),
    )
    const w = mount(AnalystChat, { props: { runId: 'run-1', llm: 'offline' }, global })
    await flushPromises()
    expect(w.findAll('.msg')).toHaveLength(2)
    expect(chat).not.toHaveBeenCalled()
  })

  it('renders answers as markdown with raw HTML escaped', async () => {
    chat.mockResolvedValue({ answer: '**Bold** <img src=x onerror=alert(1)>', sources: [], mode: 'retrieval (offline)' })
    const w = mount(AnalystChat, { props: { runId: 'run-2', llm: 'offline' }, global })
    await w.find('textarea').setValue('Anything?')
    await w.find('form.composer').trigger('submit')
    await flushPromises()
    const answer = w.find('.msg.assistant .md')
    expect(answer.find('strong').text()).toBe('Bold')
    expect(answer.find('img').exists()).toBe(false)
  })
})
