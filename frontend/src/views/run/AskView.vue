<script setup lang="ts">
import { computed } from 'vue'
import AnalystChat from '@/components/AnalystChat.vue'
import { useAppStore } from '@/stores/app'
import { useRunStore } from '@/stores/run'

const run = useRunStore()
const app = useAppStore()
const id = computed(() => run.runId as string)
</script>

<template>
  <AnalystChat :run-id="id" :llm="app.config?.llm.description ?? 'the configured LLM'" />
</template>
