"""Accessibility (AX) snapshots of the currently focused text field.

Used so the phone can show:
    1. A warning when the user holds to talk but no text field is focused.
    2. A preview of exactly what Wispr Flow just transcribed, after the
       user releases.

Design
------
We use the *system-wide* AX element (not a per-app element). When we
``focus_window(...)`` on the Cursor window right before Wispr activates,
Cursor owns keyboard focus, so the system-wide "focused UI element"
resolves into Cursor's active text field.

Detecting "is this a text field?" is surprisingly nuanced for Electron
apps like Cursor. Their chat input is a web contenteditable rendered
inside a WebKit host, so the AX role can come back as anything from
``AXTextArea`` to ``AXGroup`` to nothing at all, depending on Cursor
and macOS versions. We cast a wide net (role, role-description, and
the presence of text-editor-specific AX attributes like
``AXInsertionPointLineNumber`` / ``AXSelectedText``) before declaring
"no text field focused."

Requires Accessibility permission granted to the process running this
server. When permission is missing we return an empty ``FocusSnapshot``
and the rest of the app still works; the phone just doesn't show the
transcription preview or focus warning.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional

try:
    from ApplicationServices import (
        AXUIElementCopyAttributeNames,
        AXUIElementCopyAttributeValue,
        AXUIElementCreateSystemWide,
        kAXFocusedUIElementAttribute,
        kAXRoleAttribute,
        kAXRoleDescriptionAttribute,
        kAXValueAttribute,
    )
    _AX_AVAILABLE = True
except Exception:
    _AX_AVAILABLE = False


# Explicit text-entry roles we recognize outright.
_TEXT_ROLES = {
    "AXTextField",
    "AXTextArea",
    "AXComboBox",
    "AXSearchField",
    "AXSecureTextField",
    # Some Electron / web hosts expose the whole content area as
    # the focused element; treat it as typable.
    "AXWebArea",
}

# AX attributes that only editable text elements expose. If any of
# these is in the focused element's attribute list, it's a text input
# even if its role is something weird like "AXGroup".
_TEXT_SIGNAL_ATTRS = {
    "AXInsertionPointLineNumber",
    "AXSelectedText",
    "AXSelectedTextRange",
    "AXNumberOfCharacters",
    "AXVisibleCharacterRange",
}

# Substrings we accept inside ``AXRoleDescription`` (case-insensitive).
# AX role descriptions are localized but English-speaking users see
# strings like "text field" / "text area" / "search text field" / "edit".
_TEXT_DESC_KEYWORDS = ("text", "edit", "input", "search")

# Toggle verbose focus logging via env var so users can debug
# "no text field focused" false negatives without rebuilding.
#
#     HC_DEBUG_AX=1 ./run.sh
_DEBUG = os.environ.get("HC_DEBUG_AX", "").strip() not in ("", "0", "false", "no")


@dataclass
class FocusSnapshot:
    text: Optional[str]        # current value of the focused text field
    role: Optional[str]        # AX role string, e.g. "AXTextArea"
    has_text_field: bool       # True if something text-shaped is focused

    @classmethod
    def empty(cls) -> "FocusSnapshot":
        return cls(text=None, role=None, has_text_field=False)


def _copy(element, attr: str):
    """``AXUIElementCopyAttributeValue`` wrapper returning just the
    value, or ``None`` on any error.
    """
    try:
        err, value = AXUIElementCopyAttributeValue(element, attr, None)
        if err != 0:
            return None
        return value
    except Exception:
        return None


def _attribute_names(element) -> List[str]:
    try:
        err, names = AXUIElementCopyAttributeNames(element, None)
        if err != 0 or names is None:
            return []
        return [str(n) for n in names]
    except Exception:
        return []


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
        if _DEBUG:
            print("[ax_focus] no focused element at all", flush=True)
        return FocusSnapshot.empty()

    role = _copy(focused, kAXRoleAttribute)
    role_str = str(role) if role is not None else None

    role_desc = _copy(focused, kAXRoleDescriptionAttribute)
    role_desc_str = str(role_desc).lower() if role_desc is not None else ""

    raw_value = _copy(focused, kAXValueAttribute)
    text = str(raw_value) if isinstance(raw_value, str) else None

    attr_names = _attribute_names(focused)
    attr_set = set(attr_names)

    # Multi-signal text-field detection. Any one of these is enough.
    has_text = False
    why = ""
    if role_str in _TEXT_ROLES:
        has_text = True
        why = f"role={role_str}"
    elif isinstance(raw_value, str):
        has_text = True
        why = "AXValue is string"
    elif attr_set & _TEXT_SIGNAL_ATTRS:
        has_text = True
        why = "has " + next(iter(attr_set & _TEXT_SIGNAL_ATTRS))
    elif any(k in role_desc_str for k in _TEXT_DESC_KEYWORDS):
        has_text = True
        why = f"role description={role_desc_str!r}"

    if _DEBUG:
        print(
            f"[ax_focus] role={role_str!r} "
            f"desc={role_desc_str!r} "
            f"value_type={type(raw_value).__name__} "
            f"attrs={attr_names} "
            f"→ has_text={has_text} ({why or 'no match'})",
            flush=True,
        )

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
