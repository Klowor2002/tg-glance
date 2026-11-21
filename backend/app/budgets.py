"""Copy budgets for the G2 display, enforced server-side.

The glasses show one list of <= 20 items at <= 64 chars each, and text
pages of roughly 400-500 visible characters. Every string the backend
serves is fitted here, never in the app and never by eyeballing prompts.
"""

LIST_MAX_ITEMS = 20
LIST_ITEM_MAX = 64
CHUNK_MAX = 450


def fit_list_label(text: str) -> str:
    text = " ".join(text.split())
    if len(text) <= LIST_ITEM_MAX:
        return text
    return text[: LIST_ITEM_MAX - 1].rstrip() + "…"


def chunk_text(text: str, limit: int = CHUNK_MAX) -> list[str]:
    """Split text into pages of at most `limit` chars on line boundaries."""
    lines = [ln.rstrip() for ln in text.strip().split("\n")]
    chunks: list[str] = []
    cur: list[str] = []
    size = 0
    for ln in lines:
        add = len(ln) + (1 if cur else 0)
        if cur and size + add > limit:
            chunks.append("\n".join(cur))
            cur, size = [ln], len(ln)
        else:
            cur.append(ln)
            size += add
    if cur:
        chunks.append("\n".join(cur))
    return chunks


def fit_draft(text: str, limit: int = 200) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
