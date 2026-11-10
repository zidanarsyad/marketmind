<script setup lang="ts">
import { computed } from 'vue'

// A run's outcome at a glance: its QA score when the Critic checked it, else how it ended.
const props = defineProps<{ status: string | null; qa: number | null; compact?: boolean }>()

const view = computed(() => {
  const s = props.status ?? 'unknown'
  if (s === 'rejected') return { cls: 'bad', icon: 'pi pi-ban', text: props.compact ? 'Stopped' : 'Stopped by the reviewer' }
  if (s === 'failed') return { cls: 'bad', icon: 'pi pi-times-circle', text: 'Failed' }
  if (s === 'unverified') return { cls: 'warn', icon: 'pi pi-exclamation-triangle', text: props.compact ? 'Unverified' : 'QA not run' }
  if (props.qa !== null && props.qa !== undefined) {
    const q = Math.round(props.qa)
    return { cls: q >= 80 ? 'good' : 'warn', icon: 'pi pi-verified', text: props.compact ? `QA ${q}` : `QA ${q}/100` }
  }
  return { cls: '', icon: 'pi pi-circle', text: s }
})
</script>

<template>
  <span class="chip" :class="view.cls" :title="status ?? ''">
    <i :class="view.icon" style="font-size: 0.72rem" />{{ view.text }}
  </span>
</template>
