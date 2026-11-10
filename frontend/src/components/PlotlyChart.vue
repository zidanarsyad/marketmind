<script setup lang="ts">
// One chart from marketmind/reporting/charts.py, drawn by plotly.js from the figure JSON the API sends.
// The figure's title moves into the card's heading (HTML wraps on a phone; a Plotly title does not), the chart loads
// when it scrolls near the screen, and a theme switch fetches the figure in the other palette.
import Skeleton from 'primevue/skeleton'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { api, errorText } from '@/api'
import { useTheme } from '@/lib/theme'
import type { PlotlyFigure } from '@/types'

const props = defineProps<{ runId: string; name: string; height?: number; minWidth?: number }>()

type Plotly = (typeof import('plotly.js-cartesian-dist-min'))['default']
let plotlyLoad: Promise<Plotly> | null = null
function loadPlotly(): Promise<Plotly> {
  plotlyLoad ??= import('plotly.js-cartesian-dist-min').then((m) => ((m as { default?: Plotly }).default ?? m) as Plotly)
  return plotlyLoad
}

const { mode } = useTheme()
const root = ref<HTMLElement>()
const plotEl = ref<HTMLElement>()
const state = ref<'idle' | 'loading' | 'ready' | 'empty' | 'error'>('idle')
const drawn = ref(false)
const error = ref('')
const heading = ref('')
const height = ref(props.height ?? 380)
const label = computed(() => props.name.replace(/_/g, ' '))

let plotly: Plotly | null = null
let seen = false
let token = 0
let io: IntersectionObserver | null = null
let ro: ResizeObserver | null = null
let frame = 0

function layoutFor(fig: PlotlyFigure): Record<string, unknown> {
  const layout: Record<string, unknown> = { ...fig.layout }
  const t = fig.layout.title
  const text = typeof t === 'string' ? t : t?.text
  if (text) {
    heading.value = text.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
    layout.title = { text: '' }
    const margin = { ...(fig.layout.margin ?? {}) }
    if (typeof margin.t === 'number') margin.t = Math.max(14, margin.t - 30)
    layout.margin = margin
  }
  // On a phone the space the charts leave for bar labels outside the bars runs out: give them a wider right margin.
  const narrow = (root.value?.clientWidth ?? 800) < 600
  const outsideLabels = (fig.data as { type?: string; orientation?: string; textposition?: string }[]).some(
    (t) => t.type === 'bar' && t.orientation === 'h' && t.textposition === 'outside',
  )
  if (narrow && outsideLabels) {
    const margin = { ...((layout.margin as Record<string, number>) ?? {}) }
    margin.r = Math.max(margin.r ?? 0, 64)
    layout.margin = margin
  }
  if (props.height) layout.height = props.height
  height.value = (layout.height as number) ?? 380
  delete layout.width
  layout.autosize = true
  return layout
}

async function render() {
  const mine = ++token
  state.value = drawn.value ? 'ready' : 'loading'
  try {
    const [P, fig] = await Promise.all([loadPlotly(), api.chart(props.runId, props.name, mode.value)])
    if (mine !== token) return
    if (!fig) {
      state.value = 'empty'
      return
    }
    plotly = P
    const layout = layoutFor(fig)
    state.value = 'ready'
    await nextTick()
    if (mine !== token || !plotEl.value) return
    const narrow = (root.value?.clientWidth ?? 800) < 560
    await P.react(plotEl.value, fig.data, layout, {
      displaylogo: false,
      responsive: true,
      displayModeBar: narrow ? false : 'hover',
      modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
      toImageButtonOptions: { filename: `marketmind_${props.runId}_${props.name}` },
    })
    drawn.value = true
  } catch (e) {
    if (mine === token) {
      state.value = 'error'
      error.value = errorText(e)
    }
  }
}

onMounted(() => {
  if (typeof IntersectionObserver === 'undefined') {
    seen = true
    void render()
  } else {
    io = new IntersectionObserver(
      (entries) => {
        if (!seen && entries.some((e) => e.isIntersecting)) {
          seen = true
          io?.disconnect()
          void render()
        }
      },
      { rootMargin: '400px 0px' },
    )
    if (root.value) io.observe(root.value)
  }
  if (typeof ResizeObserver !== 'undefined' && root.value) {
    ro = new ResizeObserver(() => {
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        if (plotly && drawn.value && plotEl.value) plotly.Plots.resize(plotEl.value)
      })
    })
    ro.observe(root.value)
  }
})

watch([() => props.runId, () => props.name, mode], () => {
  if (seen) void render()
})

onBeforeUnmount(() => {
  token++
  io?.disconnect()
  ro?.disconnect()
  cancelAnimationFrame(frame)
  if (plotly && plotEl.value) plotly.purge(plotEl.value)
})
</script>

<template>
  <figure ref="root" class="card chart-card" :class="{ empty: state === 'empty' }" :data-chart="name">
    <figcaption v-if="state !== 'empty'" class="chart-title">{{ heading || ' ' }}</figcaption>
    <p v-if="state === 'empty'" class="caption"><i class="pi pi-info-circle" /> {{ label }}: no data in this run</p>
    <p v-else-if="state === 'error'" class="caption error"><i class="pi pi-exclamation-triangle" /> {{ label }}: {{ error }}</p>
    <div v-else class="scroll-x">
      <div class="plot-wrap" :style="{ minWidth: minWidth ? `${minWidth}px` : undefined, height: `${height}px` }">
        <Skeleton v-if="!drawn" class="plot-skeleton" width="100%" :height="`${height}px`" border-radius="8px" />
        <div v-show="state === 'ready'" ref="plotEl" class="plot" :style="{ height: `${height}px` }" />
      </div>
    </div>
  </figure>
</template>

<style scoped>
.chart-card {
  margin: 0;
  padding: 12px 14px 10px;
}
.chart-card.empty {
  padding: 10px 14px;
  border-style: dashed;
  background: transparent;
  box-shadow: none;
}
.chart-title {
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--mm-text);
  margin: 0 2px 4px;
  min-height: 1.2em;
}
.plot-wrap {
  position: relative;
}
.plot-skeleton {
  position: absolute;
  inset: 0;
}
.plot {
  width: 100%;
}
.error {
  color: var(--mm-bad);
}
</style>
