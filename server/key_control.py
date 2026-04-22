"""Simulate keyboard events via Quartz (CoreGraphics)."""

from __future__ import annotations

from Quartz import (
    CGEventCreateKeyboardEvent,
    CGEventPost,
    CGEventSetFlags,
    kCGEventFlagMaskAlternate,
    kCGEventFlagMaskCommand,
    kCGHIDEventTap,
)

KEYCODE_RIGHT_OPTION = 61
KEYCODE_RETURN = 36
KEYCODE_Z = 6  # kVK_ANSI_Z


def _post(keycode: int, is_down: bool, flags: int = 0) -> None:
    event = CGEventCreateKeyboardEvent(None, keycode, is_down)
    if flags:
        CGEventSetFlags(event, flags)
    CGEventPost(kCGHIDEventTap, event)


def right_option_down() -> None:
    _post(KEYCODE_RIGHT_OPTION, True, flags=kCGEventFlagMaskAlternate)


def right_option_up() -> None:
    _post(KEYCODE_RIGHT_OPTION, False, flags=0)


def press_enter() -> None:
    _post(KEYCODE_RETURN, True)
    _post(KEYCODE_RETURN, False)


def press_cmd_z() -> None:
    """Simulate Cmd+Z to undo the last Wispr Flow insertion."""
    _post(KEYCODE_Z, True, flags=kCGEventFlagMaskCommand)
    _post(KEYCODE_Z, False, flags=kCGEventFlagMaskCommand)
