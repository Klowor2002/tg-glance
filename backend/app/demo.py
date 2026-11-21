"""Demo data provider.

Serves the same shapes as the live Telegram provider, generated from raw
"messages" through the real budget pipeline, so the whole read/write flow
can be exercised without a Telegram connection. The live provider
(telegram_engine.py) replaces `load_snapshot()` when TELEGRAM_LIVE=1.
"""

from .budgets import chunk_text, fit_list_label
from .drafting import draft_reply

# Raw snapshot: chat -> (unread, mentions, bulletin lines, mention text)
_RAW = {
    "dow": {
        "title": "Dow Protocol",
        "unread": 12,
        "mentions": 2,
        "lines": [
            "Dow Protocol - last 3h",
            "",
            "- Claim window for cycle 2 opens",
            "  Friday 07:00 WIB, link pinned.",
            "- Aurox quiz answers close",
            "  tonight; rewards post Monday.",
            "- Mods remind: vault deposits",
            "  stay closed until the audit",
            "  note is published.",
            "- Weekly AMA moved to Sunday.",
        ],
        "mention": "@you: does the claim window open Friday 07:00 WIB?",
    },
    "qyro": {
        "title": "Qyro Official",
        "unread": 5,
        "mentions": 0,
        "lines": [
            "Qyro Official - last 3h",
            "",
            "- Neon Striker badge wave 2",
            "  is live for 10,000 XP holders.",
            "- Star Dogfight event returns",
            "  this weekend, 1,000 XP pool.",
        ],
        "mention": None,
    },
    "zkv": {
        "title": "zkVerify Agents",
        "unread": 3,
        "mentions": 0,
        "lines": [
            "zkVerify Agents - last 3h",
            "",
            "- Round 8 standings posted;",
            "  proof verification is lagging",
            "  the leaderboard by ~1 day.",
            "- Wildcard reviews still open.",
        ],
        "mention": None,
    },
    "base": {
        "title": "Base Builders",
        "unread": 2,
        "mentions": 0,
        "lines": [
            "Base Builders - last 3h",
            "",
            "- Builder Quest demo day",
            "  moved to Dec 5, submissions",
            "  close 23:59 UTC same day.",
        ],
        "mention": None,
    },
}


def load_snapshot() -> dict:
    chats = []
    details = {}
    # Mentions first, then most unread - the ranking the home list shows.
    ordered = sorted(
        _RAW.items(), key=lambda kv: (-(kv[1]["mentions"] > 0), -kv[1]["unread"])
    )
    for chat_id, raw in ordered:
        label = fit_list_label(
            f"{raw['title']} - {raw['unread']} new"
            + (f" - {raw['mentions']} @you" if raw["mentions"] else "")
        )
        draft = None
        if raw["mention"]:
            draft = {
                "id": f"draft-{chat_id}",
                "text": draft_reply(raw["mention"], raw["title"]),
            }
        chats.append(
            {
                "id": chat_id,
                "title": raw["title"],
                "unread": raw["unread"],
                "mentions": raw["mentions"],
                "label": label,
                "hasDraft": draft is not None,
            }
        )
        details[chat_id] = {
            "id": chat_id,
            "title": raw["title"],
            "chunks": chunk_text("\n".join(raw["lines"])),
            "mentionText": raw["mention"],
            "draft": draft,
        }
    return {"chats": chats, "details": details}
