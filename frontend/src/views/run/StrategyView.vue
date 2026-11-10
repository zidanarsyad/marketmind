<script setup lang="ts">
import Accordion from 'primevue/accordion'
import AccordionContent from 'primevue/accordioncontent'
import AccordionHeader from 'primevue/accordionheader'
import AccordionPanel from 'primevue/accordionpanel'
import { computed } from 'vue'
import PlotlyChart from '@/components/PlotlyChart.vue'
import TableCard from '@/components/TableCard.vue'
import { fmtIdr } from '@/lib/format'
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
        <h3>{{ name }}</h3>
        <ul>
          <li v-for="it in items" :key="it.id">
            <strong>{{ it.title }}</strong> — {{ it.statement }} <code>{{ it.id }}</code>
          </li>
        </ul>
        <p v-if="!items.length" class="empty">None identified.</p>
      </section>
    </div>

    <div class="section-title"><h2>Recommendations</h2><span class="hint">{{ recs.length }} actions, highest priority first</span></div>
    <p v-if="!recs.length" class="empty">No recommendations in this run.</p>
    <Accordion v-else :value="['R1']" multiple class="recs">
      <AccordionPanel v-for="r in recs" :key="r.id" :value="r.id">
        <AccordionHeader>
          <span class="rec-head">
            <span class="rid">{{ r.id }}</span>
            <span class="rec-title">{{ r.title }}</span>
            <span class="rec-meta">{{ r.horizon }} · priority {{ r.priority.toFixed(2) }}</span>
          </span>
        </AccordionHeader>
        <AccordionContent>
          <dl class="rec">
            <dt>Action</dt>
            <dd>{{ r.action }}</dd>
            <dt>Why</dt>
            <dd>{{ r.rationale }}</dd>
            <dt>KPI</dt>
            <dd>{{ r.kpi }}</dd>
            <dt>Owner / timeline</dt>
            <dd>{{ r.owner }} · {{ r.timeline }} · {{ r.effort }} effort</dd>
            <template v-if="r.value_idr">
              <dt>Indicative value</dt>
              <dd>{{ fmtIdr(r.value_idr) }}</dd>
            </template>
            <dt>Evidence</dt>
            <dd class="chips"><code v-for="e in r.evidence" :key="e">{{ e }}</code></dd>
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
  gap: 14px;
}
.quad {
  border-top: 3px solid var(--mm-border-strong);
}
.quad.q-S {
  border-top-color: var(--mm-good);
}
.quad.q-W {
  border-top-color: var(--mm-bad);
}
.quad.q-O {
  border-top-color: var(--mm-accent);
}
.quad.q-T {
  border-top-color: var(--mm-warn);
}
.quad ul {
  margin: 0;
  padding-left: 18px;
}
.quad li {
  margin: 6px 0;
  color: var(--mm-text-2);
}
.quad li strong {
  color: var(--mm-text);
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
.rid {
  font-size: 0.72rem;
  font-weight: 700;
  color: var(--mm-accent);
  background: var(--mm-accent-soft);
  border-radius: 6px;
  padding: 1px 6px;
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
