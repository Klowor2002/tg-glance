import { DEMO_CHATS, DEMO_DIGEST } from './demo-data'
import type { ChatDetail, DigestResponse, PairStart, PairStatus } from './types'

// The app talks to exactly ONE origin: our backend (whitelisted in
// app.json). If the backend is unreachable we fall back to the built-in
// demo payload and set `demoMode`, so the flow stays explorable in a
// plain browser. Demo mode never sends anything.
const BASE: string =
  (import.meta as unknown as { env?: Record<string, string> }).env
    ?.VITE_BACKEND_URL ?? 'http://127.0.0.1:8787'

export let demoMode = false

/** HTTP error that keeps its status, so callers can tell "unpaired" (401)
 * apart from "backend unreachable" (network error -> demo fallback). */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/** Reset the demo fallback so the next fetch retries the live backend. */
export function retryLive(): void {
  demoMode = false
}

async function req<T>(path: string, init?: RequestInit, token?: string): Promise<T> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 4000)
  try {
    const res = await fetch(`${BASE}${path}`, {
      ...init,
      signal: ctrl.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(init?.headers ?? {}),
      },
    })
    if (!res.ok) throw new ApiError(res.status, `HTTP ${res.status}`)
    return (await res.json()) as T
  } finally {
    clearTimeout(timer)
  }
}

export async function pairStart(): Promise<PairStart> {
  try {
    return await req<PairStart>('/v1/pair/start', { method: 'POST' })
  } catch {
    demoMode = true
    return { session: 'demo-session', code: '483 920', expiresInSec: 600 }
  }
}

export async function pairStatus(session: string): Promise<PairStatus> {
  if (demoMode) return { paired: false }
  try {
    return await req<PairStatus>(`/v1/pair/status?session=${encodeURIComponent(session)}`)
  } catch {
    demoMode = true
    return { paired: false }
  }
}

/** Demo-mode only: a tap on the pairing screen "completes" pairing. */
export function demoPair(): PairStatus {
  return { paired: true, token: 'demo-token', accountLabel: '@Kingklwr (demo)' }
}

export async function fetchDigest(token: string): Promise<DigestResponse> {
  if (demoMode) return DEMO_DIGEST
  try {
    return await req<DigestResponse>('/v1/digest', undefined, token)
  } catch (e) {
    // 401 means the pairing is dead - the app must re-pair, not silently
    // fall back to demo data and pretend the user is still connected.
    if (e instanceof ApiError && e.status === 401) throw e
    demoMode = true
    return DEMO_DIGEST
  }
}

export async function fetchChat(token: string, id: string): Promise<ChatDetail> {
  if (demoMode) return DEMO_CHATS[id] ?? DEMO_CHATS.dow
  try {
    return await req<ChatDetail>(`/v1/chat/${encodeURIComponent(id)}`, undefined, token)
  } catch (e) {
    if (e instanceof ApiError && (e.status === 401 || e.status === 404)) throw e
    demoMode = true
    return DEMO_CHATS[id] ?? DEMO_CHATS.dow
  }
}

export async function sendReply(
  token: string,
  draftId: string,
): Promise<{ ok: boolean; detail: string }> {
  if (demoMode) return { ok: true, detail: 'demo mode - nothing was sent' }
  try {
    return await req('/v1/reply/send', {
      method: 'POST',
      body: JSON.stringify({ draft_id: draftId }),
    }, token)
  } catch (e) {
    return { ok: false, detail: String(e) }
  }
}

export async function redraft(
  token: string,
  chatId: string,
  style: 'fresh' | 'shorter',
): Promise<{ text: string } | null> {
  if (demoMode) {
    const d = DEMO_CHATS[chatId]?.draft
    if (!d) return null
    return {
      text:
        style === 'shorter'
          ? 'Yes - Friday 07:00 WIB, link is pinned.'
          : d.text,
    }
  }
  try {
    return await req('/v1/reply/redraft', {
      method: 'POST',
      body: JSON.stringify({ chat_id: chatId, style }),
    }, token)
  } catch {
    return null
  }
}
