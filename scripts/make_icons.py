"""Generate PWA / Apple Touch icons for Hand Control.

No third-party deps — writes PNGs using just the standard library.
Run once to regenerate:
    python3 scripts/make_icons.py
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path


def _chunk(type_bytes: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(type_bytes + data)
    return (
        struct.pack(">I", len(data))
        + type_bytes
        + data
        + struct.pack(">I", crc)
    )


def _png(size: int, pixels: bytes) -> bytes:
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)  # 8-bit RGBA
    idat = zlib.compress(pixels, 9)
    return signature + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


def _blend(fg: tuple[int, int, int], bg: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return tuple(int(fg[i] * t + bg[i] * (1 - t)) for i in range(3))  # type: ignore[return-value]


def make_icon(size: int, output: Path) -> None:
    bg = (10, 10, 10)          # #0a0a0a
    fg = (255, 77, 31)         # #ff4d1f  (accent)
    cx = cy = size / 2.0
    blob_r = size * 0.18
    ring_r = size * 0.40
    ring_w = max(2, size * 0.012)

    rows: list[bytes] = []
    for y in range(size):
        row = bytearray([0])   # PNG scanline filter byte
        for x in range(size):
            dx = x - cx
            dy = y - cy
            d = (dx * dx + dy * dy) ** 0.5

            # Central filled blob (antialiased edge)
            if d <= blob_r - 1:
                r, g, b = fg
                a = 255
            elif d <= blob_r + 1:
                t = max(0.0, min(1.0, (blob_r + 1 - d) / 2.0))
                r, g, b = _blend(fg, bg, t)
                a = 255
            # Outer pulse ring
            elif abs(d - ring_r) <= ring_w:
                edge = abs(d - ring_r) / ring_w   # 0 at center of ring, 1 at edge
                t = (1.0 - edge) * 0.55           # soft ring opacity
                r, g, b = _blend(fg, bg, t)
                a = 255
            else:
                r, g, b = bg
                a = 255
            row.extend([r, g, b, a])
        rows.append(bytes(row))

    output.write_bytes(_png(size, b"".join(rows)))
    print(f"wrote {output} ({size}x{size})")


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "phone"
    out.mkdir(exist_ok=True)
    # iOS Home Screen: apple-touch-icon is ideally 180x180
    make_icon(180, out / "icon-180.png")
    # PWA manifest: 192 and 512 are the minimum standard set
    make_icon(192, out / "icon-192.png")
    make_icon(512, out / "icon-512.png")


if __name__ == "__main__":
    main()
