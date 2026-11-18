<script setup lang="ts">
// Agent messages as a ledger: week, who wrote to whom, the performative and task, and the payload (open a row to read
// it in full). An enterprise's own log reads from its point of view: in or out, and the other party.
import Button from 'primevue/button'
import { computed, ref, watch } from 'vue'
import { agentOf, entName, entOf, payloadSummary, taskLabel, typeLabel, typeTone, weekLabel } from '../labels'
import type { EcoMessage } from '../types'

const props = withDefaults(defineProps<{ rows: EcoMessage[]; self?: string; pageSize?: number; emptyText?: string }>(), {
  self: '',
  pageSize: 40,
  emptyText: 'No messages.',
})

const page = ref(0)
const pages = computed(() => Math.max(1, Math.ceil(props.rows.length / props.pageSize)))
const shown = computed(() => props.rows.slice(page.value * props.pageSize, (page.value + 1) * props.pageSize))
watch(
  () => props.rows,
  () => {
    if (page.value >= pages.value) page.value = 0
  },
)
const json = (v: unknown) => JSON.stringify(v, null, 2)
</script>

<template>
  <div class="msgs">
    <p v-if="!rows.length" class="empty">{{ emptyText }}</p>
    <details v-for="m in shown" :key="`${m.message_id}-${m.direction ?? ''}`" class="msg">
      <summary>
        <span class="stamp">{{ weekLabel(m.week) }}</span>
        <span class="route">
          <span v-if="self && m.direction" class="dir" :class="m.direction">{{ m.direction === 'in' ? 'in' : 'out' }}</span>
          <span class="party"><i class="dot" :style="{ background: `var(--ent-${entOf(m.sender)}, var(--mm-text-2))` }" />
            <b>{{ entName(entOf(m.sender)) }}</b><small>{{ agentOf(m.sender) }}</small></span>
          <i class="pi pi-arrow-right arrow" aria-label="to" />
          <span class="party"><i class="dot" :style="{ background: `var(--ent-${entOf(m.receiver)}, var(--mm-text-2))` }" />
            <b>{{ entName(entOf(m.receiver)) }}</b><small>{{ agentOf(m.receiver) }}</small></span>
        </span>
        <span class="what">
          <span class="chip" :class="typeTone(m.message_type)">{{ typeLabel(m.message_type) }}</span>
          <span class="task">{{ taskLabel(m.task) }}</span>
        </span>
        <span class="payload">{{ payloadSummary(m.payload) }}</span>
      </summary>
      <div class="body">
        <p class="ids small muted">
          <span class="stamp">{{ m.message_id }}</span>
          conversation <span class="stamp">{{ m.conversation_id }}</span>
          <template v-if="m.in_reply_to"> in reply to <span class="stamp">{{ m.in_reply_to }}</span></template>
          <template v-if="m.reply_required">, a reply is required</template>
        </p>
        <pre>{{ json(m.payload) }}</pre>
      </div>
    </details>
    <div v-if="pages > 1" class="pager">
      <Button icon="pi pi-angle-left" text rounded severity="secondary" aria-label="Previous page" :disabled="page === 0" @click="page--" />
      <span class="small muted">{{ page * pageSize + 1 }}–{{ Math.min(rows.length, (page + 1) * pageSize) }} of {{ rows.length }}</span>
      <Button icon="pi pi-angle-right" text rounded severity="secondary" aria-label="Next page" :disabled="page >= pages - 1" @click="page++" />
    </div>
  </div>
</template>

<style scoped>
.msgs {
  display: flex;
  flex-direction: column;
}
.msg {
  border-top: 1px solid var(--mm-border);
}
.msg:first-of-type {
  border-top: 0;
}
summary {
  display: grid;
  grid-template-columns: 3.2rem minmax(0, 1.5fr) minmax(0, 1fr) minmax(0, 1.4fr);
  align-items: center;
  gap: 4px 14px;
  padding: 9px 4px;
  cursor: pointer;
  list-style: none;
}
summary::-webkit-details-marker {
  display: none;
}
summary:hover {
  background: var(--mm-panel-2);
}
summary .stamp {
  justify-content: center;
}
.route {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 8px;
  min-width: 0;
}
.party {
  display: inline-flex;
  align-items: baseline;
  gap: 5px;
  min-width: 0;
}
.party b {
  font-weight: 620;
  font-size: var(--mm-fs-sm);
  white-space: nowrap;
}
.party small {
  color: var(--mm-muted);
  font-size: var(--mm-fs-xs);
  white-space: nowrap;
}
.dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex: none;
  align-self: center;
}
.arrow {
  font-size: 0.7rem;
  color: var(--mm-muted);
}
.dir {
  font-size: 0.7rem;
  font-weight: 650;
  text-transform: lowercase;
  padding: 0 6px;
  border-radius: 4px;
  background: var(--mm-panel-2);
  color: var(--mm-text-2);
  border: 1px solid var(--mm-border);
}
.dir.in {
  color: var(--mm-accent);
  border-color: transparent;
  background: var(--mm-accent-soft);
}
.what {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 8px;
  min-width: 0;
}
.task {
  font-size: var(--mm-fs-sm);
  font-weight: 560;
}
.payload {
  color: var(--mm-text-2);
  font-size: var(--mm-fs-xs);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.body {
  padding: 2px 4px 12px 3.2rem;
}
.ids {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
  margin: 0 0 6px;
}
pre {
  margin: 0;
  padding: 10px 12px;
  max-height: 320px;
  overflow: auto;
  background: var(--mm-panel-2);
  border: 1px solid var(--mm-border);
  border-radius: var(--mm-radius-sm);
  font-size: 0.78rem;
  line-height: 1.45;
}
.pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  padding-top: 8px;
  border-top: 1px solid var(--mm-border);
}
@media (max-width: 900px) {
  summary {
    grid-template-columns: 3rem minmax(0, 1fr);
  }
  .what,
  .payload {
    grid-column: 2;
  }
  .body {
    padding-left: 4px;
  }
}
</style>
