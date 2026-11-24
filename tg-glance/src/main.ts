import {
  OsEventTypeList,
  waitForEvenAppBridge,
  type EvenAppBridge,
  type EvenHubEvent,
} from '@evenrealities/even_hub_sdk'
import * as api from './api'
import { BridgeRenderer, WebRenderer, type Screen } from './render'
import type { ChatDetail, ChatSummary } from './types'

// TG Glance — screen state machine.
//   pairing -> home (list) -> digest (text, paginated) -> reply -> sent
// Input is abstracted to actions so the Even bridge events and the web
// preview drive the exact same logic.

type Action =
  | { type: 'click' }
  | { type: 'double' }
  | { type: 'up' }
  | { type: 'down' }
  | { type: 'menu'; id: number }

type Route =
  | { name: 'pairing' }
  | { name: 'home' }
  | { name: 'digest'; chatId: string; page: number }
  | { name: 'reply'; chatId: string }
  | { name: 'sent'; chatId: string; ok: boolean }

// Home list rows. The first rows are status/action rows; chat rows follow.
// Keeping rows separate from `chats` makes tap dispatch unambiguous:
// index 0 is the mention inbox when it exists, never a chat.
type HomeRow =
  | { kind: 'offline' } // backend down - showing demo data, tap retries live
  | { kind: 'stale' } // snapshot older than STALE_AFTER_SEC, tap refreshes
  | { kind: 'mention'; chatId: string } // "N questions waiting for you"
  | { kind: 'chat'; chatId: string }

const STALE_AFTER_SEC = 600 // backend live-cache TTL is 120 s; 10 min is stale
const HOME_REFRESH_MS = 120_000 // re-fetch the digest while sitting on home

const TOKEN_KEY = 'tgglance.token'

class App {
  private route: Route = { name: 'pairing' }
  private token: string | null = null
  private pairSession: string | null = null
  private pairCode = ''
  private pairPoll: ReturnType<typeof setInterval> | null = null
  private pairStartedAt = 0
  private pairExpiresSec = 600
  private chats: ChatSummary[] = []
  private rows: HomeRow[] = []
  private homeEmpty = false
  private homeTimer: ReturnType<typeof setInterval> | null = null
  private detail: ChatDetail | null = null
  private draftText = ''
  private selectedIndex = 0

  private clearHomeTimer(): void {
    if (this.homeTimer) {
      clearInterval(this.homeTimer)
      this.homeTimer = null
    }
  }

  /** Stop all timers. Called on exit: after shutDownPageContainer the
   * glasses go blank, but this page's JS keeps running - a live home
   * timer would otherwise keep re-fetching the digest forever. */
  shutdown(): void {
    if (this.pairPoll) {
      clearInterval(this.pairPoll)
      this.pairPoll = null
    }
    this.clearHomeTimer()
  }

  constructor(
    private render: (s: Screen) => Promise<void>,
    private upgrade: (body: string) => Promise<void>,
    private storage: { get(k: string): Promise<string>; set(k: string, v: string): Promise<void> },
    private exit: () => void,
  ) {}

  async start(): Promise<void> {
    this.token = (await this.storage.get(TOKEN_KEY)) || null
    if (this.token) {
      await this.goHome()
    } else {
      await this.goPairing()
    }
  }

  // ------------------------------------------------------------- pairing
  private async goPairing(notice?: string): Promise<void> {
    this.route = { name: 'pairing' }
    this.clearHomeTimer()
    let start: Awaited<ReturnType<typeof api.pairStart>>
    try {
      start = await api.pairStart()
    } catch {
      // Backend unreachable and even the demo stand-in failed: say so
      // instead of hanging on a blank pairing screen.
      await this.render({
        kind: 'text',
        body:
          `TG Glance - pairing unavailable\n\n` +
          `The backend is not reachable.\n` +
          `Check the connection, then\n` +
          `reopen the app to retry.\n\n(double-tap to exit)`,
      })
      return
    }
    this.pairSession = start.session
    this.pairCode = start.code
    this.pairExpiresSec = start.expiresInSec
    this.pairStartedAt = Date.now()
    await this.render({
      kind: 'text',
      body:
        `TG Glance - pair this device\n\n` +
        (notice ? `${notice}\n\n` : '') +
        `Open Telegram and send this\ncode to @Kingklwr:\n\n` +
        `      ${start.code}\n\n` +
        `Waiting for pairing...\n(double-tap to exit)`,
    })
    if (this.pairPoll) clearInterval(this.pairPoll)
    this.pairPoll = setInterval(async () => {
      if (this.route.name !== 'pairing' || !this.pairSession) return
      // Code expired before the user sent it: issue a fresh one instead
      // of polling a dead session forever.
      if (Date.now() - this.pairStartedAt > this.pairExpiresSec * 1000) {
        if (this.pairPoll) clearInterval(this.pairPoll)
        await this.goPairing('That code expired - here is a new one:')
        return
      }
      const st = await api.pairStatus(this.pairSession)
      if (st.paired) {
        if (this.pairPoll) clearInterval(this.pairPoll)
        this.token = st.token
        await this.storage.set(TOKEN_KEY, st.token)
        await this.goHome()
      }
    }, 2500)
  }

