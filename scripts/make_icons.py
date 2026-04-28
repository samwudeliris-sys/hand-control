"""Generate PWA / Apple Touch icons for Blind Monkey.

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


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    if edge0 == edge1:
        return 1.0 if x >= edge1 else 0.0
    t = max(0.0, min(1.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def _ellipse_alpha(
    x: float,
    y: float,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    softness: float = 1.5,
) -> float:
    dx = (x - cx) / rx
    dy = (y - cy) / ry
    d = (dx * dx + dy * dy) ** 0.5
    return 1.0 - _smoothstep(1.0 - softness / max(rx, ry), 1.0, d)


def _line_alpha(
    x: float,
    y: float,
    ax: float,
    ay: float,
    bx: float,
    by: float,
    width: float,
) -> float:
    vx = bx - ax
    vy = by - ay
    length_sq = vx * vx + vy * vy
    if length_sq == 0:
        d = ((x - ax) ** 2 + (y - ay) ** 2) ** 0.5
    else:
        t = max(0.0, min(1.0, ((x - ax) * vx + (y - ay) * vy) / length_sq))
        px = ax + t * vx
        py = ay + t * vy
        d = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
    return 1.0 - _smoothstep(width * 0.5, width * 0.5 + 1.5, d)


def _arc_alpha(
    x: float,
    y: float,
    cx: float,
    cy: float,
    rx: float,
    ry: float,
    width: float,
    y_min: float,
) -> float:
    if y < y_min:
        return 0.0
    dx = (x - cx) / rx
    dy = (y - cy) / ry
    d = abs((dx * dx + dy * dy) ** 0.5 - 1.0) * max(rx, ry)
    return 1.0 - _smoothstep(width * 0.5, width * 0.5 + 1.3, d)


def _mix(
    base: tuple[int, int, int],
    top: tuple[int, int, int],
    alpha: float,
) -> tuple[int, int, int]:
    a = max(0.0, min(1.0, alpha))
    return tuple(int(base[i] * (1.0 - a) + top[i] * a) for i in range(3))  # type: ignore[return-value]


def make_icon(size: int, output: Path) -> None:
    bg = (10, 10, 10)
    glow = (255, 77, 31)
    fur = (123, 73, 39)
    fur_shadow = (82, 46, 28)
    face = (239, 174, 111)
    face_light = (255, 199, 135)
    ink = (21, 18, 17)
    lens = (4, 4, 5)
    gold = (245, 182, 66)
    blush = (255, 112, 82)
    cx = cy = size / 2.0

    rows: list[bytes] = []
    for y in range(size):
        row = bytearray([0])   # PNG scanline filter byte
        for x in range(size):
            px = x + 0.5
            py = y + 0.5
            color = bg

            # Accent halo keeps the icon tied to the Hand Control UI.
            halo = _ellipse_alpha(px, py, cx, cy, size * 0.43, size * 0.43, size * 0.018)
            color = _mix(color, _blend(glow, bg, 0.36), halo)

            left_ear = _ellipse_alpha(px, py, cx - size * 0.28, cy - size * 0.04, size * 0.17, size * 0.20)
            right_ear = _ellipse_alpha(px, py, cx + size * 0.28, cy - size * 0.04, size * 0.17, size * 0.20)
            head = _ellipse_alpha(px, py, cx, cy, size * 0.32, size * 0.36)
            color = _mix(color, fur_shadow, max(left_ear, right_ear) * 0.95)
            color = _mix(color, fur, head)

            left_inner = _ellipse_alpha(px, py, cx - size * 0.28, cy - size * 0.04, size * 0.09, size * 0.12)
            right_inner = _ellipse_alpha(px, py, cx + size * 0.28, cy - size * 0.04, size * 0.09, size * 0.12)
            color = _mix(color, face, max(left_inner, right_inner))

            brow = _ellipse_alpha(px, py, cx, cy - size * 0.09, size * 0.21, size * 0.20)
            muzzle = _ellipse_alpha(px, py, cx, cy + size * 0.13, size * 0.24, size * 0.18)
            color = _mix(color, face_light, max(brow, muzzle))

            cap = _ellipse_alpha(px, py, cx, cy - size * 0.275, size * 0.235, size * 0.090)
            brim = _ellipse_alpha(px, py, cx + size * 0.060, cy - size * 0.210, size * 0.180, size * 0.038)
            color = _mix(color, ink, max(cap, brim) * 0.95)

            left_lens = _ellipse_alpha(px, py, cx - size * 0.105, cy - size * 0.045, size * 0.063, size * 0.048)
            right_lens = _ellipse_alpha(px, py, cx + size * 0.105, cy - size * 0.045, size * 0.063, size * 0.048)
            bridge = _line_alpha(px, py, cx - size * 0.045, cy - size * 0.045, cx + size * 0.045, cy - size * 0.045, size * 0.018)
            color = _mix(color, lens, max(left_lens, right_lens, bridge))

            left_glint = _line_alpha(px, py, cx - size * 0.135, cy - size * 0.072, cx - size * 0.092, cy - size * 0.053, size * 0.010)
            right_glint = _line_alpha(px, py, cx + size * 0.075, cy - size * 0.072, cx + size * 0.118, cy - size * 0.053, size * 0.010)
            color = _mix(color, (255, 255, 255), max(left_glint, right_glint) * 0.55)

            nose = _ellipse_alpha(px, py, cx, cy + size * 0.065, size * 0.040, size * 0.027)
            color = _mix(color, ink, nose)

            mouth_l = _arc_alpha(px, py, cx - size * 0.047, cy + size * 0.088, size * 0.060, size * 0.064, size * 0.015, cy + size * 0.082)
            mouth_r = _arc_alpha(px, py, cx + size * 0.047, cy + size * 0.088, size * 0.060, size * 0.064, size * 0.015, cy + size * 0.082)
            mouth_mid = _line_alpha(px, py, cx, cy + size * 0.085, cx, cy + size * 0.120, size * 0.014)
            color = _mix(color, ink, max(mouth_l, mouth_r, mouth_mid))

            left_blush = _ellipse_alpha(px, py, cx - size * 0.155, cy + size * 0.105, size * 0.034, size * 0.020)
            right_blush = _ellipse_alpha(px, py, cx + size * 0.155, cy + size * 0.105, size * 0.034, size * 0.020)
            color = _mix(color, blush, max(left_blush, right_blush) * 0.35)

            chain = _arc_alpha(px, py, cx, cy + size * 0.245, size * 0.145, size * 0.070, size * 0.025, cy + size * 0.235)
            color = _mix(color, gold, chain)

            r, g, b = color
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
