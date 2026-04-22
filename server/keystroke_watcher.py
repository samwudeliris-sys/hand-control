"""Global keystroke watcher using CGEventTap.

Tracks the timestamp of the most recent keydown event coming from *any*
source. Used to detect when Wispr Flow has finished typing its transcription
so we know when to fire Enter.

Requires Accessibility permission granted to the process running this
(Terminal.app, iTerm, Cursor, Python binary — whatever you launch from).
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
    CGEventKeyboardGetUnicodeString,
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
# Navigation / editing keys whose "characters" would pollute the
# captured transcription if we included them verbatim.
_NON_CHAR_KEYCODES = {
    _KEYCODE_RETURN,
    _KEYCODE_KEYPAD_ENTER,
    48,   # Tab
    51,   # Delete / Backspace
    53,   # Escape
    117,  # Forward delete
    123, 124, 125, 126,  # Arrow keys
}


class KeystrokeWatcher:
    """Maintain a monotonically updated ``last_keydown_ts`` timestamp and
    remember when the Return / Enter key was last pressed.

    The Return timestamp lets ``main.py`` detect when Wispr Flow's
    built-in *"press enter"* voice command fires, so we can tell the
    phone the message has already been submitted and skip the normal
    Submit / Delete confirmation flow.
    """

    def __init__(self) -> None:
        self._last_ts: float = 0.0
        self._last_return_ts: float = 0.0
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._tap = None
        self._started = False
        self.active: bool = False  # True once CGEventTap is running
        # Character-capture state. Callers start/stop capture around a
        # dictation window; everything typed in between accumulates in
        # ``_captured``. This lets us recover the transcription text
        # even when Wispr's "press enter" command clears the text field
        # before our AX poller can read it.
        self._capture_since: Optional[float] = None
        self._captured: list[str] = []

    @property
    def last_keydown_ts(self) -> float:
        with self._lock:
            return self._last_ts

    def saw_return_since(self, ts: float) -> bool:
        """True if Return / Enter was pressed after the given timestamp."""
        with self._lock:
            return self._last_return_ts > ts

    def start_capture(self, since_ts: float) -> None:
        """Begin accumulating typed characters from ``since_ts`` onward."""
        with self._lock:
            self._capture_since = since_ts
            self._captured = []

    def stop_capture(self) -> str:
        """Stop accumulating and return the captured text."""
        with self._lock:
            self._capture_since = None
            text = "".join(self._captured)
            self._captured = []
            return text

    def _extract_char(self, event) -> str:
        """Return the Unicode string produced by the given keydown event,
        respecting modifiers. Returns empty string for pure modifier/
        navigation keys that don't type anything visible.
        """
        try:
            # Returns (actualStringLength, unicodeString) — pyobjc turns
            # the C out-params into a tuple. The buffer comes back as
            # either a Python str or a tuple of ints (UniChar codepoints),
            # depending on pyobjc version.
            result = CGEventKeyboardGetUnicodeString(event, 16, None, None)
        except Exception:
            return ""
        if not result:
            return ""
        length = result[0] if len(result) >= 1 else 0
        chars = result[1] if len(result) >= 2 else None
        if not chars or length <= 0:
            return ""

        if isinstance(chars, str):
            s = chars[:length]
        else:
            try:
                s = "".join(
                    chr(c) if isinstance(c, int) else str(c)
                    for c in chars[:length]
                )
            except Exception:
                return ""
        # Filter out stray control characters that slip through
        # (\b, \x7f, etc.) while keeping regular printable Unicode.
        return "".join(c for c in s if c >= " " or c in ("\n", "\t"))

    def _callback(self, proxy, type_, event, refcon):
        now = time.monotonic()
        try:
            keycode = CGEventGetIntegerValueField(
                event, kCGKeyboardEventKeycode
            )
        except Exception:
            keycode = -1

        char = ""
        if keycode not in _NON_CHAR_KEYCODES:
            char = self._extract_char(event)

        with self._lock:
            self._last_ts = now
            if keycode in (_KEYCODE_RETURN, _KEYCODE_KEYPAD_ENTER):
                self._last_return_ts = now
            # Append typed characters only while a capture window is
            # open and only for events after the capture-start time.
            if (
                self._capture_since is not None
                and now >= self._capture_since
                and char
            ):
                self._captured.append(char)
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

        Two-phase behavior when the event tap is active:
            1. Wait up to `first_key_timeout_s` for the first keystroke
               after release (Wispr starting to type).
            2. Once it starts, wait until keystrokes go quiet for `idle_ms`.

        If the event tap isn't active (Accessibility not granted) or no
        keystroke ever arrives, fall back to a heuristic delay based on
        how long the hold lasted. This keeps things usable without
        Accessibility permission, at the cost of precision.
        """
        poll_s = poll_ms / 1000.0
        idle_s = idle_ms / 1000.0

        def _heuristic_fallback() -> None:
            # Wispr's transcription latency scales roughly with audio length.
            # Empirically: ~0.4s overhead + ~30% of hold duration, capped.
            extra = 0.4 + min(hold_duration_s * 0.3, 3.0)
            time.sleep(extra)

        if not self.active:
            _heuristic_fallback()
            return

        # Phase 1: wait for Wispr's first keystroke.
        # Allow more time for long dictations (server-side transcription
        # can take a while to start).
        first_deadline = release_ts + max(first_key_timeout_s, hold_duration_s * 0.6)
        while True:
            now = time.monotonic()
            if self.last_keydown_ts > release_ts:
                break
            if now > first_deadline:
                # No typing detected — either Wispr failed, or the tap
                # isn't actually seeing keystrokes. Use heuristic.
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
