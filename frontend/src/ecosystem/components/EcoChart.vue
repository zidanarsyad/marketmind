<script setup lang="ts">
// A chart drawn in the page from data the server sent (the research app's charts come from the server as figures).
// Same Plotly bundle, loaded on demand; axes, grid and type follow the theme on screen. A parent that colours traces by
// enterprise recomputes them when the theme changes (entColor reads the colour of the theme in use).
import Skeleton from 'primevue/skeleton'
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { errorText } from '@/api'
import { useTheme } from '@/lib/theme'
import { cssVar } from '../identity'

const props = withDefaults(
  defineProps<{ data: Record<string, unknown>[]; layout?: Record<string, unknown>; height?: number; title?: string; minWidth?: number }>(),
  { layout: () => ({}), height: 300, title: '', minWidth: 0 },
)

type Plotly = (typeof import('plotly.js-cartesian-dist-min'))['default']
let plotlyLoad: Promise<Plotly> | null = null
function loadPlotly(): Promise<Plotly> {
  plotlyLoad ??= import('plotly.js-cartesian-dist-min').then((m) => ((m as { default?: Plotly }).default ?? m) as Plotly)
  return plotlyLoad
}

const APP_FONT = "'Archivo Variable', 'Archivo', system-ui, -apple-system, 'Segoe UI', sans-serif"
const { mode } = useTheme()
const root = ref<HTMLElement>()
const plotEl = ref<HTMLElement>()
const drawn = ref(false)
const error = ref('')
let plotly: Plotly | null = null
let token = 0
let ro: ResizeObserver | null = null
let frame = 0

function axis(base: Record<string, unknown> | undefined, grid: string, line: string, muted: string) {
  return { gridcolor: grid, linecolor: line, zeroline: false, tickfont: { color: muted }, automargin: true, ...(base ?? {}) }
}

function layoutFor(): Record<string, unknown> {
  const text = cssVar('--mm-text-2', '#3c504b')
  const muted = cssVar('--mm-muted', '#5e716c')
  const grid = cssVar('--mm-border', '#d6dedb')
  const line = cssVar('--mm-border-strong', '#b4c1bc')
  const panel = cssVar('--mm-panel', '#ffffff')
  const l = props.layout
  return {
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: { family: APP_FONT, size: 12, color: text },
    margin: { l: 10, r: 16, t: 8, b: 10 },
    showlegend: true,
    legend: { orientation: 'h', x: 0, y: 1.12, font: { color: text } },
    hoverlabel: { bgcolor: panel, bordercolor: line, font: { family: APP_FONT, color: cssVar('--mm-text', '#102320') } },
    ...l,
    xaxis: axis(l.xaxis as Record<string, unknown>, grid, line, muted),
    yaxis: axis(l.yaxis as Record<string, unknown>, grid, line, muted),
    height: props.height,
    autosize: true,
  }
}

async function render() {
  const mine = ++token
  try {
    const P = await loadPlotly()
    await nextTick()
    await document.fonts?.ready
    if (mine !== token || !plotEl.value) return
    plotly = P
    const narrow = (root.value?.clientWidth ?? 800) < 560
    await P.react(plotEl.value, props.data, layoutFor(), {
      displaylogo: false,
      responsive: true,
      displayModeBar: narrow ? false : 'hover',
      modeBarButtonsToRemove: ['lasso2d', 'select2d', 'autoScale2d'],
    })
    drawn.value = true
    error.value = ''
  } catch (e) {
    if (mine === token) error.value = errorText(e)
  }
}

onMounted(() => {
  void render()
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
watch([() => props.data, () => props.layout, mode], () => void render(), { deep: true })
onBeforeUnmount(() => {
  token++
  ro?.disconnect()
  cancelAnimationFrame(frame)
  if (plotly && plotEl.value) plotly.purge(plotEl.value)
})
</script>

<template>
  <figure ref="root" class="eco-chart">
    <figcaption v-if="title" class="chart-title">{{ title }}</figcaption>
    <p v-if="error" class="caption bad"><i class="pi pi-exclamation-triangle" /> {{ error }}</p>
    <div class="scroll-x">
      <div class="plot-wrap" :style="{ minWidth: minWidth ? `${minWidth}px` : undefined, height: `${height}px` }">
        <Skeleton v-if="!drawn" class="plot-skeleton" width="100%" :height="`${height}px`" border-radius="8px" />
        <div ref="plotEl" class="plot" :style="{ height: `${height}px` }" />
      </div>
    </div>
    <slot />
  </figure>
</template>

<style scoped>
.eco-chart {
  margin: 0;
  min-width: 0;
}
.chart-title {
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--mm-text);
  margin: 0 2px 4px;
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
.bad {
  color: var(--mm-bad);
}
</style>
