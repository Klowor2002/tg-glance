#!/usr/bin/env python3
"""Convert simulator framebuffer PNGs to watchable images.

The simulator's /api/screenshot/glasses returns the raw LVGL framebuffer:
RGB is constant green and the brightness lives in the alpha channel
(background alpha 0, glyphs alpha 255). Naive viewers show a solid green
rectangle. This maps alpha -> green brightness on black, which is how
the frame actually looks on the G2 display. Used for demo-video frames.

Usage: python3 scripts/shot_convert.py shots/03-digest.png [out.png]
"""

import struct
import sys
import zlib
from pathlib import Path


def decode_rgba(png: bytes) -> tuple[int, int, bytearray]:
    pos = 8
    idat = b""
    w = h = 0
    while pos < len(png):
        ln = struct.unpack(">I", png[pos : pos + 4])[0]
        ct = png[pos + 4 : pos + 8]
        d = png[pos + 8 : pos + 8 + ln]
        if ct == b"IHDR":
            w, h = struct.unpack(">II", d[:8])
        elif ct == b"IDAT":
            idat += d
        pos += 12 + ln
    raw = zlib.decompress(idat)
    bpp = 4
    stride = w * bpp + 1
    out = bytearray(w * h * bpp)
    prev = bytearray(w * bpp)
    for y in range(h):
        row = bytearray(raw[y * stride + 1 : (y + 1) * stride])
        f = raw[y * stride]
        if f == 1:
            for i in range(bpp, len(row)):
                row[i] = (row[i] + row[i - bpp]) & 0xFF
        elif f == 2:
            for i in range(len(row)):
                row[i] = (row[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(len(row)):
                a = row[i - bpp] if i >= bpp else 0
                row[i] = (row[i] + (a + prev[i]) // 2) & 0xFF
        elif f == 4:
            for i in range(len(row)):
                a = row[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                row[i] = (row[i] + pr) & 0xFF
        out[y * w * bpp : (y + 1) * w * bpp] = row
        prev = row
    return w, h, out


def encode_png(w: int, h: int, rgba: bytearray) -> bytes:
    raw = b"".join(
        b"\x00" + bytes(rgba[y * w * 4 : (y + 1) * w * 4]) for y in range(h)
    )

    def chunk(t: bytes, d: bytes) -> bytes:
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw))
    png += chunk(b"IEND", b"")
    return png


def main() -> None:
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".view.png")
    w, h, px = decode_rgba(src.read_bytes())
    for i in range(0, len(px), 4):
        a = px[i + 3]
        px[i] = 0
        px[i + 1] = a  # brightness -> green channel
        px[i + 2] = int(a * 0.25)
        px[i + 3] = 255
    dst.write_bytes(encode_png(w, h, px))
    print(f"wrote {dst}")


if __name__ == "__main__":
    main()
