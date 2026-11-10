<script setup lang="ts">
// Opens on the newest run that produced a report (not on a study a reviewer stopped); with no runs yet, a welcome.
import Button from 'primevue/button'
import ProgressSpinner from 'primevue/progressspinner'
import { watchEffect } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import BrandMark from '@/components/BrandMark.vue'
import { useAppStore } from '@/stores/app'

const app = useAppStore()
const router = useRouter()

watchEffect(() => {
  if (!app.runsLoaded || !app.runs.length) return
  const target = app.runs.find((r) => r.status !== 'rejected') ?? app.runs[0]
  void router.replace(`/runs/${target.run_id}/overview`)
})
</script>

<template>
  <div class="page">
    <div v-if="!app.runsLoaded" class="center"><ProgressSpinner style="width: 40px; height: 40px" /></div>
    <section v-else-if="app.runsError" class="card welcome">
      <h1>The server is not reachable</h1>
      <p class="muted">{{ app.runsError }}</p>
      <Button label="Try again" icon="pi pi-refresh" @click="app.loadRuns()" />
    </section>
    <section v-else-if="!app.runs.length" class="card welcome">
      <BrandMark :size="56" />
      <h1>Welcome to MarketMind</h1>
      <p>
        Eleven AI agents plan, collect, clean, analyse and report a complete market research study: market size and
        trends, competitors, consumer sentiment with a deep-learning model, segments, a demand forecast, pricing and a
        strategy, checked by a critic agent before the report is released.
      </p>
      <RouterLink v-slot="{ navigate }" to="/new" custom>
        <Button label="Start the first study" icon="pi pi-play" size="large" @click="navigate" />
      </RouterLink>
      <p class="caption">It runs offline without any API key; an LLM key in <code>.env</code> only improves the writing.</p>
    </section>
  </div>
</template>

<style scoped>
.center {
  display: flex;
  justify-content: center;
  padding: 80px 0;
}
.welcome {
  max-width: 680px;
  margin: 40px auto;
  padding: 32px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  align-items: flex-start;
}
.welcome p {
  margin: 0;
  color: var(--mm-text-2);
}
</style>
