// Component tests: the KPI tiles, the approval form, Ask the analyst (agentic RAG) and Ask the data (the ReAct agent),
// mounted in jsdom.
import { flushPromises, mount } from '@vue/test-utils'
import PrimeVue from 'primevue/config'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { DATA_SUGGESTIONS, SUGGESTIONS } from '@/lib/chat'
import { overviewTiles } from '@/lib/kpis'
import type { Pending } from '@/types'
import AnalystChat from './AnalystChat.vue'
import ApprovalForm from './ApprovalForm.vue'
import DataAgent from './DataAgent.vue'
import KpiTiles from './KpiTiles.vue'

vi.mock('@/api', () => ({
  api: { chat: vi.fn(), askData: vi.fn() },
  errorText: (e: unknown) => String(e),
}))
const { api } = await import('@/api')
const chat = api.chat as unknown as ReturnType<typeof vi.fn>
const askData = api.askData as unknown as ReturnType<typeof vi.fn>

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
      mode: 'agentic RAG (offline)',
    })
    const w = mount(AnalystChat, { props: { runId: 'run-1', llm: 'offline' }, global })
    const suggestion = w.findAll('button.suggestion').find((b) => b.text() === SUGGESTIONS[0])!
    await suggestion.trigger('click')
    await flushPromises()
    expect(chat).toHaveBeenCalledTimes(1)
    expect(chat).toHaveBeenCalledWith('run-1', SUGGESTIONS[0], [])
    expect(w.findAll('.msg')).toHaveLength(2)
    expect(w.text()).toContain('Sources: CON-03 (finding) · agentic RAG (offline)')
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
    chat.mockResolvedValue({ answer: '**Bold** <img src=x onerror=alert(1)>', sources: [], mode: 'agentic RAG (offline)' })
    const w = mount(AnalystChat, { props: { runId: 'run-2', llm: 'offline' }, global })
    await w.find('textarea').setValue('Anything?')
    await w.find('form.composer').trigger('submit')
    await flushPromises()
    const answer = w.find('.msg.assistant .md')
    expect(answer.find('strong').text()).toBe('Bold')
    expect(answer.find('img').exists()).toBe(false)
  })

  it("keeps the trace of the agent's steps under the answer, also after a reload", async () => {
    chat.mockResolvedValue({
      answer: 'Packaging complaints spiked `[CON-03]`',
      sources: [{ id: 'CON-03', kind: 'finding', title: 'Complaint spike', area: 'consumer', source: 'x', score: 1 }],
      mode: 'agentic RAG (offline)',
      verified: true,
      trace: [
        { step: 'plan', detail: '1 sub-question(s); sources findings, recommendations, reviews' },
        { step: 'grade', detail: '1 of 4 passages relevant (graded by score thresholds)', relevant: ['CON-03'] },
      ],
    })
    const w = mount(AnalystChat, { props: { runId: 'run-3', llm: 'offline' }, global })
    await w.find('textarea').setValue('What is wrong?')
    await w.find('form.composer').trigger('submit')
    await flushPromises()
    expect(w.find('details.trace summary').text()).toBe('How the agent answered (2 steps)')
    expect(w.find('details.trace').text()).toContain('Grade: 1 of 4 passages relevant')
    expect(w.find('details.trace').text()).toContain('kept CON-03')
    const again = mount(AnalystChat, { props: { runId: 'run-3', llm: 'offline' }, global })
    await flushPromises()
    expect(again.find('details.trace summary').text()).toBe('How the agent answered (2 steps)')
  })
})

describe('DataAgent', () => {
  beforeEach(() => askData.mockReset())

  it('asks a suggested question once and shows the answer with its reasoning steps', async () => {
    askData.mockResolvedValue({
      answer: 'Shopee has the highest revenue in 2025: Rp 2.13 trillion [O1].',
      mode: 'ReAct with rule-based policy (offline)',
      verified: true,
      seconds: 0.2,
      observations: 1,
      steps: [
        {
          n: 1,
          kind: 'action',
          thought: 'I aggregate revenue by channel for 2025.',
          action: 'aggregate',
          args: { table: 'sales', by: 'channel' },
          observation: 'sales: sum(revenue_idr) by channel',
          id: 'O1',
          error: false,
        },
        { n: 2, kind: 'answer', thought: 'O1 answers the question.', answer: 'Shopee ...' },
      ],
    })
    const w = mount(DataAgent, { props: { runId: 'run-1', llm: 'offline' }, global })
    const suggestion = w.findAll('button.suggestion').find((b) => b.text() === DATA_SUGGESTIONS[0])!
    await suggestion.trigger('click')
    await flushPromises()
    expect(askData).toHaveBeenCalledTimes(1)
    expect(askData).toHaveBeenCalledWith('run-1', DATA_SUGGESTIONS[0])
    expect(w.find('.result .md').text()).toContain('Shopee has the highest revenue in 2025')
    expect(w.text()).toContain('ReAct with rule-based policy (offline) · verified · 0.2s')
    expect(w.find('details.steps summary').text()).toBe('Reasoning steps (1 tool call)')
    expect(w.find('.action code').text()).toBe('aggregate({"table":"sales","by":"channel"})')
    expect(w.find('pre.obs').text()).toContain('sum(revenue_idr)')
  })

  it('shows the server error instead of an answer', async () => {
    // A plain function, not the vi.fn spy: Vitest reports a rejection that passes through a reset spy as an error of
    // the test even after the component has caught it.
    const real = api.askData
    api.askData = () => Promise.reject(new Error('The run is gone'))
    try {
      const w = mount(DataAgent, { props: { runId: 'run-1', llm: 'offline' }, global })
      await w.find('input').setValue('Which brand sells most?')
      await w.find('form.composer').trigger('submit')
      await flushPromises()
      expect(w.find('.err').text()).toContain('The run is gone')
      expect(w.find('.result').exists()).toBe(false)
    } finally {
      api.askData = real
    }
  })
})
