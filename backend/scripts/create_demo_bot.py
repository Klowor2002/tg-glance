"""Create a demo bot via @BotFather for the Nov 25 live-mention staging.

The bot lives only in our own demo group and posts staged questions that
mention @Kingklwr on cue, so the live mention -> draft -> tap-to-send loop
can be proven without a third-party user and deterministically re-staged
for the Nov 26 demo video. The bot token is a secret: it is written to a
0600 file in-process and NEVER printed (only its length is reported).
"""

import asyncio
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["TELEGRAM_LIVE"] = "1"

from app.main import engine  # noqa: E402

TOKEN_FILE = os.path.join(os.path.dirname(__file__), "..", ".demo-bot-token")
BOTFATHER = "BotFather"  # resolved by username (numeric id is not cached)
NAME = "TG Glance Demo Bot"
USERNAMES = ["tgglancedemobot", "tg_glance_demo_bot", "glance_demo_bot", "kingklwr_glance_bot"]


async def main() -> int:
    await engine.start()
    try:
        client = engine.client
        token_path = os.path.abspath(TOKEN_FILE)
        if os.path.exists(token_path):
            print("token file already exists - refusing to recreate (delete it first if a fresh bot is really needed)")
            return 2

        async with client.conversation(BOTFATHER, timeout=90) as conv:
            await conv.send_message("/newbot")
            r = await conv.get_response()
            print("botfather:", " ".join(r.text.split())[:120])
            await conv.send_message(NAME)
            r = await conv.get_response()
            print("botfather:", " ".join(r.text.split())[:120])
            token = None
            used = None
            for uname in USERNAMES:
                await conv.send_message(uname)
                r = await conv.get_response()
                text = r.text or ""
                print(f"botfather [{uname}]:", " ".join(text.split())[:160])
                m = re.search(r"(\d{6,12}:[A-Za-z0-9_-]{30,})", text)
                if m:
                    token = m.group(1)
                    used = uname
                    break
                if "taken" not in text.lower() and "sorry" not in text.lower():
                    print("unexpected BotFather reply - stopping")
                    return 1
            if not token:
                print("BOT CREATE FAIL: no username accepted")
                return 1
        with open(token_path, "w") as f:
            f.write(token + "\n")
        os.chmod(token_path, 0o600)
        print(f"BOT OK: username=@{used} token saved to {token_path} (0600, length {len(token)})")
        return 0
    finally:
        if engine.client is not None:
            await engine.client.disconnect()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
