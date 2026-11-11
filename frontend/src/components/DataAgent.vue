<script setup lang="ts">
// Ask the data: the ReAct Data Agent answers from this study's datasets. It thinks, calls one read-only tool, reads
// the observation and repeats until it can answer; the server checks that every number in the answer comes from an
// observation. The reasoning steps stay visible under the answer.
import Button from 'primevue/button'
import InputText from 'primevue/inputtext'
import { computed, ref, watch } from 'vue'
import { api, errorText } from '@/api'
import { DATA_SUGGESTIONS } from '@/lib/chat'
import { renderMarkdown } from '@/lib/markdown'
import type { DataAnswer } from '@/types'

const props = defineProps<{ runId: string; llm: string }>()

const question = ref('')
const asked = ref('')
const result = ref<DataAnswer | null>(null)
const busy = ref(false)
const error = ref('')

watch(
  () => props.runId,
  () => {
    result.value = null
    asked.value = ''
    error.value = ''
  },
)

async function ask(q: string) {
  const text = q.trim()
  if (!text || busy.value) return
  question.value = text
  asked.value = text
  busy.value = true
  error.value = ''
  try {
    result.value = await api.askData(props.runId, text)
  } catch (e) {
    error.value = errorText(e)
    result.value = null
  } finally {
    busy.value = false
  }
}

const toolCalls = computed(() => result.value?.steps.filter((s) => s.kind === 'action').length ?? 0)
const call = (action?: string, args?: Record<string, unknown>) => `${action}(${JSON.stringify(args ?? {})})`
</script>

<template>
  <section class="card data-agent">
    <h3>Ask the data</h3>
    <p class="caption">
      A ReAct agent answers from this study's datasets: it thinks, calls one read-only tool, reads the result and
      repeats until it can answer. Every number in the answer must come from a tool result. Via {{ llm }}.
    </p>

    <div class="suggest" role="group" aria-label="Try asking">
      <button v-for="s in DATA_SUGGESTIONS" :key="s" type="button" class="chip suggestion" :disabled="busy" @click="ask(s)">
        {{ s }}
      </button>
    </div>

    <form class="composer" @submit.prevent="ask(question)">
      <InputText
        v-model="question"
        maxlength="1000"
        placeholder="Which channel had the highest revenue in 2025?"
        aria-label="Your question about the data"
        fluid
      />
      <Button type="submit" label="Ask" icon="pi pi-search" :loading="busy" :disabled="!question.trim()" />
    </form>

    <p v-if="busy" class="caption" aria-live="polite">The agent is reasoning and calling tools ...</p>
    <p v-if="error" class="caption err">{{ error }}</p>

    <div v-if="result && !busy" class="result" aria-live="polite">
      <p class="q">{{ asked }}</p>
      <!-- eslint-disable-next-line vue/no-v-html -- markdown-it escapes raw HTML (html: false) -->
      <div class="md" v-html="renderMarkdown(result.answer)" />
      <p class="caption">{{ result.mode }} · {{ result.verified ? 'verified' : 'not verified' }} · {{ result.seconds }}s</p>
      <details class="steps">
        <summary>Reasoning steps ({{ toolCalls }} tool {{ toolCalls === 1 ? 'call' : 'calls' }})</summary>
        <ol>
          <li v-for="s in result.steps" :key="s.n" :class="s.kind">
            <template v-if="s.kind === 'action'">
              <p><strong>Thought {{ s.n }}.</strong> {{ s.thought }}</p>
              <p class="action">
                Action: <code>{{ call(s.action, s.args) }}</code>
                <span v-if="s.error" class="err"> - an error, which the next step corrects</span>
              </p>
              <pre class="obs">{{ s.observation }}</pre>
            </template>
            <p v-else-if="s.kind === 'check'"><strong>Check {{ s.n }}.</strong> {{ s.observation }}</p>
            <p v-else-if="s.kind === 'answer'"><strong>Thought {{ s.n }}.</strong> {{ s.thought }}</p>
            <p v-else class="caption">{{ s.observation }}</p>
          </li>
        </ol>
      </details>
    </div>
  </section>
</template>

<style scoped>
.data-agent {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.data-agent h3 {
  margin: 0;
}
.suggest {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.suggestion {
  cursor: pointer;
  white-space: normal;
  text-align: left;
  font: inherit;
  font-size: 0.82rem;
}
.suggestion:hover:not(:disabled) {
  border-color: var(--mm-accent);
  color: var(--mm-accent);
}
.composer {
  display: flex;
  gap: 8px;
  align-items: center;
}
.result {
  border-top: 1px solid var(--mm-border);
  padding-top: 10px;
}
.q {
  font-weight: 600;
  margin: 0 0 6px;
}
.md :deep(p) {
  margin: 0 0 8px;
}
.steps {
  font-size: 0.85rem;
}
.steps summary {
  cursor: pointer;
  color: var(--mm-muted);
}
.steps ol {
  margin: 8px 0 0;
  padding-left: 20px;
}
.steps li {
  margin: 0 0 10px;
}
.steps p {
  margin: 0 0 4px;
  overflow-wrap: anywhere;
}
.action code {
  overflow-wrap: anywhere;
  white-space: normal;
}
.obs {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--mm-panel-2);
  border: 1px solid var(--mm-border);
  font-size: 0.78rem;
  line-height: 1.45;
  white-space: pre-wrap;
  overflow-x: auto;
  max-height: 260px;
}
.err {
  color: var(--mm-bad);
}
</style>
