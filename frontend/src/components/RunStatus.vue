<script setup lang="ts">
import { computed } from 'vue'

// A run's outcome at a glance: its QA score when the Critic checked it, else how it ended. A coloured dot plus words,
// so the state never rests on colour alone.
const props = defineProps<{ status: string | null; qa: number | null; compact?: boolean }>()

const view = computed(() => {
  const s = props.status ?? 'unknown'
  if (s === 'rejected') return { cls: 'bad', text: props.compact ? 'Stopped' : 'Stopped at a gate' }
  if (s === 'failed') return { cls: 'bad', text: 'Failed' }
  if (s === 'unverified') return { cls: 'warn', text: props.compact ? 'Unverified' : 'QA not run' }
  if (props.qa !== null && props.qa !== undefined) {
    const q = Math.round(props.qa)
    return { cls: q >= 80 ? 'good' : 'warn', text: props.compact ? `QA ${q}` : `QA ${q}/100` }
  }
  return { cls: '', text: s }
})
</script>

<template>
  <span class="status" :class="view.cls" :title="status ?? ''"><span class="dot" aria-hidden="true" />{{ view.text }}</span>
</template>

<style scoped>
.status {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--mm-fs-xs);
  font-weight: 560;
  color: var(--mm-text-2);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.dot {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--mm-border-strong);
}
.status.good .dot {
  background: var(--mm-good);
}
.status.warn {
  color: var(--mm-warn);
}
.status.warn .dot {
  background: var(--mm-warn);
}
.status.bad {
  color: var(--mm-bad);
}
.status.bad .dot {
  background: var(--mm-bad);
}
</style>
