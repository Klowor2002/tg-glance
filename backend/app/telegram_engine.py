"""Live Telegram provider (Telethon) — OFF unless TELEGRAM_LIVE=1.

Uses the project-owned agent account session from ~/workspace/telegram/
(pre-existing infrastructure, declared in the README). Credentials are
read in-process at runtime and never logged, returned, or committed.

Safety rails:
- Reads are scoped to groups/channels the account belongs to; private
  DMs are never read or shown (PREP privacy rule). An explicit
  TG_CHAT_ALLOWLIST (comma-separated dialog ids or exact titles) can
  narrow the scope further to e.g. the demo group.
- Sending requires SEND_ENABLED=1 as well, and main.py throttles sends.
- The pairing listener binds an app session when the pairing code is
  received as a message to the agent account.

Transport: this VM only reaches the internet through the egress HTTP
proxy, so the Telethon client is built with the proxy from the
environment (same construction as ~/workspace/telegram/test_read.py).
Without it, client.start() hangs on a direct TCP connect that never
completes.
"""

import json
import os
import time
from urllib.parse import urlparse

TG_DIR = os.path.expanduser("~/workspace/telegram")
SNAPSHOT_MAX_CHATS = 8
SNAPSHOT_MAX_MSGS = 15
SNAPSHOT_WINDOW_SEC = 3 * 3600


def _proxy_from_env():
    raw = os.environ.get("https_proxy") or os.environ.get("HTTPS_PROXY")
    if not raw:
        return None
    u = urlparse(raw)
    return {
        "proxy_type": "http",
        "addr": u.hostname,
        "port": u.port or 3128,
        "username": u.username,
        "password": u.password,
        "rdns": True,
    }


def _allowlist():
    raw = os.environ.get("TG_CHAT_ALLOWLIST", "").strip()
    if not raw:
        return None
    return {part.strip() for part in raw.split(",") if part.strip()}


class TelegramEngine:
    def __init__(self) -> None:
        self.client = None
        self._pair_codes: dict[str, str] = {}  # code -> app session id
        self.on_paired = None  # callback(session_id)

    @property
    def live(self) -> bool:
        return os.environ.get("TELEGRAM_LIVE") == "1"

    @property
    def send_enabled(self) -> bool:
        return self.live and os.environ.get("SEND_ENABLED") == "1"

    async def start(self) -> None:
        if not self.live:
            return
        from telethon import TelegramClient, events

        with open(os.path.join(TG_DIR, "api_credentials.json")) as f:
            creds = json.load(f)
        self.client = TelegramClient(
            os.path.join(TG_DIR, "agent"),
            creds["api_id"],
            creds["api_hash"],
            proxy=_proxy_from_env(),
            # The egress proxy is slow (HTTPS fetches take 10-20 s through
            # it); Telethon's 10 s default connect timeout expires before
            # the proxy finishes the CONNECT to the DC.
            timeout=60,
        )
        await self.client.start()

        @self.client.on(events.NewMessage(incoming=True))
        async def _listener(event):  # pragma: no cover - live only
            text = (event.raw_text or "").strip()
            session = self._pair_codes.pop(text, None)
            if session and self.on_paired:
                self.on_paired(session)

    def watch_pair_code(self, code: str, session: str) -> None:
        self._pair_codes[code] = session

    async def send(self, chat_id: str, text: str) -> None:
        if not self.send_enabled or self.client is None:
            raise RuntimeError("telegram send is not enabled")
        await self.client.send_message(int(chat_id), text)

    async def snapshot(self) -> dict:
        """Raw live snapshot: ranked chats + recent messages per chat.

        Returns {"chats": [...], "fetchedAt": epoch}. Each chat:
        {id, title, unread, mentions, mentionText, messages: [str]}.
        Raises if the client is not connected.
        """
        if self.client is None:
            raise RuntimeError("telegram client is not started")
        allow = _allowlist()
        dialogs = await self.client.get_dialogs(limit=100)
        now = time.time()
        window_start = now - SNAPSHOT_WINDOW_SEC
        chats = []
        for d in dialogs:
            # Scope: communities only — never private DMs (PREP privacy rule).
            if not (d.is_group or d.is_channel):
                continue
            if allow is not None and str(d.id) not in allow and d.name not in allow:
                continue
            unread = d.unread_count or 0
            mentions = d.unread_mentions_count or 0
            messages = []
            mention_text = None
            try:
                history = await self.client.get_messages(d, limit=SNAPSHOT_MAX_MSGS)
            except Exception:
                history = []
            for m in history:
                text = (getattr(m, "text", None) or "").strip()
                if not text:
                    continue
                ts = m.date.timestamp() if getattr(m, "date", None) else 0
                if ts and ts < window_start:
                    continue
                messages.append(text)
                if mention_text is None and getattr(m, "mentioned", False):
                    mention_text = text
            # A mention inside the window outranks unread counts for ranking,
            # but a chat with no recent traffic still shows with stale counts.
            chats.append(
                {
                    "id": str(d.id),
                    "title": d.name or "Unknown",
                    "unread": unread,
                    "mentions": mentions,
                    "mentionText": ("@you: " + mention_text) if mention_text else None,
                    "messages": messages,
                }
            )
        chats.sort(key=lambda c: (-(c["mentions"] > 0), -c["unread"]))
        return {"chats": chats[:SNAPSHOT_MAX_CHATS], "fetchedAt": now}
