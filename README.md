# TG Glance

**Your Telegram, at a glance.** The channels and communities that matter,
condensed to a few lines on your Even Realities G2 — and when something
needs an answer, an AI drafts the reply and you send it with **one tap**.
Your phone never leaves your pocket.

- **Track:** 01 · Messaging & News (Telegram) — also entered for
  **Best Telegram integration**.
- **Problem:** group chats and channels carry the signal (a claim window,
  a question with your name on it) buried in hundreds of messages. Checking
  means pulling out your phone and breaking the moment.
- **Who:** people who live in Telegram communities — crypto traders,
  DAO contributors, community mods — and need the 3-line version plus the
  ability to act on it, hands-free.
- **How:** a G2 app (Even Hub SDK, web app) talks to one small backend.
  The backend watches the user's own Telegram account, builds ranked
  digests fitted to the 576×288 display, pre-drafts replies to mentions,
  and sends — only ever after the user's tap on the glasses.

## Screens

0. **Pairing** — the glasses show a 6-digit code; you send it to the
   agent account in Telegram; the glasses unlock. (No Google sign-in —
   it does not work in the WebView; the organizers prescribe pairing
   codes, and so do we.)
1. **Home** — ranked list of chats with unread signal, mentions first.
2. **Digest** — 2–3 condensed bullets per chat, tap to page.
3. **Reply** — the question you were asked + the AI draft.
   **Tap = send.** Contextual menu: *Re-draft*, *Shorter*.
4. **Sent** — confirmation, then back to the list.

Nothing sends without a human tap. Sends are throttled server-side
(min interval + hourly cap). No funds, no keys in the app: the app talks
to exactly one origin (the backend), which is the only entry in the
`app.json` network whitelist.

## Setup

Prerequisites: Node 20+ (22+ recommended), Python 3.11+.

```bash
# 1) Even tools
npm install -g @evenrealities/evenhub-cli @evenrealities/evenhub-simulator

# 2) Backend (demo mode: no Telegram connection, sends go to outbox.jsonl)
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh                      # http://127.0.0.1:8787

# 3) App
cd ../tg-glance
npm install
npm run dev                   # http://localhost:5173

# 4) Simulator (separate terminal)
evenhub-simulator http://localhost:5173 --automation-port 9898
```

In demo mode, pairing completes via `POST /v1/pair/confirm` with the code
shown on the glasses (a stand-in for sending the code in Telegram; with a
live backend the Telethon listener confirms for real). The end-to-end
journey is scripted in `tg-glance/scripts/e2e_sim.py`.

**Live mode** (the demo video setup): run the backend with
`TELEGRAM_LIVE=1 SEND_ENABLED=1` and a Telegram session for a
project-owned account placed in `~/workspace/telegram/` (see
`backend/app/telegram_engine.py`). Reads are scoped to an allowlist of
communities; the demo shows only communities the account belongs to.

**Web preview:** open the Vite URL in a plain browser — with no Even
bridge present, the app renders the same screens to a canvas
(click = tap, double-click = double-tap, ↑/↓ = swipe).

**Package (optional):** `npm run pack` produces `tgglance.ehpk`.

## Architecture

```
G2 glasses <--BLE--> Even app (WebView) <--HTTPS--> TG Glance backend
                                                       |  pairing codes
                                                       |  digest pipeline
                                                       |  draft engine
                                                       +--> Telegram (Telethon)
```

- `tg-glance/` — the G2 app. TypeScript + Vite, `@evenrealities/even_hub_sdk`.
  A pure screen model (`src/render.ts`) feeds two renderers: the SDK
  bridge (real containers on the glasses) and a canvas fallback.
  All copy arrives pre-fitted from the backend.
- `backend/` — FastAPI service. `app/budgets.py` enforces the display
  budgets (list ≤ 20 × 64 chars, digest chunks ≤ ~450 chars) server-side;
  `app/demo.py` is the demo data provider running the same pipeline;
  `app/telegram_engine.py` is the live Telethon provider (off by default);
  `app/drafting.py` is the offline draft fallback (an LLM drafter plugs
  into the same function in production).

## What existed before Nov 23, 2026 (declared per the hackathon rules)

- The Telegram agent account **@Kingklwr** and its Telethon session/API
  credentials — created Nov 18, 2026 for unrelated agent work; a
  project-owned test account and a member of the communities in the demo.
- The official Even Hub documentation and `evenhub-templates` (MIT) were
  studied during preparation; this repository's code is original.
- A pre-window prototype spike (Nov 21): app scaffold, screen state
  machine, backend skeleton and demo data provider — written to de-risk
  the toolchain (simulator on a headless Linux VM) before the build
  window. The build continues during Nov 23–29 from this base.
- Third-party services used as-is: Telegram (MTProto via Telethon), the
  Even Hub SDK, and hosted LLM endpoints used by the backend for
  summarization and reply drafting.

## Privacy & safety

- Demo data: only communities the project account itself belongs to,
  plus a demo group we control. No third-party private DMs are read.
- The glasses app holds no API keys; the backend holds the Telegram
  session and never exposes it.
- Track 1 only: no funds anywhere in this project.

## License

MIT