  // ---------------------------------------------------------------- home
  private async goHome(): Promise<void> {
    this.route = { name: 'home' }
    this.selectedIndex = 0
    this.clearHomeTimer()
    let digest: Awaited<ReturnType<typeof api.fetchDigest>>
    try {
      digest = await api.fetchDigest(this.token ?? '')
    } catch (e) {
      // Unpaired: the stored token is dead. Drop it and re-pair openly
      // instead of showing demo data as if the user were connected.
      if (e instanceof api.ApiError && e.status === 401) return this.onUnauthorized()
      throw e
    }
    this.chats = digest.chats
    this.rows = this.buildRows(digest)
    this.homeEmpty = this.chats.length === 0
    if (this.homeEmpty) {
      await this.render({
        kind: 'text',
        body:
          'TG Glance\n\nAll quiet - no unread chats\nin your watched communities.\n\n(tap: refresh - double-tap: exit)',
      })
    } else {
      await this.render({ kind: 'list', items: this.rows.map((r) => this.rowLabel(r)) })
    }
    // Refresh cadence: while the user sits on home, re-fetch on the
    // backend's snapshot rhythm so the list never goes quietly stale.
    this.homeTimer = setInterval(() => {
      if (this.route.name === 'home') void this.goHome()
    }, HOME_REFRESH_MS)
  }

  /** Status rows first, then chat rows. Order is the UX contract:
   * mention inbox on top, offline/stale notices above the chats. */
  private buildRows(digest: { generatedAt: string | number; chats: ChatSummary[] }): HomeRow[] {
    const rows: HomeRow[] = []
    if (api.demoMode) rows.push({ kind: 'offline' })
    const gen = digest.generatedAt
    if (typeof gen === 'number' && Date.now() / 1000 - gen > STALE_AFTER_SEC) {
      rows.push({ kind: 'stale' })
    }
    const totalMentions = digest.chats.reduce((n, c) => n + c.mentions, 0)
    if (totalMentions > 0) {
      const first = digest.chats.find((c) => c.mentions > 0)
      if (first) rows.push({ kind: 'mention', chatId: first.id })
    }
    for (const c of digest.chats) rows.push({ kind: 'chat', chatId: c.id })
    return rows
  }

  private rowLabel(row: HomeRow): string {
    switch (row.kind) {
      case 'offline':
        return 'Offline - demo data (tap to retry)'
      case 'stale': {
        return 'Digest is stale - tap to refresh'
      }
      case 'mention': {
        const total = this.chats.reduce((n, c) => n + c.mentions, 0)
        return total === 1 ? '1 question waiting for you' : `${total} questions waiting for you`
      }
      case 'chat': {
        const c = this.chats.find((x) => x.id === row.chatId)
        return c ? c.label : row.chatId
      }
    }
  }

  /** A 401 anywhere past pairing means the token died mid-session. */
  private async onUnauthorized(): Promise<void> {
    this.token = null
    await this.storage.set(TOKEN_KEY, '')
    await this.goPairing('Session expired - pair again:')
  }

  private async openMentionRow(chatId: string): Promise<void> {
    // Mention-first: jump straight to the reply screen for the chat that
    // asked the user something, skipping the digest. If the draft is not
    // there (yet), fall back to the digest.
    try {
      this.detail = await api.fetchChat(this.token ?? '', chatId)
    } catch (e) {
      if (e instanceof api.ApiError && e.status === 401) return this.onUnauthorized()
      throw e
    }
    if (this.detail?.draft) {
      await this.goReply(chatId)
    } else {
      await this.goDigest(chatId, 0)
    }
  }

