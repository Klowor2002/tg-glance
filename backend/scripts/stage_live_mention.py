"""Stage a live mention for the Nov 25 tap-to-send test.

Creates the demo megagroup "TG Glance Demo" if it does not exist (our own
agent account's group, no third parties), posts a staged question that
mentions @Kingklwr, then checks whether the live snapshot picks it up as
a mention (mentionText -> draft). Prints only public data: group title/id,
message ids, mention flags. No credentials, no session material.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["TELEGRAM_LIVE"] = "1"

from app.main import engine  # noqa: E402

DEMO_TITLE = "TG Glance Demo"
STAGED_Q = "TG Glance test - @Kingklwr is the Friday demo still on for 07:00 WIB?"


async def main() -> int:
    await engine.start()
    try:
        client = engine.client
        print("authorized:", await client.is_user_authorized())
        me = await client.get_me()
        print("account:", me.username, "id:", me.id)

        dialogs = await client.get_dialogs(limit=100)
        demo = next((d for d in dialogs if d.name == DEMO_TITLE), None)
        if demo is None:
            from telethon.tl.functions.channels import CreateChannelRequest

            created = await client(
                CreateChannelRequest(
                    title=DEMO_TITLE,
                    about="TG Glance demo group - agent test chat",
                    megagroup=True,
                )
            )
            chat = created.chats[0]
            print(f"created demo group: {chat.title!r} id={chat.id}")
            demo_id = chat.id
        else:
            print(f"demo group exists: {demo.name!r} id={demo.id}")
            demo_id = demo.id

        sent = await client.send_message(demo_id, STAGED_Q)
        print(f"staged mention sent: msg_id={sent.id}")

        # Read back: does Telegram flag the self-mention?
        history = await client.get_messages(demo_id, limit=5)
        for m in history:
            print(
                f"  msg {m.id} out={m.out} mentioned={getattr(m, 'mentioned', None)} "
                f"text={(m.text or '')[:80]!r}"
            )

        raw = await engine.snapshot()
        hit = next((c for c in raw["chats"] if str(c["id"]) == str(demo_id)), None)
        if hit is None:
            print("SNAPSHOT MISS: demo group not in snapshot chats")
            print("  snapshot titles:", [c["title"] for c in raw["chats"]])
            return 1
        print(
            f"snapshot: title={hit['title']!r} unread={hit['unread']} "
            f"mentions={hit['mentions']} mentionText={hit['mentionText']!r}"
        )
        if not hit.get("mentionText"):
            print("STAGE FAIL: no mentionText - self-mention not flagged")
            return 1
        print("STAGE OK: live mention staged, draft will be built from it")
        return 0
    finally:
        if engine.client is not None:
            await engine.client.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
