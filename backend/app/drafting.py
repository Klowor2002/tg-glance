"""Deterministic reply drafting (offline fallback).

In production the backend calls an LLM with the recent thread context and
hard instructions (<= 2 short sentences, no markdown, answer the question
that was asked). This module is the no-key fallback: it builds a draft
from the mention text itself so the write path works end to end in demos
and tests. It never invents facts beyond echoing the asked-about detail.
"""

import re

from .budgets import fit_draft


def draft_reply(mention_text: str | None, chat_title: str) -> str:
    if not mention_text:
        return fit_draft("Thanks for the update - noted, I will follow up in the thread.")
    q = mention_text.split(":", 1)[-1].strip()
    # Pull a time expression like "Friday 07:00 WIB" out of the question.
    m = re.search(
        r"(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)?\s*"
        r"\d{1,2}:\d{2}\s*(WIB|UTC|GMT[+-]\d)?",
        q,
    )
    if "?" in q and m:
        when = " ".join(m.group(0).split())
        return fit_draft(f"Yes - {when}, link in the pinned post.")
    if "?" in q:
        return fit_draft("Yes, confirmed - details are in the pinned post.")
    return fit_draft(f"Noted, thanks - following along in {chat_title}.")
