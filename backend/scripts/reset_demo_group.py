"""Reset the demo group history, then read back the live send result.

Usage: reset_demo_group.py [--readback-only]
  Default: delete every message in "TG Glance Demo" (our own test group)
  so the next stage+send run leaves exactly one clean mention->reply pair.
  --readback-only: list the group's recent messages (sender, text) so the
  live send can be verified from Telegram itself. Prints only public data.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["TELEGRAM_LIVE"] = "1"

from app.main import engine  # noqa: E402

DEMO_TITLE = "TG Glance Demo"


async def main() -> int:
    readback_only = "--readback-only" in sys.argv
    await engine.start()
    try:
        client = engine.client
        dialogs = await client.get_dialogs(limit=100)
        demo = next((d for d in dialogs if d.name == DEMO_TITLE), None)
        if demo is None:
            print("no demo group found")
            return 1
        history = await client.get_messages(demo, limit=20)
        for m in history:
            sender = getattr(m.sender, "username", None) or getattr(m.sender, "id", "?")
            print(f"  msg {m.id} from @{sender}: {(m.text or '')[:100]!r}")
        if readback_only:
            ok = any(
                (m.text or "").startswith("Yes - 07:00 WIB")
                and (getattr(m.sender, "username", "") == "Kingklwr")
                for m in history
            )
            print("READBACK:", "OK - live reply present in Telegram" if ok else "FAIL - reply not found")
            return 0 if ok else 1
        ids = [m.id for m in history]
        if ids:
            await client.delete_messages(demo, ids)
            print(f"deleted {len(ids)} messages from demo group")
        return 0
    finally:
        if engine.client is not None:
            await engine.client.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
