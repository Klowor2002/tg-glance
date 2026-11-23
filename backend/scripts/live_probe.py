"""Live-provider probe (read-only): verify the Telethon snapshot end to end.

Usage: TELEGRAM_LIVE=1 .venv/bin/python scripts/live_probe.py
Prints only public data: dialog titles/counts and truncated message text
from the communities the agent account belongs to. No credentials, no
session material, no chain writes, no sends.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["TELEGRAM_LIVE"] = "1"

from app.main import engine  # noqa: E402
from app.summarizing import build_snapshot  # noqa: E402


async def main() -> int:
    await engine.start()
    try:
        if engine.client is None:
            print("PROBE FAIL: client did not start")
            return 1
        print("authorized:", await engine.client.is_user_authorized())
        dialogs = await engine.client.get_dialogs(limit=100)
        groups = [d for d in dialogs if d.is_group or d.is_channel]
        print(f"dialogs: {len(dialogs)} total, {len(groups)} groups/channels")
        for d in groups:
            print(
                f"  - {d.name!r} id={d.id} unread={d.unread_count or 0} "
                f"mentions={d.unread_mentions_count or 0}"
            )
        raw = await engine.snapshot()
        print(f"snapshot chats: {len(raw['chats'])}")
        for c in raw["chats"]:
            print(
                f"  * {c['title']!r} unread={c['unread']} mentions={c['mentions']} "
                f"msgs={len(c['messages'])} mention={bool(c['mentionText'])}"
            )
            for m in c["messages"][:3]:
                print("      msg:", " ".join(m.split())[:80])
        data = build_snapshot(raw)
        assert len(data["chats"]) <= 20, "too many chats for the glasses list"
        for chat in data["chats"]:
            assert len(chat["label"]) <= 64, f"label too long: {chat['label']!r}"
            det = data["details"][chat["id"]]
            for chunk in det["chunks"]:
                assert len(chunk) <= 450, f"chunk too long ({len(chunk)})"
            print(f"  built {chat['title']!r}: label={chat['label']!r} "
                  f"chunks={len(det['chunks'])} hasDraft={chat['hasDraft']}")
            for chunk in det["chunks"]:
                print("    chunk:", repr(chunk[:120]))
        print("PROBE OK: live snapshot builds within glasses budgets")
        return 0
    finally:
        if engine.client is not None:
            await engine.client.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
