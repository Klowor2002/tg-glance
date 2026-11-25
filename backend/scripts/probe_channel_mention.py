"""Probe: does a channel post mentioning @Kingklwr flag mentioned=True?

Channel posts are authored by the channel, not the user, so the server may
flag a self-mention in a channel where it does not for a group message.
Prints only public data. No credentials, no session material.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["TELEGRAM_LIVE"] = "1"

from app.main import engine  # noqa: E402

TITLE = "TG Glance Demo Channel"
Q = "TG Glance test - @Kingklwr is the Friday demo still on for 07:00 WIB?"


async def main() -> int:
    await engine.start()
    try:
        client = engine.client
        dialogs = await client.get_dialogs(limit=100)
        ch = next((d for d in dialogs if d.name == TITLE), None)
        if ch is None:
            from telethon.tl.functions.channels import CreateChannelRequest

            created = await client(
                CreateChannelRequest(
                    title=TITLE,
                    about="TG Glance demo channel - agent test chat",
                    megagroup=False,
                )
            )
            chat = created.chats[0]
            print(f"created channel: {chat.title!r} id={chat.id}")
            ch_id = chat.id
        else:
            print(f"channel exists: {ch.name!r} id={ch.id}")
            ch_id = ch.id

        sent = await client.send_message(ch_id, Q)
        print(f"posted: msg_id={sent.id}")
        history = await client.get_messages(ch_id, limit=5)
        for m in history:
            print(
                f"  msg {m.id} out={m.out} mentioned={getattr(m, 'mentioned', None)} "
                f"text={(m.text or '')[:80]!r}"
            )
        raw = await engine.snapshot()
        hit = next((c for c in raw["chats"] if str(c["id"]) == str(ch_id)), None)
        if hit is None:
            print("SNAPSHOT MISS for channel")
            return 1
        print(
            f"snapshot: mentions={hit['mentions']} mentionText={hit['mentionText']!r}"
        )
        return 0 if hit.get("mentionText") else 1
    finally:
        if engine.client is not None:
            await engine.client.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
