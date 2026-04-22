"""Accessibility (AX) snapshots of the currently focused text field.

Used so the phone can show:
    1. A warning when the user holds to talk but no text field is focused.
    2. A preview of exactly what Wispr Flow just transcribed, after the
       user releases.

Design
------
We use the *system-wide* AX element (not a per-app element). When we
`focus_window(...)` on the Cursor window right before Wispr activates,
Cursor owns keyboard focus, so the system-wide "focused UI element"
resolves into Cursor's active text field.

Requires Accessibility permission granted to the process running this
server (Terminal.app, iTerm, etc.). If permission is missing or the
focused element isn't a text field, functions return a best-effort
``FocusSnapshot`` with ``has_text_field=False`` — callers use this to
tell the phone "no text detected" rather than silently doing nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

try:
    from ApplicationServices import (
        AXUIElementCopyAttributeValue,
        AXUIElementCreateSystemWide,
        kAXFocusedUIElementAttribute,
        kAXRoleAttribute,
        kAXValueAttribute,
    )
    _AX_AVAILABLE = True
except Exception:
    _AX_AVAILABLE = False


# Roles that "count" as a text-entry field. Electron apps (Cursor is one)
# often expose web inputs as AXTextArea / AXTextField thanks to the
# WebKit bridge, so the standard list is usually enough.
_TEXT_ROLES = {
    "AXTextField",
    "AXTextArea",
    "AXComboBox",
    "AXSearchField",
    "AXSecureTextField",
}


@dataclass
class FocusSnapshot:
    text: Optional[str]        # current value of the focused text field
    role: Optional[str]        # AX role string, e.g. "AXTextArea"
    has_text_field: bool       # True if something text-shaped is focused

    @classmethod
    def empty(cls) -> "FocusSnapshot":
        return cls(text=None, role=None, has_text_field=False)


def _copy(element, attr: str):
    """Wrapper around AXUIElementCopyAttributeValue that returns just
    the value (or None on any error)."""
    try:
        err, value = AXUIElementCopyAttributeValue(element, attr, None)
        if err != 0:
            return None
        return value
    except Exception:
        return None


def read_focus() -> FocusSnapshot:
    """Snapshot the system-wide focused UI element's text value + role."""
    if not _AX_AVAILABLE:
        return FocusSnapshot.empty()
    try:
        system = AXUIElementCreateSystemWide()
    except Exception:
        return FocusSnapshot.empty()

    focused = _copy(system, kAXFocusedUIElementAttribute)
    if focused is None:
        return FocusSnapshot.empty()

    role = _copy(focused, kAXRoleAttribute)
    role_str = str(role) if role is not None else None

    raw_value = _copy(focused, kAXValueAttribute)
    text = str(raw_value) if isinstance(raw_value, str) else None

    # A field "counts" as a text input if either
    #   (a) its role looks like a text role, OR
    #   (b) it exposes a readable string value.
    # (b) catches Electron / WebKit inputs whose role is sometimes
    # reported as AXGroup / AXWebArea even though they accept typing.
    has_text = (role_str in _TEXT_ROLES) or isinstance(raw_value, str)

    return FocusSnapshot(text=text, role=role_str, has_text_field=has_text)


def compute_transcription(baseline: Optional[str], final: Optional[str]) -> str:
    """Return the text Wispr just typed, given snapshots before and
    after dictation.

    Strategy:
      • If we don't have both snapshots, return "".
      • If ``final`` ends with ``baseline`` unchanged up to some prefix
        plus appended content, return the appended content. This is
        the common case — the cursor was at end of line / beginning of
        an empty field and Wispr appended.
      • Otherwise, find the longest common prefix and longest common
        suffix and return what's in the middle. This handles cursor
        positions in the middle of existing text.
    """
    if baseline is None or final is None:
        return ""
    if baseline == final:
        return ""

    # Fast path: Wispr just appended.
    if final.startswith(baseline):
        return final[len(baseline):].strip()

    # Fast path: Wispr just replaced a fully-selected field.
    if baseline == "":
        return final.strip()

    # General case: diff prefix + suffix.
    n = min(len(baseline), len(final))
    common_prefix = 0
    while common_prefix < n and baseline[common_prefix] == final[common_prefix]:
        common_prefix += 1

    common_suffix = 0
    while (
        common_suffix < n - common_prefix
        and baseline[len(baseline) - 1 - common_suffix]
        == final[len(final) - 1 - common_suffix]
    ):
        common_suffix += 1

    inserted = final[common_prefix : len(final) - common_suffix]
    return inserted.strip()
