<script setup lang="ts">
import Accordion from 'primevue/accordion'
import AccordionContent from 'primevue/accordioncontent'
import AccordionHeader from 'primevue/accordionheader'
import AccordionPanel from 'primevue/accordionpanel'
import { computed } from 'vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import TableCard from '@/components/TableCard.vue'
import { fmtIdr, range } from '@/lib/format'
import { useRunStore } from '@/stores/run'

const run = useRunStore()
const id = computed(() => run.runId as string)
const swot = computed(() => Object.entries(run.bundle?.swot ?? {}))
const recs = computed(() => run.bundle?.recommendations ?? [])
const quadrant: Record<string, string> = { Strengths: 'S', Weaknesses: 'W', Opportunities: 'O', Threats: 'T' }
</script>

<template>
  <div class="stack">
    <div v-if="swot.length" class="swot">
      <section v-for="[name, items] in swot" :key="name" class="card quad" :class="`q-${quadrant[name] ?? 'x'}`">
        <h3><span class="q-mark" aria-hidden="true" />{{ name }}</h3>
        <article v-for="it in items" :key="it.id" class="finding">
          <span class="stamp" :class="`swot-${quadrant[name] ?? 'x'}`">{{ it.id }}</span>
          <b>{{ it.title }}</b>
          <p>{{ it.statement }}</p>
        </article>
        <p v-if="!items.length" class="empty">None identified.</p>
      </section>
    </div>

    <div class="section-title"><h2>Recommendations</h2><span class="hint">{{ recs.length }} actions, highest priority first</span></div>
    <p v-if="!recs.length" class="empty">No recommendations in this run.</p>
    <Accordion v-else :value="['R1']" multiple class="recs">
      <AccordionPanel v-for="r in recs" :key="r.id" :value="r.id">
        <AccordionHeader>
          <span class="rec-head">
            <span class="stamp">{{ r.id }}</span>
            <span class="rec-title">{{ r.title }}</span>
            <span class="rec-meta">{{ r.horizon }}, priority {{ r.priority.toFixed(2) }}</span>
          </span>
        </AccordionHeader>
        <AccordionContent>
          <dl class="rec">
            <dt>Action</dt>
            <dd>{{ r.action }}</dd>
            <dt>Why</dt>
            <dd>{{ r.rationale }}</dd>
            <dt>Target</dt>
            <dd>{{ r.kpi }}</dd>
            <dt>Owner and timeline</dt>
            <dd>{{ r.owner }}, over {{ range(r.timeline) }}, {{ r.effort.toLowerCase() }} effort</dd>
            <template v-if="r.value_idr">
              <dt>Indicative value</dt>
              <dd>{{ fmtIdr(r.value_idr) }}</dd>
            </template>
            <dt>Evidence</dt>
            <dd class="chips"><span v-for="e in r.evidence" :key="e" class="stamp">{{ e }}</span></dd>
          </dl>
        </AccordionContent>
      </AccordionPanel>
    </Accordion>

    <PlotlyChart :run-id="id" name="opportunities" />
    <TableCard :run-id="id" table-key="strategy.opportunities" title="Sized opportunities and assumptions" />
  </div>
</template>

<style scoped>
.swot {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 420px), 1fr));
  gap: 18px;
}
/* each quadrant keyed by the colour its evidence stamps carry */
.quad h3 {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 6px;
}
.q-mark {
  width: 10px;
  height: 10px;
  border-radius: 3px;
  background: var(--mm-border-strong);
}
.q-S .q-mark {
  background: var(--mm-good);
}
.q-W .q-mark {
  background: var(--mm-bad);
}
.q-O .q-mark {
  background: var(--mm-accent);
}
.q-T .q-mark {
  background: var(--mm-warn);
}
.quad .finding p {
  font-size: var(--mm-fs-sm);
}
.recs {
  border: 1px solid var(--mm-border);
  border-radius: var(--mm-radius);
  overflow: hidden;
  background: var(--mm-panel);
}
.rec-head {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
  text-align: left;
}
.rec-title {
  font-weight: 620;
  color: var(--mm-text);
}
.rec-meta {
  font-size: 0.8rem;
  color: var(--mm-muted);
  font-weight: 400;
}
.rec {
  display: grid;
  grid-template-columns: 9rem 1fr;
  gap: 6px 14px;
  margin: 0;
}
.rec dt {
  font-weight: 600;
  color: var(--mm-text);
}
.rec dd {
  margin: 0;
  color: var(--mm-text-2);
}
@media (max-width: 560px) {
  .rec {
    grid-template-columns: 1fr;
  }
  .rec dd {
    margin-bottom: 6px;
  }
}
</style>
