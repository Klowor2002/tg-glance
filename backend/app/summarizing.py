"""Live digest builder: raw Telethon snapshot -> glasses-shaped snapshot.

Same output shape as demo.load_snapshot() so the app and the HTTP layer
do not care which provider produced the data:
  {"chats": [{id, title, unread, mentions, label, hasDraft}],
   "details": {id: {id, title, chunks, mentionText, draft}}}

Summarization runs through a free helper model behind the budget
pipeline; ANY failure (timeout, empty answer, unparsable output) falls
back to extractive bullets taken verbatim from recent messages, so the
digest pipeline can never die on the LLM. Bullets and drafts are fitted
to the glasses copy budgets here, never by eyeballing prompts.
"""

import subprocess
import sys

from .budgets import chunk_text, fit_list_label
from .drafting import draft_reply

HELPER = "/home/hatch/workspace/nvidia/helper.py"
GROQ_HELPER = "/home/hatch/workspace/groq/helper.py"
LLM_TIMEOUT_SEC = 25
MAX_BULLETS = 4
BULLET_MAX = 90
# LLM calls are the slow part of a refresh (Groq ~6 s each); cap them per
# refresh so a digest rebuild never takes minutes. Chats past the cap use
# the extractive fallback, which is always available.
LLM_CALLS_PER_REFRESH = 4


def _parse_bullets(text: str) -> list[str] | None:
    lines = []
    for ln in text.splitlines():
        ln = ln.strip()
        if ln.startswith("[helper:"):
            continue
        if ln.startswith("- "):
            lines.append(ln[2:].strip())
        elif ln.startswith("• "):
            lines.append(ln[2:].strip())
    lines = [ln for ln in lines if ln]
    if not (2 <= len(lines) <= 6):
        return None
    bullets = []
    for ln in lines[:MAX_BULLETS]:
        if len(ln) > BULLET_MAX:
            ln = ln[: BULLET_MAX - 1].rstrip() + "…"
        bullets.append(ln)
    return bullets


def _llm_bullets(title: str, messages: list[str]) -> list[str] | None:
    """Ask a free helper model to condense recent messages. None on failure.

    Route order (measured 2026-11-23): Groq first (fast, ~6 s, free tier);
    NVIDIA direct second (times out through today's egress); anything
    failing falls through to the extractive fallback in build_snapshot.
    ApiNex is NOT routed: it now 402s behind a $5 top-up (PAY RULE: $0).
    """
    if not messages:
        return None
    joined = "\n".join(f"- {m}" for m in messages[:12])
    prompt = (
        f"Summarize these recent Telegram messages from the group '{title}' "
        f"into 3 short factual bullets for smart glasses. Rules: each bullet "
        f"under 90 characters, plain text, no markdown, no preamble, one "
        f"bullet per line starting with '- '. Do not invent facts not in "
        f"the messages.\n\nMessages:\n{joined}"
    )
    # Groq helper takes the prompt as argv[1] and prints only the reply.
    try:
        proc = subprocess.run(
            [sys.executable, GROQ_HELPER, prompt],
            capture_output=True,
            text=True,
            timeout=LLM_TIMEOUT_SEC,
        )
        if proc.returncode == 0:
            bullets = _parse_bullets(proc.stdout)
            if bullets:
                return bullets
    except Exception:
        pass
    # NVIDIA helper reads the prompt from stdin.
    try:
        proc = subprocess.run(
            [sys.executable, HELPER, "saring"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=LLM_TIMEOUT_SEC,
        )
        if proc.returncode == 0:
            return _parse_bullets(proc.stdout)
    except Exception:
        pass
    return None


def _extractive_bullets(messages: list[str]) -> list[str]:
    """Verbatim fallback: the most substantive recent messages, truncated."""
    bullets = []
    for m in messages:
        one = " ".join(m.split())
        if len(one) < 12:
            continue
        if one.lower().startswith(("http", "t.me/", "www.")):
            continue
        if len(one) > BULLET_MAX:
            one = one[: BULLET_MAX - 1].rstrip() + "…"
        bullets.append(one)
        if len(bullets) >= MAX_BULLETS:
            break
    return bullets


def build_snapshot(raw: dict) -> dict:
    chats = []
    details = {}
    llm_left = LLM_CALLS_PER_REFRESH
    for chat in raw["chats"]:
        title = chat["title"]
        bullets = None
        if chat["messages"] and llm_left > 0:
            bullets = _llm_bullets(title, chat["messages"])
            if bullets:
                llm_left -= 1
            else:
                # LLM route is down for this refresh: fail fast to
                # extractive for the remaining chats instead of burning
                # a 25 s timeout per chat.
                llm_left = 0
        if not bullets:
            bullets = _extractive_bullets(chat["messages"])
        if bullets:
            body = "\n".join(f"- {b}" for b in bullets)
        else:
            body = "No new messages in the last 3h."
        text = f"{title} - last 3h\n\n{body}"
        draft = None
        if chat.get("mentionText"):
            draft = {
                "id": f"draft-{chat['id']}",
                "text": draft_reply(chat["mentionText"], title),
            }
        label = fit_list_label(
            f"{title} - {chat['unread']} new"
            + (f" - {chat['mentions']} @you" if chat["mentions"] else "")
        )
        chats.append(
            {
                "id": chat["id"],
                "title": title,
                "unread": chat["unread"],
                "mentions": chat["mentions"],
                "label": label,
                "hasDraft": draft is not None,
            }
        )
        details[chat["id"]] = {
            "id": chat["id"],
            "title": title,
            "chunks": chunk_text(text),
            "mentionText": chat.get("mentionText"),
            "draft": draft,
        }
    return {"chats": chats, "details": details}
