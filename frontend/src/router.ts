import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'

/** The twelve views of a saved run, in the order of the Streamlit dashboard's tabs. */
export const RUN_VIEWS = [
  { name: 'overview', label: 'Overview', icon: 'pi pi-home' },
  { name: 'agents', label: 'Agents', icon: 'pi pi-sitemap' },
  { name: 'market', label: 'Market', icon: 'pi pi-chart-bar' },
  { name: 'competition', label: 'Competition', icon: 'pi pi-flag' },
  { name: 'consumers', label: 'Consumers', icon: 'pi pi-users' },
  { name: 'segments', label: 'Segments', icon: 'pi pi-th-large' },
  { name: 'forecast', label: 'Forecast & pricing', icon: 'pi pi-chart-line' },
  { name: 'strategy', label: 'Strategy', icon: 'pi pi-compass' },
  { name: 'report', label: 'Report', icon: 'pi pi-file' },
  { name: 'ask', label: 'Ask the analyst', icon: 'pi pi-comments' },
  { name: 'evaluation', label: 'Evaluation', icon: 'pi pi-check-square' },
  { name: 'data', label: 'Data', icon: 'pi pi-database' },
] as const

const views: Record<string, () => Promise<unknown>> = {
  overview: () => import('./views/run/OverviewView.vue'),
  agents: () => import('./views/run/AgentsView.vue'),
  market: () => import('./views/run/MarketView.vue'),
  competition: () => import('./views/run/CompetitionView.vue'),
  consumers: () => import('./views/run/ConsumersView.vue'),
  segments: () => import('./views/run/SegmentsView.vue'),
  forecast: () => import('./views/run/ForecastView.vue'),
  strategy: () => import('./views/run/StrategyView.vue'),
  report: () => import('./views/run/ReportView.vue'),
  ask: () => import('./views/run/AskView.vue'),
  evaluation: () => import('./views/run/EvaluationView.vue'),
  data: () => import('./views/run/DataView.vue'),
}

const routes: RouteRecordRaw[] = [
  { path: '/', name: 'home', component: () => import('./views/HomeView.vue') },
  { path: '/runs', name: 'runs', component: () => import('./views/RunsView.vue') },
  { path: '/new', name: 'new', component: () => import('./views/NewStudyView.vue') },
  { path: '/studies/:id', name: 'study', component: () => import('./views/StudyView.vue'), props: true },
  {
    path: '/runs/:id',
    component: () => import('./views/RunLayout.vue'),
    props: true,
    children: [
      { path: '', name: 'run', redirect: (to) => ({ name: 'overview', params: to.params }) },
      ...RUN_VIEWS.map((v) => ({ path: v.name, name: v.name, component: views[v.name], meta: { title: v.label } })),
    ],
  },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('./views/NotFoundView.vue') },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, saved) {
    if (saved) return saved
    // switching between a run's views keeps the header in place
    if (to.params.id && to.params.id === from.params.id && to.path.startsWith('/runs/')) return false
    return { top: 0 }
  },
})
