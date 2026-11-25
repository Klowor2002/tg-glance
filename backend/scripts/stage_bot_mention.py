"""Invite the demo bot to the demo group and have it stage a mention.

The bot posts as a different user, so Telegram flags the mention of
@Kingklwr (mentioned=True) and the live snapshot builds a draft from it.
Bot token is read in-process from the 0600 file and never printed.
Prints only public data: group/bot ids, message ids, mention flags.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["TELEGRAM_LIVE"] = "1"

import requests  # noqa: E402

from app.main import engine  # noqa: E402

DEMO_TITLE = "TG Glance Demo"
BOT_USERNAME = "tgglancedemobot"
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "..", ".demo-bot-token")
Q = "TG Glance test - @Kingklwr is the Friday demo still on for 07:00 WIB?"


async def main() -> int:
    with open(os.path.abspath(TOKEN_FILE)) as f:
        token = f.read().strip()
    await engine.start()
    try:
        client = engine.client
        dialogs = await client.get_dialogs(limit=100)
        demo = next((d for d in dialogs if d.name == DEMO_TITLE), None)
        if demo is None:
            print("no demo group found")
            return 1
        print(f"demo group: {demo.name!r} id={demo.id}")

        bot = await client.get_entity(BOT_USERNAME)
        print(f"bot: @{bot.username} id={bot.id}")
        from telethon.tl.functions.channels import InviteToChannelRequest

        try:
            await client(InviteToChannelRequest(demo, [bot]))
            print("bot invited to demo group")
        except Exception as exc:  # already a member, etc.
            print(f"invite note (continuing): {type(exc).__name__}: {exc}")

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        resp = requests.post(
            url, json={"chat_id": demo.id, "text": Q}, timeout=60
        )
        body = resp.json()
        if not body.get("ok"):
            print(f"BOT SEND FAIL: HTTP {resp.status_code} {body.get('description')}")
            return 1
        print(f"bot staged mention: msg_id={body['result']['message_id']}")

        raw = await engine.snapshot()
        hit = next((c for c in raw["chats"] if str(c["id"]) == str(demo.id)), None)
        if hit is None:
            print("SNAPSHOT MISS: demo group not in snapshot chats")
            return 1
        print(
            f"snapshot: mentions={hit['mentions']} mentionText={hit['mentionText']!r}"
        )
        if not hit.get("mentionText"):
            print("STAGE FAIL: mentionText still empty")
            return 1
        print("STAGE OK: live mention staged via demo bot")
        return 0
    finally:
        if engine.client is not None:
            await engine.client.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