  // -------------------------------------------------------------- digest
  private async goDigest(chatId: string, page: number, refresh = false): Promise<void> {
    this.route = { name: 'digest', chatId, page }
    this.clearHomeTimer()
    // On-open refresh: always re-fetch the detail when arriving from home
    // or the mention row, so the draft on the reply screen is never
    // stale. Page turns within a digest reuse the loaded detail.
    if (refresh || !this.detail || this.detail.id !== chatId) {
      try {
        this.detail = await api.fetchChat(this.token ?? '', chatId)
      } catch (e) {
        if (e instanceof api.ApiError && e.status === 401) return this.onUnauthorized()
        throw e
      }
    }
    const d = this.detail
    const total = d.chunks.length
    const footer =
      page < total - 1
        ? '\n\n(tap: more - double-tap: back)'
        : d.draft
          ? '\n\n(tap: see reply draft)'
          : '\n\n(tap: back to list)'
    await this.render({ kind: 'text', body: d.chunks[page] + footer })
  }

  // --------------------------------------------------------------- reply
  private async goReply(chatId: string): Promise<void> {
    this.route = { name: 'reply', chatId }
    const d = this.detail
    if (!d?.draft) return this.goHome()
    this.draftText = d.draft.text
    await this.render({
      kind: 'text',
      body:
        `${d.title} - reply\n\n` +
        (d.mentionText ? `They asked:\n${d.mentionText}\n\n` : '') +
        `Draft:\n${this.draftText}\n\n` +
        `(tap: SEND - double-tap: discard)`,
      menu: [
        { id: 1, name: 'Re-draft' },
        { id: 2, name: 'Shorter' },
      ],
    })
  }

  private async doSend(): Promise<void> {
    const route = this.route
    if (route.name !== 'reply' || !this.detail?.draft) return
    const res = await api.sendReply(this.token ?? '', this.detail.draft.id)
    this.route = { name: 'sent', chatId: route.chatId, ok: res.ok }
    await this.render({
      kind: 'text',
      body: res.ok
        ? `Sent to ${this.detail.title}\n\nYour reply is on its way.\n\n(tap: back to list)`
        : `Could not send.\n${res.detail}\n\n(tap: back to the draft)`,
    })
  }

  // --------------------------------------------------------------- input
  async onAction(a: Action): Promise<void> {
    const r = this.route
    switch (r.name) {
      case 'pairing': {
        if (a.type === 'double') return this.exit()
        // Demo mode only: a tap completes pairing so the flow is testable
        // without a phone. With a live backend the poll does this instead.
        if (a.type === 'click' && api.demoMode) {
          const st = api.demoPair()
          if (st.paired) {
            if (this.pairPoll) clearInterval(this.pairPoll)
            this.token = st.token
            await this.storage.set(TOKEN_KEY, st.token)
            await this.goHome()
          }
        }
        return
      }
      case 'home': {
        if (a.type === 'double') return this.exit()
        if (a.type === 'up') this.selectedIndex = Math.max(0, this.selectedIndex - 1)
        if (a.type === 'down')
          this.selectedIndex = Math.min(this.rows.length - 1, this.selectedIndex + 1)
        if (a.type === 'click') {
          // Empty digest: a tap refreshes instead of doing nothing.
          if (this.homeEmpty) return this.goHome()
          const row = this.rows[this.selectedIndex]
          if (!row) return
          switch (row.kind) {
            case 'offline':
              // Backend may be back: retry live, fall back to demo again
              // if it is still down (fetchDigest handles that).
              api.retryLive()
              return this.goHome()
            case 'stale':
              return this.goHome()
            case 'mention':
              return this.openMentionRow(row.chatId)
            case 'chat':
              return this.goDigest(row.chatId, 0, true)
          }
        }
        return
      }
      case 'digest': {
        if (a.type === 'double') return this.goHome()
        if (a.type === 'click') {
          const d = this.detail
          if (!d) return this.goHome()
          if (r.page < d.chunks.length - 1) return this.goDigest(r.chatId, r.page + 1)
          if (d.draft) return this.goReply(r.chatId)
          return this.goHome()
        }
        return
      }
      case 'reply': {
        if (a.type === 'double') return this.goDigest(r.chatId, 0)
        if (a.type === 'click') return this.doSend()
        if (a.type === 'menu') {
          const style = a.id === 2 ? 'shorter' : 'fresh'
          const next = await api.redraft(this.token ?? '', r.chatId, style)
          if (next) {
            this.draftText = next.text
            if (this.detail?.draft) this.detail.draft.text = next.text
            await this.goReply(r.chatId)
          }
        }
        return
      }
      case 'sent': {
        if (a.type === 'click' || a.type === 'double') {
          if (!r.ok && a.type === 'click') return this.goReply(r.chatId)
          return this.goHome()
        }
        return
      }
    }
  }
}

