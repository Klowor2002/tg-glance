"""TG Glance backend.

One public origin for the G2 app (whitelisted in app.json). Endpoints:

  POST /v1/pair/start            -> {session, code, expiresInSec}
  GET  /v1/pair/status?session=  -> {paired:false} | {paired:true, token, accountLabel}
  POST /v1/pair/confirm          -> demo-only stand-in for "user sent the code
                                      in Telegram" (rejected when TELEGRAM_LIVE=1;
                                      the Telethon listener confirms for real)
  GET  /v1/digest                -> ranked chat list (Bearer)
  GET  /v1/chat/{id}             -> digest chunks + pending draft (Bearer)
  POST /v1/reply/send            -> {draft_id} sends (throttled; outbox in demo)
  POST /v1/reply/redraft         -> {chat_id, style} -> {text}

Nothing sends without an explicit tap-driven request from the app.
"""

import asyncio
import json
import os
import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import demo
from .drafting import draft_reply
from .telegram_engine import TelegramEngine

app = FastAPI(title="TG Glance backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = TelegramEngine()
OUTBOX = Path(__file__).resolve().parent.parent / "outbox.jsonl"

_pairs: dict[str, dict] = {}  # session -> {code, token|None, created}
_tokens: dict[str, str] = {}  # token -> account label
_send_times: list[float] = []
SEND_MIN_INTERVAL = 5.0
SEND_HOURLY_CAP = 20


@app.on_event("startup")
async def _startup() -> None:
    engine.on_paired = _bind_pair
    await engine.start()


def _bind_pair(session: str) -> None:
    rec = _pairs.get(session)
    if rec and not rec.get("token"):
        token = secrets.token_urlsafe(24)
        rec["token"] = token
        _tokens[token] = "@Kingklwr"


def _auth(authorization: str = Header(default="")) -> str:
    token = authorization.removeprefix("Bearer ").strip()
    if token not in _tokens:
        raise HTTPException(401, "not paired")
    return token


def _snapshot() -> dict:
    # Live provider lands here during the build window; the demo provider
    # already runs the same budget pipeline over raw snapshot data.
    return demo.load_snapshot()


class ConfirmBody(BaseModel):
    code: str


class SendBody(BaseModel):
    draft_id: str


class RedraftBody(BaseModel):
    chat_id: str
    style: str = "fresh"


@app.get("/healthz")
async def healthz() -> dict:
    return {"ok": True, "telegram_live": engine.live, "send_enabled": engine.send_enabled}


@app.post("/v1/pair/start")
async def pair_start() -> dict:
    session = secrets.token_urlsafe(12)
    code = f"{secrets.randbelow(900) + 100} {secrets.randbelow(900) + 100}"
    _pairs[session] = {"code": code, "token": None, "created": time.time()}
    engine.watch_pair_code(code, session)
    print(f"[pair] issued code {code} for session {session} (dev log only)", flush=True)
    return {"session": session, "code": code, "expiresInSec": 600}


@app.get("/v1/pair/status")
async def pair_status(session: str) -> dict:
    rec = _pairs.get(session)
    if not rec:
        raise HTTPException(404, "unknown session")
    if rec.get("token"):
        return {
            "paired": True,
            "token": rec["token"],
            "accountLabel": _tokens[rec["token"]],
        }
    return {"paired": False}


@app.post("/v1/pair/confirm")
async def pair_confirm(body: ConfirmBody) -> dict:
    if engine.live:
        raise HTTPException(403, "pairing completes via Telegram when live")
    for session, rec in _pairs.items():
        if rec["code"] == body.code and not rec.get("token"):
            _bind_pair(session)
            return {"ok": True}
    raise HTTPException(404, "code not recognised")


@app.get("/v1/digest")
async def digest(_: str = Depends(_auth)) -> dict:
    snap = _snapshot()
    return {"generatedAt": "now", "chats": snap["chats"]}


@app.get("/v1/chat/{chat_id}")
async def chat(chat_id: str, _: str = Depends(_auth)) -> dict:
    snap = _snapshot()
    detail = snap["details"].get(chat_id)
    if not detail:
        raise HTTPException(404, "unknown chat")
    return detail


@app.post("/v1/reply/send")
async def reply_send(body: SendBody, _: str = Depends(_auth)) -> dict:
    now = time.time()
    recent = [t for t in _send_times if now - t < 3600]
    if recent and now - recent[-1] < SEND_MIN_INTERVAL:
        raise HTTPException(429, "send throttled: too fast")
    if len(recent) >= SEND_HOURLY_CAP:
        raise HTTPException(429, "send throttled: hourly cap")
    snap = _snapshot()
    target = None
    for detail in snap["details"].values():
        if detail.get("draft") and detail["draft"]["id"] == body.draft_id:
            target = detail
            break
    if not target:
        raise HTTPException(404, "unknown draft")
    text = target["draft"]["text"]
    if engine.send_enabled:
        await engine.send(target["id"], text)
        detail_out = "sent via telegram"
    else:
        with OUTBOX.open("a") as f:
            f.write(json.dumps({"ts": now, "chat": target["id"], "text": text}) + "\n")
        detail_out = "recorded to outbox (send disabled)"
    _send_times.append(now)
    return {"ok": True, "detail": detail_out}


@app.post("/v1/reply/redraft")
async def reply_redraft(body: RedraftBody, _: str = Depends(_auth)) -> dict:
    snap = _snapshot()
    detail = snap["details"].get(body.chat_id)
    if not detail:
        raise HTTPException(404, "unknown chat")
    text = draft_reply(detail.get("mentionText"), detail["title"])
    if body.style == "shorter" and len(text) > 60:
        text = text[:57].rstrip() + "…"
    return {"text": text}
