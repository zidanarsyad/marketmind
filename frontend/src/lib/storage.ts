// Per-browser conveniences kept in localStorage: the analyst chat of each run. Every access is guarded, so the app
// works (without memory) when storage is blocked.
import type { ChatMessage } from '@/types'

const chatKey = (runId: string) => `mm-chat-${runId}`

export function loadChat(runId: string): ChatMessage[] {
  try {
    const raw = localStorage.getItem(chatKey(runId))
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed.filter((m) => m && (m.role === 'user' || m.role === 'assistant')) : []
  } catch {
    return []
  }
}

export function saveChat(runId: string, messages: ChatMessage[]): void {
  try {
    localStorage.setItem(chatKey(runId), JSON.stringify(messages.slice(-60)))
  } catch {
    /* storage full or blocked */
  }
}

export function clearChat(runId: string): void {
  try {
    localStorage.removeItem(chatKey(runId))
  } catch {
    /* ignore */
  }
}
