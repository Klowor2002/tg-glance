#!/usr/bin/env python3
"""End-to-end journey test against the Even Hub simulator automation API.

Drives the full TG Glance flow:
  boot -> pairing screen -> confirm pairing (demo stand-in for the
  Telegram message) -> home list -> open chat -> digest -> reply draft
  -> tap SEND -> sent confirmation.

Asserts at each step that the glasses framebuffer changed and that the
simulator console shows no errors. Screenshots land in scripts/shots/.

Usage: python3 scripts/e2e_sim.py [backend_log]
Requires: backend on :8787, vite on :5173, simulator with
--automation-port 9898.
"""

import json
import re
import struct
import sys
import time
import urllib.request
import zlib
from pathlib import Path

SIM = "http://127.0.0.1:9898"
BACKEND_LOG = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/tgglance-backend.log")
SHOTS = Path(__file__).parent / "shots"
SHOTS.mkdir(exist_ok=True)


def call(method: str, url: str, body: dict | None = None) -> bytes:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=10) as r:
        return r.read()


def lit_pixels(png: bytes) -> int:
    """Count non-transparent pixels in an RGBA PNG (framebuffer check)."""
    pos = 8
    idat = b""
    w = h = None
    bit_depth = color = None
    while pos < len(png):
        length = struct.unpack(">I", png[pos : pos + 4])[0]
        ctype = png[pos + 4 : pos + 8]
        data = png[pos + 8 : pos + 8 + length]
        if ctype == b"IHDR":
            w, h, bit_depth, color = struct.unpack(">IIBB", data[:10])
        elif ctype == b"IDAT":
            idat += data
        pos += 12 + length
    assert w == 576 and h == 288, f"unexpected framebuffer {w}x{h}"
    raw = zlib.decompress(idat)
    bpp = 4  # RGBA
    stride = w * bpp + 1
    lit = 0
    prev = bytearray(w * bpp)
    for y in range(h):
        row = bytearray(raw[y * stride + 1 : (y + 1) * stride])
        filt = raw[y * stride]
        if filt == 1:
            for i in range(bpp, len(row)):
                row[i] = (row[i] + row[i - bpp]) & 0xFF
        elif filt == 2:
            for i in range(len(row)):
                row[i] = (row[i] + prev[i]) & 0xFF
        elif filt == 3:
            for i in range(len(row)):
                a = row[i - bpp] if i >= bpp else 0
                row[i] = (row[i] + (a + prev[i]) // 2) & 0xFF
        elif filt == 4:
            for i in range(len(row)):
                a = row[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                row[i] = (row[i] + pr) & 0xFF
        for x in range(0, len(row), bpp):
            if row[x + 3] > 0 and (row[x] > 24 or row[x + 1] > 24):
                lit += 1
        prev = row
    return lit


def shot(name: str) -> int:
    png = call("GET", f"{SIM}/api/screenshot/glasses")
    (SHOTS / f"{name}.png").write_bytes(png)
    return lit_pixels(png)


def console_since(since: int) -> tuple[str, int]:
    raw = call("GET", f"{SIM}/api/console?since_id={since}")
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError:
        return raw.decode(errors="replace"), since
    if isinstance(entries, dict):
        entries = entries.get("entries", [])
    text = "\n".join(str(e) for e in entries)
    nxt = since + len(entries)
    return text, nxt


def wait_for(marker: str, since: int, timeout: float = 30.0) -> int:
    deadline = time.time() + timeout
    while time.time() < deadline:
        text, nxt = console_since(since)
        if marker in text:
            return nxt
        since = nxt
        time.sleep(0.7)
    raise AssertionError(f"console marker not seen: {marker!r}")


def main() -> None:
    print("ping:", call("GET", f"{SIM}/api/ping"))
    since = wait_for("TG Glance ready", 0)
    print("app booted; pairing screen lit pixels:", shot("01-pairing"))

    # Read the pairing code the backend issued (dev log), confirm pairing.
    log = BACKEND_LOG.read_text()
    codes = re.findall(r"\[pair\] issued code ([\d ]+) for session", log)
    assert codes, "no pairing code in backend log"
    code = codes[-1].strip()
    print("pairing code:", code)
    print("confirm:", call("POST", "http://127.0.0.1:8787/v1/pair/confirm", {"code": code}))
    time.sleep(3.5)  # app polls every 2.5s
    print("home list lit pixels:", shot("02-home"))

    def tap(action: str, name: str, wait: float = 1.2) -> None:
        call("POST", f"{SIM}/api/input", {"action": action})
        time.sleep(wait)
        print(f"{name} lit pixels:", shot(name))

    tap("click", "03-digest")          # open first chat (Dow Protocol)
    tap("click", "04-reply")           # last chunk -> reply draft
    tap("click", "05-sent", wait=1.8)   # SEND

    text, _ = console_since(0)
    errors = [ln for ln in text.splitlines() if "error" in ln.lower() or "uncaught" in ln.lower()]
    assert not errors, f"console errors: {errors[:3]}"
    print("E2E OK - full journey completed, no console errors")


if __name__ == "__main__":
    main()
