"""Global keystroke watcher using CGEventTap.

Tracks the timestamp of the most recent keydown event so we can tell
when Wispr Flow has finished typing, and specifically whether the
Return / Enter key was pressed (which signals Wispr's built-in
"press enter" voice command has already submitted the message).

Requires Accessibility permission granted to whatever binary launched
this server (Terminal.app, iTerm, Cursor, etc.).
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from Quartz import (
    CFMachPortCreateRunLoopSource,
    CFRunLoopAddSource,
    CFRunLoopGetCurrent,
    CFRunLoopRun,
    CGEventGetIntegerValueField,
    CGEventMaskBit,
    CGEventTapCreate,
    CGEventTapEnable,
    kCFRunLoopCommonModes,
    kCGEventKeyDown,
    kCGEventTapOptionListenOnly,
    kCGHeadInsertEventTap,
    kCGKeyboardEventKeycode,
    kCGSessionEventTap,
)

# macOS virtual keycode for the Return / Enter key on the main keyboard.
_KEYCODE_RETURN = 36
# Numeric keypad Enter — some apps / dictation tools use this variant.
_KEYCODE_KEYPAD_ENTER = 76


class KeystrokeWatcher:
    """Maintain the timestamp of the most recent keydown event and of the
    most recent Return / Enter press.

    ``main.py`` uses these to:
        - Wait for Wispr Flow's typing to quiet down before enabling
          the Submit / Delete buttons on the phone.
        - Detect when Wispr's built-in "press enter" voice command
          fires, so the phone can show a "Sent" confirmation and skip
          the normal confirmation flow.
    """

    def __init__(self) -> None:
        self._last_ts: float = 0.0
        self._last_return_ts: float = 0.0
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._tap = None
        self._started = False
        self.active: bool = False  # True once CGEventTap is running

    @property
    def last_keydown_ts(self) -> float:
        with self._lock:
            return self._last_ts

    def saw_return_since(self, ts: float) -> bool:
        """True if Return / Enter was pressed after the given timestamp."""
        with self._lock:
            return self._last_return_ts > ts

    def _callback(self, proxy, type_, event, refcon):
        now = time.monotonic()
        try:
            keycode = CGEventGetIntegerValueField(
                event, kCGKeyboardEventKeycode
            )
        except Exception:
            keycode = -1
        with self._lock:
            self._last_ts = now
            if keycode in (_KEYCODE_RETURN, _KEYCODE_KEYPAD_ENTER):
                self._last_return_ts = now
        return event

    def _run(self) -> None:
        mask = CGEventMaskBit(kCGEventKeyDown)
        self._tap = CGEventTapCreate(
            kCGSessionEventTap,
            kCGHeadInsertEventTap,
            kCGEventTapOptionListenOnly,
            mask,
            self._callback,
            None,
        )
        if not self._tap:
            # Most likely: Accessibility permission not granted.
            print(
                "[keystroke_watcher] Failed to create event tap. "
                "Enter-timing will use a heuristic fallback based on hold "
                "duration. Grant Accessibility permission to your terminal "
                "in System Settings → Privacy & Security → Accessibility, "
                "then restart the server for precise Enter timing."
            )
            return
        source = CFMachPortCreateRunLoopSource(None, self._tap, 0)
        CFRunLoopAddSource(CFRunLoopGetCurrent(), source, kCFRunLoopCommonModes)
        CGEventTapEnable(self._tap, True)
        self.active = True
        CFRunLoopRun()

    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def wait_for_typing_to_settle(
        self,
        release_ts: float,
        hold_duration_s: float,
        idle_ms: int = 400,
        first_key_timeout_s: float = 2.5,
        max_wait_s: float = 10.0,
        poll_ms: int = 50,
    ) -> None:
        """Block until Wispr Flow has finished typing, then return.

        Two-phase behavior when the event tap is active and Wispr is
        synthesizing real keydowns:
            1. Wait up to ``first_key_timeout_s`` for the first keystroke
               after release.
            2. Once it arrives, wait until keystrokes go quiet for
               ``idle_ms``.

        Electron apps (Cursor, VSCode) sometimes receive dictated text
        through a channel that *doesn't* generate keydown events we can
        see. When that happens, or when the tap isn't running at all,
        we fall back to a heuristic delay scaled to the hold duration.
        The result: the phone's Submit / Delete buttons appear a little
        less precisely, but they still appear at a reasonable moment.
        """
        poll_s = poll_ms / 1000.0
        idle_s = idle_ms / 1000.0

        def _heuristic_fallback() -> None:
            # ~0.4s baseline + 30% of hold duration, capped — gives
            # short utterances a snappy response and long ones time
            # for transcription to finish.
            extra = 0.4 + min(hold_duration_s * 0.3, 3.0)
            time.sleep(extra)

        if not self.active:
            _heuristic_fallback()
            return

        # Phase 1: wait for Wispr's first keystroke.
        first_deadline = release_ts + max(first_key_timeout_s, hold_duration_s * 0.6)
        while True:
            now = time.monotonic()
            if self.last_keydown_ts > release_ts:
                break
            if now > first_deadline:
                # No typing detected — either Wispr used a non-keystroke
                # input path (common in Cursor) or it just never fired.
                # Fall back to heuristic timing.
                _heuristic_fallback()
                return
            time.sleep(poll_s)

        # Phase 2: wait for typing to go quiet.
        hard_deadline = release_ts + max_wait_s
        while True:
            now = time.monotonic()
            if now > hard_deadline:
                return
            if now - self.last_keydown_ts >= idle_s:
                return
            time.sleep(poll_s)
