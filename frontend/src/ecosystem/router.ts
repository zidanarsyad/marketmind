import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import type { EcoNode } from './types'

export interface NavItem {
  name: string
  path: string
  label: string
  icon: string
}

export const ENTERPRISE_NAV: NavItem[] = [
  { name: 'overview', path: '/', label: 'Overview', icon: 'pi pi-home' },
  { name: 'data', path: '/data', label: 'Data explorer', icon: 'pi pi-database' },
  { name: 'messages', path: '/messages', label: 'Messages', icon: 'pi pi-comments' },
  { name: 'negotiations', path: '/negotiations', label: 'Negotiations', icon: 'pi pi-arrow-right-arrow-left' },
  { name: 'decisions', path: '/decisions', label: 'Decisions', icon: 'pi pi-check-square' },
]

export const CONTROL_NAV: NavItem[] = [
  { name: 'overview', path: '/', label: 'Overview', icon: 'pi pi-th-large' },
  { name: 'plans', path: '/plans', label: 'Plans', icon: 'pi pi-calendar' },
  { name: 'messages', path: '/messages', label: 'Agent messages', icon: 'pi pi-comments' },
  { name: 'negotiations', path: '/negotiations', label: 'Negotiations', icon: 'pi pi-arrow-right-arrow-left' },
  { name: 'decisions', path: '/decisions', label: 'Decisions and events', icon: 'pi pi-bolt' },
]

const enterpriseViews: Record<string, () => Promise<unknown>> = {
  overview: () => import('./views/EnterpriseOverview.vue'),
  data: () => import('./views/EnterpriseData.vue'),
  messages: () => import('./views/EnterpriseMessages.vue'),
  negotiations: () => import('./views/EnterpriseNegotiations.vue'),
  decisions: () => import('./views/EnterpriseDecisions.vue'),
}

const controlViews: Record<string, () => Promise<unknown>> = {
  overview: () => import('./views/ControlOverview.vue'),
  plans: () => import('./views/ControlPlans.vue'),
  messages: () => import('./views/ControlMessages.vue'),
  negotiations: () => import('./views/ControlNegotiations.vue'),
  decisions: () => import('./views/ControlDecisions.vue'),
}

export function createEcoRouter(node: EcoNode) {
  const [nav, views] = node.kind === 'enterprise' ? [ENTERPRISE_NAV, enterpriseViews] : [CONTROL_NAV, controlViews]
  const routes: RouteRecordRaw[] = nav.map((n) => ({ path: n.path, name: n.name, component: views[n.name], meta: { title: n.label } }))
  routes.push({ path: '/:pathMatch(.*)*', redirect: '/' })
  return createRouter({ history: createWebHistory(), routes, scrollBehavior: (_to, _from, saved) => saved ?? { top: 0 } })
}
