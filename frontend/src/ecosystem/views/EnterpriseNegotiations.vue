<script setup lang="ts">
// The negotiations this enterprise took part in, rebuilt from its own message log.
import { computed, ref, watch } from 'vue'
import { errorText } from '@/api'
import { enterpriseApi } from '../api'
import NegotiationCard from '../components/NegotiationCard.vue'
import { threadsFrom } from '../negotiation'
import { useEnterpriseStore } from '../store'
import type { EcoMessage } from '../types'

const ent = useEnterpriseStore()
const log = ref<EcoMessage[]>([])
const error = ref('')
let timer = 0
async function load() {
  try {
    log.value = (await enterpriseApi.messages(2000)).rows.slice().reverse()
    error.value = ''
  } catch (e) {
    error.value = errorText(e)
  }
}
watch(() => ent.revision, () => {
  window.clearTimeout(timer)
  timer = window.setTimeout(load, 300)
}, { immediate: true })
const threads = computed(() => threadsFrom(log.value))
</script>

<template>
  <div class="page stack">
    <header class="hero">
      <h1>Negotiations</h1>
      <p class="lede">
        The terms {{ ent.node?.name }} negotiated with its partners. Its own limits never leave this server: the other
        side sees only the offers.
      </p>
    </header>
    <p v-if="error" class="caption bad">{{ error }}</p>
    <p v-else-if="!threads.length" class="empty">
      {{ ent.status?.mode === 'local' ? 'With local intelligence nobody negotiates: list prices and standard terms.' : 'No negotiation in the current run.' }}
    </p>
    <NegotiationCard v-for="t in threads" :key="t.conversation_id" :thread="t" />
  </div>
</template>

<style scoped>
.hero {
  max-width: 78ch;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.lede {
  margin: 0;
  color: var(--mm-text-2);
}
.bad {
  color: var(--mm-bad);
}
</style>
