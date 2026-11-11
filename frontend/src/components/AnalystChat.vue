<script setup lang="ts">
// Ask the analyst: the agentic-RAG Analyst Chat. It plans the question, searches the run's findings, recommendations
// and report, the method notes and the customer reviews, grades what it finds, rewrites the query when too little
// fits, and checks every citation and number in its answer; each answer keeps the trace of those steps.
// A question is sent once, when you ask it. The conversation is kept in this browser, so reloading the page shows it
// again without asking the LLM again (in the Streamlit dashboard a reload repeated the last question).
import Button from 'primevue/button'
import Textarea from 'primevue/textarea'
import { nextTick, ref, watch } from 'vue'
import { api, errorText } from '@/api'
import { SUGGESTIONS } from '@/lib/chat'
import { renderMarkdown } from '@/lib/markdown'
import { clearChat, loadChat, saveChat } from '@/lib/storage'
import type { ChatMessage } from '@/types'

const props = defineProps<{ runId: string; llm: string }>()

const history = ref<ChatMessage[]>(loadChat(props.runId))
const draft = ref('')
const busy = ref(false)
const error = ref('')
const list = ref<HTMLElement>()

watch(
  () => props.runId,
  (id) => {
    history.value = loadChat(id)
    error.value = ''
  },
)

async function scrollDown() {
  await nextTick()
  list.value?.lastElementChild?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
}

async function ask(question: string) {
  const q = question.trim()
  if (!q || busy.value) return
  const runId = props.runId
  const before = history.value.slice()
  history.value = [...before, { role: 'user', content: q }]
  saveChat(runId, history.value)
  draft.value = ''
  busy.value = true
  error.value = ''
  void scrollDown()
  try {
    const out = await api.chat(runId, q, before)
    const sources = out.sources.length
      ? `Sources: ${out.sources.map((s) => `${s.id} (${s.kind})`).join(', ')} · ${out.mode}`
      : ''
    const next: ChatMessage[] = [
      ...before,
      { role: 'user', content: q },
      { role: 'assistant', content: out.answer, sources, trace: out.trace ?? [] },
    ]
    saveChat(runId, next) // kept with its run, even if you have moved on to another run meanwhile
    if (runId === props.runId) history.value = next
  } catch (e) {
    error.value = errorText(e)
  } finally {
    busy.value = false
    void scrollDown()
  }
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    void ask(draft.value)
  }
}

function reset() {
  clearChat(props.runId)
  history.value = []
  error.value = ''
}

const stepName = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)
</script>

<template>
  <section class="card chat">
    <header class="chat-head">
      <div>
        <h2>Ask the analyst</h2>
        <p class="caption">
          Agentic RAG: the agent plans the question, searches this run's findings, recommendations and report, the
          method notes and the customer reviews, grades what it finds, rewrites the query when too little fits, and
          checks every citation and number in its answer. Via {{ llm }}.
        </p>
      </div>
      <Button v-if="history.length" label="Clear" icon="pi pi-trash" size="small" severity="secondary" text @click="reset" />
    </header>

    <div class="suggest" role="group" aria-label="Try asking">
      <button v-for="s in SUGGESTIONS" :key="s" type="button" class="chip suggestion" :disabled="busy" @click="ask(s)">
        {{ s }}
      </button>
    </div>

    <ol ref="list" class="messages" aria-live="polite">
      <li v-for="(m, i) in history" :key="i" class="msg" :class="m.role">
        <span class="avatar" aria-hidden="true"><i :class="m.role === 'user' ? 'pi pi-user' : 'pi pi-sparkles'" /></span>
        <div class="bubble">
          <!-- eslint-disable-next-line vue/no-v-html -- markdown-it escapes raw HTML (html: false) -->
          <div v-if="m.role === 'assistant'" class="md" v-html="renderMarkdown(m.content)" />
          <p v-else>{{ m.content }}</p>
          <p v-if="m.sources" class="caption">{{ m.sources }}</p>
          <details v-if="m.trace?.length" class="trace">
            <summary>How the agent answered ({{ m.trace.length }} steps)</summary>
            <ol>
              <li v-for="(s, j) in m.trace" :key="j">
                <strong>{{ stepName(s.step) }}</strong>: {{ s.detail }}
                <span v-if="s.step === 'grade' && s.relevant?.length" class="kept"> - kept {{ s.relevant.join(', ') }}</span>
              </li>
            </ol>
          </details>
        </div>
      </li>
      <li v-if="busy" class="msg assistant">
        <span class="avatar" aria-hidden="true"><i class="pi pi-sparkles" /></span>
        <div class="bubble typing" aria-label="The analyst is answering"><span /><span /><span /></div>
      </li>
    </ol>
    <p v-if="error" class="caption err">{{ error }}</p>

    <form class="composer" @submit.prevent="ask(draft)">
      <Textarea
        v-model="draft"
        auto-resize
        rows="1"
        maxlength="1000"
        placeholder="Ask the analyst about this study"
        aria-label="Your question"
        fluid
        @keydown="onKey"
      />
      <Button type="submit" icon="pi pi-send" aria-label="Ask" :loading="busy" :disabled="!draft.trim()" />
    </form>
  </section>
</template>

<style scoped>
.chat {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-width: 980px;
}
.chat-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
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
.messages {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.msg {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}
.msg.user {
  flex-direction: row-reverse;
}
.avatar {
  flex: none;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--mm-panel-2);
  border: 1px solid var(--mm-border);
  color: var(--mm-muted);
  font-size: 0.8rem;
}
.msg.assistant .avatar {
  background: var(--mm-accent-soft);
  color: var(--mm-accent);
  border-color: transparent;
}
.bubble {
  min-width: 0;
  max-width: min(760px, 100%);
  padding: 10px 14px;
  border-radius: 14px;
  background: var(--mm-panel-2);
  border: 1px solid var(--mm-border);
}
.msg.user .bubble {
  background: var(--mm-accent-soft);
  border-color: transparent;
}
.bubble p {
  margin: 0;
}
.bubble .caption {
  margin-top: 6px;
}
.md :deep(p) {
  margin: 0 0 8px;
}
.md :deep(p:last-child),
.md :deep(ul:last-child) {
  margin-bottom: 0;
}
.md :deep(ul) {
  padding-left: 20px;
  margin: 4px 0 8px;
}
.md :deep(li) {
  margin: 4px 0;
}
.typing {
  display: inline-flex;
  gap: 4px;
  padding: 14px;
}
.typing span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--mm-muted);
  animation: blink 1.2s infinite ease-in-out;
}
.typing span:nth-child(2) {
  animation-delay: 0.2s;
}
.typing span:nth-child(3) {
  animation-delay: 0.4s;
}
@keyframes blink {
  50% {
    opacity: 0.25;
  }
}
.composer {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}
.err {
  color: var(--mm-bad);
}
.trace {
  margin-top: 8px;
  font-size: 0.82rem;
  color: var(--mm-muted);
}
.trace summary {
  cursor: pointer;
}
.trace ol {
  margin: 6px 0 0;
  padding-left: 20px;
}
.trace li {
  margin: 3px 0;
  overflow-wrap: anywhere;
}
</style>
