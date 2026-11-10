<script setup lang="ts">
// Try the run's deep-learning sentiment model on any review: the label, the class probabilities, where the BiGRU's
// attention went, and the sentiment of each product aspect the text mentions.
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import Message from 'primevue/message'
import { computed, onMounted, ref } from 'vue'
import { api, errorText } from '@/api'
import { useTheme } from '@/lib/theme'
import type { SentimentResult } from '@/types'
import DataGrid from './DataGrid.vue'

const props = defineProps<{ runId: string; note?: string | null }>()
const SAMPLE = 'Teksturnya ringan dan cepat meresap, tapi pump-nya rusak baru seminggu dipake 😭'

const { mode } = useTheme()
const available = ref<boolean | null>(null)
const text = ref(SAMPLE)
const busy = ref(false)
const error = ref('')
const result = ref<SentimentResult | null>(null)

async function analyse() {
  if (!text.value.trim() || busy.value) return
  busy.value = true
  error.value = ''
  try {
    result.value = await api.sentiment(props.runId, text.value)
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  try {
    available.value = (await api.sentimentStatus(props.runId)).available
    if (available.value) await analyse()
  } catch (e) {
    available.value = false
    error.value = errorText(e)
  }
})

const maxAttention = computed(() => Math.max(1e-9, ...(result.value?.attention ?? []).map(([, w]) => w)))
function tokenStyle(w: number) {
  const rgb = mode.value === 'dark' ? '57,135,229' : '42,120,214'
  return { background: `rgba(${rgb},${(0.08 + (0.75 * w) / maxAttention.value).toFixed(2)})` }
}
const probs = computed(() => {
  const p = result.value?.probabilities
  return p
    ? [
        { label: 'P(negative)', value: p.negative },
        { label: 'P(neutral)', value: p.neutral },
        { label: 'P(positive)', value: p.positive },
      ]
    : []
})
</script>

<template>
  <section class="card tester">
    <h2>Try the deep-learning model</h2>
    <p v-if="note" class="caption">{{ note }}</p>
    <Message v-if="available === false && !error" severity="info">
      The trained model is not on disk for this run (retrain by starting a new run).
    </Message>
    <template v-else-if="available">
      <form class="ask" @submit.prevent="analyse">
        <label for="sentiment-text" class="caption">Type a review or post (Indonesian slang and English both work)</label>
        <div class="row">
          <InputText id="sentiment-text" v-model="text" fluid maxlength="2000" />
          <Button type="submit" label="Analyse" icon="pi pi-bolt" :loading="busy" :disabled="!text.trim()" />
        </div>
      </form>
      <template v-if="result">
        <div class="tiles">
          <div class="tile">
            <div class="label">Prediction</div>
            <div class="value" :class="result.label">{{ result.label }}</div>
          </div>
          <div v-for="p in probs" :key="p.label" class="tile">
            <div class="label">{{ p.label }}</div>
            <div class="value">{{ p.value.toFixed(2) }}</div>
          </div>
        </div>
        <div v-if="result.attention.length">
          <h3>Where the BiGRU looked (attention weights)</h3>
          <p class="tokens">
            <span v-for="([t, w], i) in result.attention" :key="i" class="token" :style="tokenStyle(w)" :title="w.toFixed(3)">{{ t }}</span>
          </p>
        </div>
        <div v-if="result.aspects.length">
          <h3>Aspect-based sentiment</h3>
          <DataGrid :columns="['clause', 'aspect', 'score', 'polarity']" :rows="result.aspects" scroll-height="none" />
        </div>
      </template>
    </template>
    <p v-if="error" class="caption err">{{ error }}</p>
  </section>
</template>

<style scoped>
.tester {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.ask .row {
  display: flex;
  gap: 8px;
  margin-top: 4px;
}
.tester h3 {
  margin: 4px 0 6px;
  font-size: 0.92rem;
}
.tokens {
  margin: 0;
  line-height: 2;
}
.token {
  border-radius: 4px;
  padding: 1px 4px;
  margin: 1px;
  display: inline-block;
}
.value.negative {
  color: var(--mm-bad);
}
.value.positive {
  color: var(--mm-good);
}
.err {
  color: var(--mm-bad);
}
@media (max-width: 560px) {
  .ask .row {
    flex-direction: column;
  }
}
</style>
