<script setup lang="ts">
// A saved run, set out as a dossier: the client and the study's question, the Critic agent's seal, the run's facts,
// and the twelve views as tabs in four groups. A study stopped at an approval gate (by the reviewer, or by the time
// limit when nobody answered) shows who or what stopped it and why, and no tabs: it released no report.
import Message from 'primevue/message'
import ProgressSpinner from 'primevue/progressspinner'
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import DataGrid from '@/components/DataGrid.vue'
import QaSeal from '@/components/QaSeal.vue'
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

// the study's question: the brief's first sentence, with the whole brief a click away
const brief = computed(() => (meta.value?.brief ?? '').trim())
const lede = computed(() => {
  const flat = brief.value.replace(/\s+/g, ' ')
  const first = /^(.+?[.!?])(\s|$)/.exec(flat)?.[1] ?? flat
  return first.length > 240 ? `${first.slice(0, 237).trimEnd()}…` : first
})
const briefHasMore = computed(() => brief.value.replace(/\s+/g, ' ').length > lede.value.length + 1)
const showBrief = ref(false)
watch(
  () => props.id,
  () => (showBrief.value = false),
)

const facts = computed(() => {
  const m = meta.value
  const b = run.bundle
  if (!m || !b) return []
  const useLlm = (m.options?.use_llm ?? true) as boolean
  const { findings, recommendations } = b.summary.counts
  return [
    { label: 'Run', value: m.run_id },
    { label: 'Started', value: runDate(m.run_id, m.started) },
    { label: 'Took', value: seconds(m.seconds) || 'n/a' },
    { label: 'Language model', value: useLlm ? m.llm?.description || 'On' : 'Off, a deterministic run' },
    {
      label: 'Output',
      value: `${findings} finding${findings === 1 ? '' : 's'}, ${recommendations} recommendation${recommendations === 1 ? '' : 's'}`,
    },
  ]
})

// a rule opens each group of tabs after the first
const tabList = RUN_VIEWS.map((v, i) => ({ ...v, opensGroup: i > 0 && RUN_VIEWS[i - 1].group !== v.group }))

const approvalRows = computed(() =>
  (meta.value?.approvals ?? []).map((a) => ({
    gate: a.gate,
    decision: a.approved ? 'approved' : 'rejected',
    by: a.reviewer,
    time: a.time,
    detail: [a.drop?.length ? `removed ${a.drop.join(', ')}` : '', a.comment].filter(Boolean).join('; ') || '-',
  })),
)

// keep the active tab in view where the tab strip scrolls sideways
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
        <h1>{{ meta.client || 'Unknown client' }}</h1>
        <div v-if="lede" class="lede">
          <p id="run-brief" :class="{ full: showBrief }">{{ showBrief ? brief : lede }}</p>
          <button
            v-if="briefHasMore"
            type="button"
            class="brief-toggle"
            aria-controls="run-brief"
            :aria-expanded="showBrief"
            @click="showBrief = !showBrief"
          >
            {{ showBrief ? 'Show less' : 'Read the full brief' }}
          </button>
        </div>
        <QaSeal class="seal" :status="meta.status" :score="qa?.score" :passed="qa?.passed" :revisions="qa?.revisions" />
        <dl class="facts">
          <div v-for="f in facts" :key="f.label">
            <dt>{{ f.label }}</dt>
            <dd>{{ f.value }}</dd>
          </div>
        </dl>
      </header>
      <Message v-if="meta.status === 'unverified'" severity="warn" class="head-msg">
        The Critic agent did not complete in this run, so the report's numbers, citations and coverage were not checked.
        The Agents view shows the error.
      </Message>

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
          <RouterLink
            v-for="v in tabList"
            :key="v.name"
            :to="{ name: v.name, params: { id } }"
            class="tab"
            :class="{ 'opens-group': v.opensGroup }"
          >
            {{ v.label }}
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

