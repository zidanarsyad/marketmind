<script setup lang="ts">
// A paused study's approval gate: the research plan (which modules to run) or the recommendations (which to keep
// before the report is written). Approve, possibly leaving items out, or reject the study.
import Button from 'primevue/button'
import Checkbox from 'primevue/checkbox'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import { computed, ref, watch } from 'vue'
import type { Decision, Pending } from '@/types'

const props = defineProps<{ pending: Pending; busy?: boolean; error?: string }>()
const emit = defineEmits<{ decide: [decision: Decision] }>()

const items = computed(() =>
  props.pending.gate === 'plan'
    ? props.pending.proposal.modules.map((m) => ({ id: m, label: m, detail: '' }))
    : props.pending.proposal.recommendations.map((r) => ({
        id: r.id,
        label: `${r.id}. ${r.title}`,
        detail: `${r.horizon} · priority ${r.priority.toFixed(2)} · evidence ${r.evidence.join(', ')}`,
      })),
)

const kept = ref<Record<string, boolean>>({})
const comment = ref('')
const problem = ref('')
watch(
  () => props.pending,
  () => {
    kept.value = Object.fromEntries(items.value.map((i) => [i.id, true]))
    comment.value = ''
    problem.value = ''
  },
  { immediate: true },
)

const dropped = computed(() => items.value.filter((i) => !kept.value[i.id]).map((i) => i.id))

function approve() {
  if (dropped.value.length === items.value.length) {
    problem.value = 'Nothing would be left. Keep at least one item, or reject the study.'
    return
  }
  problem.value = ''
  emit('decide', { gate: props.pending.gate, approved: true, comment: comment.value.trim(), drop: dropped.value })
}

function reject() {
  problem.value = ''
  emit('decide', { gate: props.pending.gate, approved: false, comment: comment.value.trim(), drop: [] })
}
</script>

<template>
  <form class="card approval" @submit.prevent="approve">
    <header>
      <span class="chip warn"><i class="pi pi-pause-circle" style="font-size: 0.75rem" />Waiting for your approval</span>
      <h2 v-if="pending.gate === 'plan'">Research plan for {{ pending.proposal.client }}</h2>
      <h2 v-else>Recommendations, before the executive summary and the report are written</h2>
    </header>

    <template v-if="pending.gate === 'plan'">
      <p class="caption">
        Horizon {{ pending.proposal.horizon_months }} months<template v-if="pending.proposal.concept"> · concept: {{ pending.proposal.concept }}</template>
      </p>
      <ol class="questions">
        <li v-for="q in pending.proposal.questions" :key="q.id">
          <span class="qid">{{ q.id }}</span><span class="area">{{ q.area }}</span>{{ q.question }}
        </li>
      </ol>
      <h3>Modules to run <span class="caption">(untick to leave one out)</span></h3>
    </template>
    <h3 v-else>Recommendations to keep <span class="caption">(untick to drop one)</span></h3>

    <div class="items" :class="pending.gate">
      <label v-for="i in items" :key="i.id" class="item" :class="{ off: !kept[i.id] }">
        <Checkbox v-model="kept[i.id]" binary :input-id="`keep-${i.id}`" />
        <span>
          <strong>{{ i.label }}</strong>
          <small v-if="i.detail">{{ i.detail }}</small>
        </span>
      </label>
    </div>
    <p v-if="pending.gate === 'plan' && dropped.includes('segmentation') && !dropped.includes('pricing') && items.some((i) => i.id === 'pricing')" class="caption">
      Leaving out segmentation also leaves out pricing: the concept price research runs inside the segmentation agent.
    </p>

    <label class="comment">
      <span class="caption">Comment (optional, kept in the run's approval record)</span>
      <InputText v-model="comment" maxlength="1000" fluid />
    </label>

    <Message v-if="problem || error" severity="error">{{ problem || error }}</Message>

    <div class="buttons">
      <Button type="submit" label="Approve" icon="pi pi-check" :loading="busy" />
      <Button type="button" label="Reject the study" icon="pi pi-ban" severity="danger" outlined :disabled="busy" @click="reject" />
    </div>
  </form>
</template>

<style scoped>
.approval {
  display: flex;
  flex-direction: column;
  gap: 12px;
  border-color: var(--mm-warn);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--mm-warn) 50%, transparent);
}
.approval header {
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: flex-start;
}
.approval h3 {
  font-size: 0.95rem;
  margin: 4px 0 0;
}
.questions {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.questions li {
  color: var(--mm-text-2);
  font-size: 0.9rem;
}
.qid {
  font-weight: 700;
  color: var(--mm-text);
  margin-right: 6px;
}
.area {
  font-size: 0.74rem;
  border: 1px solid var(--mm-border-strong);
  border-radius: 999px;
  padding: 0 7px;
  margin-right: 6px;
  color: var(--mm-muted);
}
.items {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 200px), 1fr));
  gap: 8px;
}
.items.recommendations {
  grid-template-columns: 1fr;
}
.item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 8px 10px;
  border: 1px solid var(--mm-border);
  border-radius: 10px;
  cursor: pointer;
  background: var(--mm-panel-2);
}
.item.off {
  opacity: 0.6;
  border-style: dashed;
}
.item strong {
  display: block;
  font-weight: 600;
}
.item small {
  display: block;
  color: var(--mm-muted);
  font-size: 0.78rem;
}
.comment {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.buttons {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
</style>
