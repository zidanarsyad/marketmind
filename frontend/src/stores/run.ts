// The saved run on screen: summary (meta + KPIs), findings, recommendations and SWOT, fetched together and kept
// for the few runs viewed most recently (a saved run never changes).
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { api, errorText } from '@/api'
import type { Finding, Recommendation, RunSummary, Swot } from '@/types'

export interface RunBundle {
  summary: RunSummary
  findings: Finding[]
  recommendations: Recommendation[]
  swot: Swot
}

export const useRunStore = defineStore('run', () => {
  const cache = new Map<string, RunBundle>()
  const runId = ref<string | null>(null)
  const bundle = ref<RunBundle | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)
  const notFound = ref(false)

  async function load(id: string) {
    runId.value = id
    error.value = null
    notFound.value = false
    const hit = cache.get(id)
    if (hit) {
      bundle.value = hit
      return
    }
    bundle.value = null
    loading.value = true
    try {
      const [summary, findings, recommendations, swot] = await Promise.all([
        api.run(id),
        api.findings(id),
        api.recommendations(id),
        api.swot(id),
      ])
      const b = { summary, findings, recommendations, swot }
      cache.set(id, b)
      if (cache.size > 6) cache.delete(cache.keys().next().value as string)
      if (runId.value === id) bundle.value = b
    } catch (e) {
      if (runId.value === id) {
        error.value = errorText(e)
        notFound.value = (e as { status?: number }).status === 404
      }
    } finally {
      if (runId.value === id) loading.value = false
    }
  }

  /** Mark the run as evaluated after the Evaluation view scored it. */
  function markEvaluated(id: string) {
    const b = cache.get(id)
    if (b) b.summary.evaluated = true
  }

  const meta = computed(() => bundle.value?.summary.meta ?? null)
  const kpis = computed(() => bundle.value?.summary.kpis ?? {})
  const client = computed(() => meta.value?.client ?? '')
  const horizon = computed(() => bundle.value?.summary.horizon_months ?? 12)

  return { runId, bundle, loading, error, notFound, meta, kpis, client, horizon, load, markEvaluated }
})
