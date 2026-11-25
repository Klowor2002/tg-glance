"""Nov 25 live tap-to-send E2E test (HTTP surface, real Telegram send).

Runs the FastAPI app in-process (TestClient) with TELEGRAM_LIVE=1 and
SEND_ENABLED=1, so the Telethon client is the real one. The pairing-bind
step calls main._bind_pair directly - that is exactly the callback the
Telethon NewMessage listener invokes when the pairing code arrives in
Telegram, so this simulates the production pairing event without a human
needing to send the code. Prints only public data (ids, statuses, draft
text, throttle responses). No credentials, no session material.

Checks:
 1. pair/start + simulated listener bind -> paired + token
 2. digest without token -> 401
 3. digest -> demo group hasDraft (live mention from the demo bot)
 4. chat detail -> draft text matches the Friday 07:00 question
 5. redraft fresh + shorter
 6. send -> {"ok": true, "detail": "sent via telegram"} (REAL Telegram send)
 7. immediate re-send -> 429 too fast (5 s throttle)
 8. unknown draft -> 404
 9. hourly cap (20 pre-filled recent sends) -> 429 hourly cap
Read-back that the reply landed in the group is done by the separate
scripts/readback_send.py after this process exits (fresh client, own loop).
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["TELEGRAM_LIVE"] = "1"
os.environ["SEND_ENABLED"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402

DEMO_ID = "-1005970341035"
FAILURES = []


def check(name, cond, extra=""):
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")
    if not cond:
        FAILURES.append(name)


def run() -> int:
    with TestClient(main.app) as c:
        print("healthz:", c.get("/healthz").json())
        r = c.get("/v1/digest")
        check("digest without token -> 401", r.status_code == 401, f"got {r.status_code}")

        r = c.post("/v1/pair/start")
        assert r.status_code == 200, r.text
        session, code = r.json()["session"], r.json()["code"]
        print(f"pair code issued: {code!r} (dev log only)")
        main._bind_pair(session)  # simulate Telethon listener firing
        r = c.get("/v1/pair/status", params={"session": session})
        assert r.status_code == 200, r.text
        assert r.json()["paired"] is True
        token = r.json()["token"]
        print("paired as:", r.json()["accountLabel"])
        H = {"Authorization": f"Bearer {token}"}

        r = c.get("/v1/digest", headers=H)
        assert r.status_code == 200, r.text
        chats = r.json()["chats"]
        demo = next((x for x in chats if x["id"] == DEMO_ID), None)
        check("demo group in live digest", demo is not None)
        check("demo group hasDraft", bool(demo and demo["hasDraft"]), f"hasDraft={demo and demo['hasDraft']}")
        print("demo label:", demo and demo["label"])

        r = c.get(f"/v1/chat/{DEMO_ID}", headers=H)
        assert r.status_code == 200, r.text
        detail = r.json()
        print("mentionText:", detail.get("mentionText"))
        draft = detail.get("draft")
        check("draft present", draft is not None)
        print("draft:", draft and draft["text"])
        check(
            "draft answers the 07:00 WIB question",
            bool(draft and "07:00 WIB" in draft["text"]),
        )
        draft_id = draft["id"]

        r = c.post("/v1/reply/redraft", json={"chat_id": DEMO_ID, "style": "fresh"}, headers=H)
        check("redraft fresh 200", r.status_code == 200, f"got {r.status_code}: {r.text[:120]}")
        print("redraft fresh:", r.json().get("text") if r.status_code == 200 else "")
        r = c.post("/v1/reply/redraft", json={"chat_id": DEMO_ID, "style": "shorter"}, headers=H)
        check("redraft shorter 200", r.status_code == 200, f"got {r.status_code}")

        r = c.post("/v1/reply/send", json={"draft_id": "draft-nope"}, headers=H)
        check("unknown draft -> 404", r.status_code == 404, f"got {r.status_code}")

        r = c.post("/v1/reply/send", json={"draft_id": draft_id}, headers=H)
        print("send response:", r.status_code, r.text[:200])
        check("live send 200 + sent via telegram", r.status_code == 200 and r.json().get("detail") == "sent via telegram")

        r = c.post("/v1/reply/send", json={"draft_id": draft_id}, headers=H)
        check("immediate re-send -> 429 too fast", r.status_code == 429, f"got {r.status_code}: {r.text[:120]}")

        # Hourly cap: 20 recent sends, last one 10 s ago (passes interval, hits cap).
        real_times = list(main._send_times)
        now = time.time()
        main._send_times = [now - 10 - i for i in range(20)]
        r = c.post("/v1/reply/send", json={"draft_id": draft_id}, headers=H)
        check("hourly cap -> 429", r.status_code == 429 and "hourly cap" in r.text, f"got {r.status_code}: {r.text[:120]}")
        main._send_times = real_times

    if main.engine.client is not None:
        try:
            import asyncio

            coro = main.engine.client.disconnect()
            if coro is not None:
                asyncio.run(coro)
        except Exception as exc:  # noqa: BLE001 - process exit disconnects anyway
            print(f"disconnect note: {exc!r}")
    print("FAILURES:", FAILURES or "none")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    raise SystemExit(run())