// Resolve an envelope's event type. CLICK_EVENT is 0 and protobuf drops
// zero fields, so a tap arrives with eventType ABSENT; the default must be
// resolved inside each envelope check, never on a merged object.
function eventTypeOf(envelope?: { eventType?: OsEventTypeList }): OsEventTypeList | null {
  if (!envelope) return null
  return envelope.eventType ?? OsEventTypeList.CLICK_EVENT
}

async function bootWithBridge(bridge: EvenAppBridge): Promise<void> {
  const renderer = new BridgeRenderer(bridge)
  // The firmware's list highlight: rebuildPageContainer resets it to the
  // first item, but the last listEvent's index lingers in this variable.
  // Reset it on every list render, or the next tap opens the row the
  // highlight USED to be on (proven Nov 24: the mention-row tap opened
  // Dow instead, because the index was stale at 1 from an earlier down).
  let listIndex = 0
  const app = new App(
    async (s) => {
      await renderer.show(s)
      if (s.kind === 'list') listIndex = 0
    },
    (b) => renderer.upgradeText(b),
    {
      get: (k) => bridge.getLocalStorage(k),
      set: async (k, v) => {
        await bridge.setLocalStorage(k, v)
      },
    },
    () => {
      app.shutdown()
      void bridge.shutDownPageContainer(1)
    },
  )

  bridge.onEvenHubEvent((event: EvenHubEvent) => {
    const sys = eventTypeOf(event.sysEvent)
    const txt = eventTypeOf(event.textEvent)
    const lst = eventTypeOf(event.listEvent)

    if (event.menuItemClickEvent?.itemID != null) {
      void app.onAction({ type: 'menu', id: event.menuItemClickEvent.itemID })
      return
    }
    if (event.listEvent?.currentSelectItemIndex != null) {
      listIndex = event.listEvent.currentSelectItemIndex
    }

    const types = [sys, txt, lst]
    if (types.includes(OsEventTypeList.DOUBLE_CLICK_EVENT)) {
      void app.onAction({ type: 'double' })
      return
    }
    if (types.includes(OsEventTypeList.SCROLL_TOP_EVENT)) {
      void app.onAction({ type: 'up' })
      return
    }
    if (types.includes(OsEventTypeList.SCROLL_BOTTOM_EVENT)) {
      void app.onAction({ type: 'down' })
      return
    }
    if (types.includes(OsEventTypeList.CLICK_EVENT)) {
      // For list pages the firmware highlight IS the selection.
      ;(app as unknown as { selectedIndex: number }).selectedIndex = listIndex
      void app.onAction({ type: 'click' })
    }
  })

  await app.start()
  console.log('TG Glance ready')
}

function bootWebPreview(): void {
  const wrap = document.getElementById('webpreview')
  const canvas = document.getElementById('glass') as HTMLCanvasElement | null
  if (!wrap || !canvas) return
  wrap.style.display = 'block'
  const renderer = new WebRenderer(canvas)
  let current: Screen = { kind: 'text', body: '' }
  const app = new App(
    async (s) => {
      current = s
      renderer.selectedIndex = (app as unknown as { selectedIndex: number }).selectedIndex
      renderer.show(s)
    },
    async (b) => renderer.show({ kind: 'text', body: b }),
    {
      get: async (k) => localStorage.getItem(k) ?? '',
      set: async (k, v) => localStorage.setItem(k, v),
    },
    () => {
      app.shutdown()
      console.log('exit requested (web preview)')
    },
  )
  let lastClick = 0
  canvas.addEventListener('click', () => {
    const now = Date.now()
    if (now - lastClick < 350) {
      void app.onAction({ type: 'double' })
      lastClick = 0
    } else {
      lastClick = now
      setTimeout(() => {
        if (lastClick !== 0) void app.onAction({ type: 'click' })
        lastClick = 0
      }, 360)
    }
  })
  window.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowUp') void app.onAction({ type: 'up' })
    if (e.key === 'ArrowDown') {
      void app.onAction({ type: 'down' })
      renderer.selectedIndex = (app as unknown as { selectedIndex: number }).selectedIndex
      renderer.show(current)
    }
  })
  void app.start()
}

// The bridge resolves immediately inside the Even app / simulator; in a
// plain browser it never does, so race it against a short timeout and
// fall back to the web preview.
const bridgeOrNull = await Promise.race([
  waitForEvenAppBridge().then((b) => b as EvenAppBridge | null),
  new Promise<null>((resolve) => setTimeout(() => resolve(null), 1500)),
])

if (bridgeOrNull) {
  await bootWithBridge(bridgeOrNull)
} else {
  bootWebPreview()
}
