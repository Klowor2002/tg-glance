"""Live Telegram provider (Telethon) — OFF unless TELEGRAM_LIVE=1.

Uses the project-owned agent account session from ~/workspace/telegram/
(pre-existing infrastructure, declared in the README). Credentials are
read in-process at runtime and never logged, returned, or committed.

Safety rails:
- Reads are scoped to CHAT_ALLOWLIST (dialog ids) when set.
- Sending requires SEND_ENABLED=1 as well, and main.py throttles sends.
- The pairing listener binds an app session when the pairing code is
  received as a message to the agent account.
"""

import json
import os

TG_DIR = os.path.expanduser("~/workspace/telegram")


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
            os.path.join(TG_DIR, "agent"), creds["api_id"], creds["api_hash"]
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
        await self.client.send_message(chat_id, text)
