<script setup lang="ts">
// Start a study. It runs on the server, so it carries on if this page is closed; the live view finds it again.
import Button from 'primevue/button'
import Message from 'primevue/message'
import Select from 'primevue/select'
import Textarea from 'primevue/textarea'
import ToggleSwitch from 'primevue/toggleswitch'
import { reactive, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { api, errorText } from '@/api'
import { useAppStore } from '@/stores/app'
import type { StudyRequest } from '@/types'

const app = useAppStore()
const router = useRouter()

const form = reactive<StudyRequest>({
  brief: '',
  client: null,
  use_llm: false,
  sentiment_data: 'study',
  retrain: false,
  parallel: true,
  review: false,
})
const busy = ref(false)
const error = ref('')
const generating = ref(false)

watch(
  () => app.config,
  (c) => {
    if (!c || form.brief) return
    form.brief = c.default_brief
    form.client = c.brands.includes(c.default_client) ? c.default_client : (c.brands[0] ?? null)
    form.use_llm = c.llm.available
  },
  { immediate: true },
)

async function start() {
  busy.value = true
  error.value = ''
  try {
    const study = await api.startStudy({ ...form, brief: form.brief.trim() })
    app.upsertStudy(study)
    app.watchStudies()
    await router.push(`/studies/${study.id}`)
  } catch (e) {
    error.value = errorText(e)
    void app.loadStudies()
  } finally {
    busy.value = false
  }
}

async function generate() {
  generating.value = true
  error.value = ''
  try {
    await api.generateData()
    form.brief = ''
    await app.loadConfig()
  } catch (e) {
    error.value = errorText(e)
  } finally {
    generating.value = false
  }
}
</script>

<template>
  <div class="page">
    <form class="card study-form" @submit.prevent="start">
      <header>
        <h1>New research study</h1>
        <p class="caption">
          Eleven agents plan, collect, clean, analyse and report. A study takes a few minutes; the first one trains the
          sentiment model, which takes longer.
        </p>
      </header>

      <Message v-if="app.activeStudy" severity="info">
        A study is already running.
        <RouterLink :to="`/studies/${app.activeStudy.id}`">Open it</RouterLink>, or wait until it has finished.
      </Message>

      <template v-if="app.config && !app.config.data.ready">
        <Message severity="warn">Datasets not found in the data folder.</Message>
        <Button label="Generate datasets" icon="pi pi-database" :loading="generating" @click="generate" />
      </template>

      <label class="field">
        <span class="label">Research brief</span>
        <Textarea v-model="form.brief" rows="7" auto-resize maxlength="4000" fluid />
      </label>

      <label class="field">
        <span class="label">Client brand</span>
        <Select v-model="form.client" :options="app.config?.brands ?? []" placeholder="Brand from the brief" show-clear fluid />
        <span class="help">Brands in the data, most records first.</span>
      </label>

      <label class="field">
        <span class="label">Sentiment training data</span>
        <Select
          v-model="form.sentiment_data"
          :options="app.config?.sentiment_options ?? [{ value: 'study', label: 'The study\'s reviews (default)' }]"
          option-label="label"
          option-value="value"
          fluid
        />
        <span class="help">
          Which reviews the deep-learning sentiment models learn from. The real Shopee/Tokopedia beauty reviews must be
          downloaded first (docs/DATA_SOURCES.md); a new mix trains once, for a few minutes.
        </span>
      </label>

      <div class="toggles">
        <label class="toggle">
          <ToggleSwitch v-model="form.use_llm" :disabled="!app.config?.llm.available" aria-label="Use LLM reasoning" />
          <span>
            <strong>Use LLM reasoning</strong>
            <small v-if="app.config?.llm.available">{{ app.config.llm.description }}</small>
            <small v-else>Add a free API key to .env (see the README) to enable LLM planning and narrative.</small>
          </span>
        </label>
        <label class="toggle">
          <ToggleSwitch v-model="form.review" aria-label="Review the plan and recommendations myself" />
          <span>
            <strong>Review the plan and recommendations myself</strong>
            <small>
              The study pauses twice for your approval: after planning, and before the report is written. Without
              review, both gates approve automatically and the report says so.
            </small>
          </span>
        </label>
        <label class="toggle">
          <ToggleSwitch v-model="form.parallel" aria-label="Run analysis agents in parallel" />
          <span><strong>Run analysis agents in parallel</strong><small>Faster; turn off to follow one agent at a time.</small></span>
        </label>
        <label class="toggle">
          <ToggleSwitch v-model="form.retrain" aria-label="Retrain the deep-learning model" />
          <span><strong>Retrain the deep-learning model</strong><small>Otherwise a model trained on the same data is reused.</small></span>
        </label>
      </div>

      <Message v-if="error" severity="error">{{ error }}</Message>

      <div class="actions">
        <Button
          type="submit"
          label="Run study"
          icon="pi pi-play"
          size="large"
          :loading="busy"
          :disabled="!app.config?.data.ready || !!app.activeStudy || !form.brief.trim()"
        />
      </div>
    </form>
  </div>
</template>

<style scoped>
.study-form {
  max-width: 820px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 24px;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.label {
  font-weight: 600;
  font-size: 0.92rem;
}
.help {
  font-size: 0.8rem;
  color: var(--mm-muted);
}
.toggles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(100%, 320px), 1fr));
  gap: 14px 24px;
}
.toggle {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  cursor: pointer;
}
.toggle :deep(.p-toggleswitch) {
  flex: none;
  margin-top: 1px;
}
.toggle strong {
  display: block;
  font-size: 0.92rem;
  font-weight: 600;
}
.toggle small {
  display: block;
  font-size: 0.8rem;
  color: var(--mm-muted);
  overflow-wrap: anywhere;
}
.actions {
  display: flex;
  justify-content: flex-start;
}
@media (max-width: 720px) {
  .study-form {
    padding: 16px;
  }
  .actions :deep(.p-button) {
    width: 100%;
  }
}
</style>
