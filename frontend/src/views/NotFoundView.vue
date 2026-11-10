<script setup lang="ts">
import { RouterLink } from 'vue-router'
</script>

<template>
  <div class="page">
    <section class="card" style="max-width: 560px; margin: 40px auto">
      <h1>Page not found</h1>
      <p class="muted">There is nothing at this address.</p>
      <RouterLink to="/">Go to the latest run</RouterLink>
    </section>
  </div>
</template>
