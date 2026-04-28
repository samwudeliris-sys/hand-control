"""Paste text into whatever UI element is currently focused.

Why paste instead of synthesizing per-character Unicode keystrokes: on
Electron chat inputs (Cursor included) a long synthesized burst can
drop characters and runs visibly slow. A single ``Cmd+V`` appears
instantly and is always Unicode-clean.

We save the pasteboard's previous string contents before writing and
restore them after a short delay, so the user's clipboard isn't
clobbered by dictating. Non-string clipboard payloads (images, files)
are left alone — we only touch the string slot.
"""

from __future__ import annotations

import time

from AppKit import NSPasteboard, NSPasteboardTypeString  # type: ignore
from Quartz import (  # type: ignore
    CGEventCreateKeyboardEvent,
    CGEventPost,
    CGEventSetFlags,
    kCGEventFlagMaskCommand,
    kCGHIDEventTap,
)

KEYCODE_V = 9  # kVK_ANSI_V

# How long to wait between the paste and the clipboard restore. Cursor /
# Electron apps finish handling the paste well within a few ms but we
# give a comfortable buffer — the user can't type that fast anyway.
_RESTORE_DELAY_S = 0.25


def _press_cmd_v() -> None:
    down = CGEventCreateKeyboardEvent(None, KEYCODE_V, True)
    CGEventSetFlags(down, kCGEventFlagMaskCommand)
    CGEventPost(kCGHIDEventTap, down)

    up = CGEventCreateKeyboardEvent(None, KEYCODE_V, False)
    CGEventSetFlags(up, kCGEventFlagMaskCommand)
    CGEventPost(kCGHIDEventTap, up)


def paste_text(text: str) -> None:
    """Write ``text`` to the system clipboard, send Cmd+V, then restore
    the previous clipboard string after a short delay.

    Safe to call with an empty string — we simply no-op.
    """
    if not text:
        return

    pb = NSPasteboard.generalPasteboard()
    # ``stringForType_`` returns None if the pasteboard doesn't hold a
    # string (e.g. an image) — that's fine, we just won't restore.
    previous = pb.stringForType_(NSPasteboardTypeString)

    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)

    # Tiny beat so the pasteboard write is visible to the target app
    # before we fire Cmd+V. In practice 0ms works but a small sleep
    # eliminates the rare first-paste flake on heavily loaded systems.
    time.sleep(0.01)

    _press_cmd_v()

    if previous is not None:
        time.sleep(_RESTORE_DELAY_S)
        try:
            pb.clearContents()
            pb.setString_forType_(previous, NSPasteboardTypeString)
        except Exception:
            pass
