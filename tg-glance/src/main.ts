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

const TOKEN_KEY = 'tgglance.token'

class App {
  private route: Route = { name: 'pairing' }
  private token: string | null = null
  private pairSession: string | null = null
  private pairCode = ''
  private pairPoll: ReturnType<typeof setInterval> | null = null
  private chats: ChatSummary[] = []
  private detail: ChatDetail | null = null
  private draftText = ''
  private selectedIndex = 0

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
  private async goPairing(): Promise<void> {
    this.route = { name: 'pairing' }
    const start = await api.pairStart()
    this.pairSession = start.session
    this.pairCode = start.code
    await this.render({
      kind: 'text',
      body:
        `TG Glance - pair this device\n\n` +
        `Open Telegram and send this\ncode to @Kingklwr:\n\n` +
        `      ${start.code}\n\n` +
        `Waiting for pairing...\n(double-tap to exit)`,
    })
    if (this.pairPoll) clearInterval(this.pairPoll)
    this.pairPoll = setInterval(async () => {
      if (this.route.name !== 'pairing' || !this.pairSession) return
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
    const digest = await api.fetchDigest(this.token ?? '')
    this.chats = digest.chats
    if (this.chats.length === 0) {
      await this.render({
        kind: 'text',
        body: 'TG Glance\n\nAll quiet - no unread chats\nin your watched communities.\n\n(double-tap to exit)',
      })
      return
    }
    await this.render({ kind: 'list', items: this.chats.map((c) => c.label) })
  }

  // -------------------------------------------------------------- digest
  private async goDigest(chatId: string, page: number): Promise<void> {
    this.route = { name: 'digest', chatId, page }
    if (!this.detail || this.detail.id !== chatId) {
      this.detail = await api.fetchChat(this.token ?? '', chatId)
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
          this.selectedIndex = Math.min(this.chats.length - 1, this.selectedIndex + 1)
        if (a.type === 'click') {
          const chat = this.chats[this.selectedIndex]
          if (chat) await this.goDigest(chat.id, 0)
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
  const app = new App(
    (s) => renderer.show(s),
    (b) => renderer.upgradeText(b),
    {
      get: (k) => bridge.getLocalStorage(k),
      set: async (k, v) => {
        await bridge.setLocalStorage(k, v)
      },
    },
    () => {
      void bridge.shutDownPageContainer(1)
    },
  )

  let listIndex = 0
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
    () => console.log('exit requested (web preview)'),
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
