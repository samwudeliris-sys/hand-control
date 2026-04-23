"""Mouse control — simulate cursor movement, clicks, and scrolling via
Quartz (CoreGraphics).

Used by the phone's trackpad mode: the phone sends relative cursor
deltas, taps, and scroll deltas; we translate them into real HID
mouse events on the Mac. Handy for clicking back into Cursor's chat
input before holding to talk, without walking back to the keyboard.
"""

from __future__ import annotations

import time

from Quartz import (
    CGEventCreate,
    CGEventCreateMouseEvent,
    CGEventCreateScrollWheelEvent,
    CGEventGetLocation,
    CGEventPost,
    kCGEventLeftMouseDown,
    kCGEventLeftMouseUp,
    kCGEventMouseMoved,
    kCGEventRightMouseDown,
    kCGEventRightMouseUp,
    kCGHIDEventTap,
    kCGMouseButtonLeft,
    kCGMouseButtonRight,
    kCGScrollEventUnitPixel,
)


def _current_position() -> tuple[float, float]:
    """Return the cursor's current (x, y) in global screen coords."""
    evt = CGEventCreate(None)
    pt = CGEventGetLocation(evt)
    return (pt.x, pt.y)


def mouse_move_by(dx: float, dy: float) -> None:
    """Move the cursor by ``(dx, dy)`` pixels, relative to its current
    position. Fires a single ``kCGEventMouseMoved`` event so hover
    states in apps update naturally.
    """
    x, y = _current_position()
    # pyobjc bridges a (x, y) tuple into a CGPoint for CG functions.
    evt = CGEventCreateMouseEvent(
        None, kCGEventMouseMoved, (x + dx, y + dy), 0
    )
    CGEventPost(kCGHIDEventTap, evt)


def mouse_click(button: str = "left") -> None:
    """Click at the cursor's current position.

    ``button`` is ``"left"`` (default) or ``"right"``. A single click
    is a down/up pair with a small gap so receiving apps register the
    event cleanly — bursts of events in the same tick can otherwise
    be coalesced.
    """
    pos = _current_position()
    if button == "right":
        down_t, up_t, btn = (
            kCGEventRightMouseDown,
            kCGEventRightMouseUp,
            kCGMouseButtonRight,
        )
    else:
        down_t, up_t, btn = (
            kCGEventLeftMouseDown,
            kCGEventLeftMouseUp,
            kCGMouseButtonLeft,
        )

    down = CGEventCreateMouseEvent(None, down_t, pos, btn)
    up = CGEventCreateMouseEvent(None, up_t, pos, btn)
    CGEventPost(kCGHIDEventTap, down)
    time.sleep(0.035)
    CGEventPost(kCGHIDEventTap, up)


def mouse_scroll(dy: float, dx: float = 0.0) -> None:
    """Scroll by ``(dx, dy)`` pixels.

    Sign convention matches a physical trackpad on macOS with
    "natural" scroll direction: positive ``dy`` scrolls content DOWN
    (like pushing your fingers up), negative scrolls UP. ``dx`` is
    horizontal; positive scrolls RIGHT.
    """
    # Sub-pixel deltas get dropped otherwise — round so small drags
    # still produce visible scrolling.
    idy = int(dy)
    idx = int(dx)
    if idy == 0 and idx == 0:
        return
    if idx != 0:
        # Two-axis scroll event.
        evt = CGEventCreateScrollWheelEvent(
            None, kCGScrollEventUnitPixel, 2, idy, idx
        )
    else:
        evt = CGEventCreateScrollWheelEvent(
            None, kCGScrollEventUnitPixel, 1, idy
        )
    CGEventPost(kCGHIDEventTap, evt)
