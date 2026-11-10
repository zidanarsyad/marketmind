// jsdom lacks a few browser APIs the components call; give them harmless stand-ins.
import { vi } from 'vitest'

Element.prototype.scrollIntoView = vi.fn()

globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
}