/* ------------------------------------------------------------------ the dossier's cover */
.run-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  grid-template-areas:
    'title seal'
    'lede seal'
    'facts facts';
  column-gap: 32px;
  align-items: start;
  padding-top: 4px;
}
.run-head h1 {
  grid-area: title;
  font-size: clamp(1.75rem, 1.1rem + 1.6vw, 2.5rem);
  font-weight: 740;
  font-stretch: 122%;
  letter-spacing: -0.024em;
  line-height: 1.06;
  overflow-wrap: anywhere;
}
.lede {
  grid-area: lede;
  margin-top: 10px;
  max-width: 66ch;
}
.lede p {
  margin: 0;
  color: var(--mm-text-2);
  font-size: var(--mm-fs-md);
  line-height: 1.5;
}
.lede p.full {
  white-space: pre-line;
}
.brief-toggle {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  margin-top: 2px;
  padding: 0;
  border: 0;
  background: none;
  color: var(--mm-accent);
  font: inherit;
  font-size: var(--mm-fs-sm);
  font-weight: 600;
  cursor: pointer;
}
.brief-toggle:hover {
  text-decoration: underline;
  text-underline-offset: 3px;
}
.seal {
  grid-area: seal;
  align-self: center;
  margin-right: 4px;
}
.facts {
  grid-area: facts;
  display: flex;
  flex-wrap: wrap;
  gap: 10px 36px;
  margin: 20px 0 0;
  padding: 13px 0 14px;
  border-top: 1px solid var(--mm-border);
}
.facts div {
  min-width: 0;
}
.facts dt {
  font-size: var(--mm-fs-xs);
  font-weight: 520;
  color: var(--mm-muted);
}
.facts dd {
  margin: 1px 0 0;
  font-size: var(--mm-fs-sm);
  font-weight: 560;
  color: var(--mm-text);
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}
.head-msg {
  margin-bottom: 14px;
}

/* ------------------------------------------------------------------ tabs: one row, four groups */
.tabs {
  position: sticky;
  top: 0;
  z-index: 5;
  display: flex;
  align-items: stretch;
  margin: 0 -36px 22px;
  padding: 0 30px;
  background: color-mix(in srgb, var(--mm-bg) 94%, transparent);
  backdrop-filter: blur(8px);
  border-top: 1px solid var(--mm-border);
  border-bottom: 1px solid var(--mm-border);
  overflow-x: auto;
  scrollbar-width: none;
  /* when the row is wider than the page it scrolls sideways, fading at the edges */
  -webkit-mask-image: linear-gradient(to right, transparent 0, #000 12px, #000 calc(100% - 24px), transparent 100%);
  mask-image: linear-gradient(to right, transparent 0, #000 12px, #000 calc(100% - 24px), transparent 100%);
}
.tabs::-webkit-scrollbar {
  display: none;
}
.tab {
  position: relative;
  flex: none;
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  padding: 0 10px;
  color: var(--mm-text-2);
  text-decoration: none;
  white-space: nowrap;
  font-size: var(--mm-fs-sm);
  font-weight: 560;
  font-stretch: 97%;
  border-bottom: 2px solid transparent;
  margin-bottom: -1px;
}
.tab.opens-group {
  margin-left: 13px;
}
.tab.opens-group::before {
  content: '';
  position: absolute;
  left: -7px;
  top: 14px;
  bottom: 14px;
  width: 1px;
  background: var(--mm-border-strong);
}
.tab:hover {
  color: var(--mm-text);
  text-decoration: none;
}
.tab.router-link-active {
  color: var(--mm-accent);
  font-weight: 650;
  border-bottom-color: var(--mm-accent);
}
.tab:focus-visible {
  outline-offset: -3px;
  border-radius: 4px;
}

@media (max-width: 1023px) {
  /* under the sticky top bar */
  .tabs {
    top: 49px;
  }
}
@media (max-width: 720px) {
  .run-head {
    grid-template-areas:
      'title seal'
      'lede lede'
      'facts facts';
    column-gap: 16px;
    padding-top: 0;
  }
  .run-head h1 {
    align-self: center;
  }
  .lede {
    margin-top: 12px;
  }
  .lede p {
    font-size: var(--mm-fs-sm);
  }
  .brief-toggle {
    min-height: 44px;
    margin-top: 0;
  }
  .seal {
    margin-right: 0;
  }
  .facts {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px 16px;
    margin-top: 16px;
  }
  .facts div:last-child {
    grid-column: 1 / -1;
  }
  .tabs {
    margin: 0 -16px 16px;
    padding: 0 10px;
  }
  .tab {
    padding: 0 9px;
  }
}
</style>
