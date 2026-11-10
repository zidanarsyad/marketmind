<script setup lang="ts">
// A saved run: its header (client, chips, warnings) and the twelve views as tabs. A study a reviewer stopped shows
// who stopped it and why, and no tabs: it released no report.
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import DataGrid from '@/components/DataGrid.vue'
import { runDate, seconds } from '@/lib/format'
import { RUN_VIEWS } from '@/router'
import { useRunStore } from '@/stores/run'

const props = defineProps<{ id: string }>()
const run = useRunStore()
const route = useRoute()
const tabs = ref<HTMLElement>()

watch(
  () => props.id,
  (id) => void run.load(id),
  { immediate: true },
)

const meta = computed(() => run.meta)
const qa = computed(() => meta.value?.qa)
const rejected = computed(() => meta.value?.status === 'rejected')
const stop = computed(() => meta.value?.approvals?.find((a) => !a.approved))

const chips = computed(() => {
  const m = meta.value
  const b = run.bundle
  if (!m || !b) return []
  const useLlm = (m.options?.use_llm ?? true) as boolean
  const out: { text: string; cls?: string; icon: string }[] = [
    { text: `Run ${m.run_id}`, icon: 'pi pi-hashtag' },
    { text: runDate(m.run_id, m.started), icon: 'pi pi-calendar' },
    { text: seconds(m.seconds), icon: 'pi pi-stopwatch' },
    { text: useLlm ? m.llm?.description || 'LLM' : 'LLM off (deterministic run)', icon: 'pi pi-sparkles', cls: useLlm ? 'accent' : '' },
  ]
  if (qa.value?.score !== null && qa.value?.score !== undefined)
    out.push({
      text: `QA ${qa.value.score}/100 ${qa.value.passed ? 'passed' : 'not passed'}`,
      icon: 'pi pi-verified',
      cls: qa.value.passed ? 'good' : 'warn',
    })
  else if (rejected.value) out.push({ text: 'stopped by the reviewer', icon: 'pi pi-ban', cls: 'bad' })
  else out.push({ text: 'QA not run - unverified', icon: 'pi pi-exclamation-triangle', cls: 'warn' })
  out.push({ text: `${b.summary.counts.findings} findings`, icon: 'pi pi-lightbulb' })
  out.push({ text: `${b.summary.counts.recommendations} recommendations`, icon: 'pi pi-list-check' })
  return out
})

const approvalRows = computed(() =>
  (meta.value?.approvals ?? []).map((a) => ({
    gate: a.gate,
    decision: a.approved ? 'approved' : 'rejected',
    by: a.reviewer,
    time: a.time,
    detail: [a.drop?.length ? `removed ${a.drop.join(', ')}` : '', a.comment].filter(Boolean).join('; ') || '-',
  })),
)

// keep the active tab in view on a phone, where the tab strip scrolls sideways
watch(
  () => route.name,
  async () => {
    await nextTick()
    tabs.value?.querySelector('.router-link-active')?.scrollIntoView({ block: 'nearest', inline: 'center' })
  },
)
</script>

<template>
  <div class="page run-page">
    <div v-if="run.loading && !run.bundle" class="center"><ProgressSpinner style="width: 40px; height: 40px" /></div>

    <section v-else-if="run.error" class="card">
      <h1>{{ run.notFound ? 'Run not found' : 'This run could not be loaded' }}</h1>
      <p class="muted">{{ run.error }}</p>
      <RouterLink to="/runs">See all saved runs</RouterLink>
    </section>

    <template v-else-if="meta && run.bundle">
      <header class="run-head">
        <h1>{{ meta.client || 'Unknown client' }} · Market Research</h1>
        <div class="chips">
          <span v-for="c in chips" :key="c.text" class="chip" :class="c.cls"><i :class="c.icon" style="font-size: 0.72rem" />{{ c.text }}</span>
        </div>
        <Message v-if="meta.status === 'unverified'" severity="warn" class="head-msg">
          The Critic agent did not complete in this run, so the report's numbers, citations and coverage were not checked.
          The Agents view shows the error.
        </Message>
      </header>

      <section v-if="rejected" class="stack">
        <Message severity="error">
          This study was stopped at the {{ stop?.gate ?? '?' }} approval gate by {{ stop?.reviewer ?? '?' }}<template v-if="stop?.comment">: {{ stop.comment }}</template>. No report was released.
        </Message>
        <div class="card">
          <h3>Approval record</h3>
          <DataGrid :columns="['gate', 'decision', 'by', 'time', 'detail']" :rows="approvalRows" scroll-height="none" />
        </div>
      </section>

      <template v-else>
        <nav ref="tabs" class="tabs" aria-label="Views of this run">
          <RouterLink v-for="v in RUN_VIEWS" :key="v.name" :to="{ name: v.name, params: { id } }" class="tab">
            <i :class="v.icon" />{{ v.label }}
          </RouterLink>
        </nav>
        <RouterView v-slot="{ Component }">
          <component :is="Component" :key="`${id}-${String(route.name)}`" />
        </RouterView>
      </template>
    </template>
  </div>
</template>

<style scoped>
.center {
  display: flex;
  justify-content: center;
  padding: 80px 0;
}
.run-head {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 14px;
}
.head-msg {
  margin-top: 4px;
}
.tabs {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  flex-wrap: wrap;
  gap: 0 2px;
  margin: 0 -28px 18px;
  padding: 0 28px;
  background: color-mix(in srgb, var(--mm-bg) 94%, transparent);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--mm-border);
}
.tab {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 11px 12px 10px;
  color: var(--mm-text-2);
  text-decoration: none;
  white-space: nowrap;
  font-size: 0.9rem;
  font-weight: 550;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.tab i {
  font-size: 0.85rem;
  opacity: 0.8;
}
.tab:hover {
  color: var(--mm-text);
  text-decoration: none;
}
.tab.router-link-active {
  color: var(--mm-accent);
  border-bottom-color: var(--mm-accent);
}
@media (max-width: 1023px) {
  /* one row that scrolls sideways, fading at the edges, under the sticky top bar */
  .tabs {
    top: 49px;
    flex-wrap: nowrap;
    overflow-x: auto;
    scrollbar-width: none;
    -webkit-mask-image: linear-gradient(to right, transparent 0, #000 14px, #000 calc(100% - 28px), transparent 100%);
    mask-image: linear-gradient(to right, transparent 0, #000 14px, #000 calc(100% - 28px), transparent 100%);
  }
  .tabs::-webkit-scrollbar {
    display: none;
  }
}
@media (max-width: 720px) {
  .tabs {
    margin: 0 -16px 14px;
    padding: 0 12px;
  }
  .tab {
    padding: 10px 10px 9px;
    font-size: 0.86rem;
  }
}
</style>
