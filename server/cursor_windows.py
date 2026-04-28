"""List and focus Cursor IDE windows via AppleScript."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass


@dataclass
class CursorWindow:
    title: str   # normalized title, without the "●" unsaved-indicator
    project: str


# Last list_windows failure (for /health) — e.g. Automation denied to System Events.
_last_list_error: str | None = None


def last_list_error() -> str | None:
    return _last_list_error


# Primary bundle name on macOS; add aliases here if Cursor ever renames the process.
_APP_PROCESS_CANDIDATES: tuple[str, ...] = ("Cursor",)
# Filled in after the first successful window list so focus can hit the same process.
_resolved_process: str | None = None


def _osascript(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=3,
    )
    if result.returncode != 0:
        raise RuntimeError(f"osascript failed: {result.stderr.strip()}")
    return result.stdout.strip()


# Two occurrences of the literal Cursor — both are the app process name.
_BASE_LIST_SCRIPT = """
tell application "System Events"
    if not (exists process "Cursor") then return ""
    tell process "Cursor"
        set titles to {}
        repeat with w in windows
            set end of titles to name of w
        end repeat
        set AppleScript's text item delimiters to "\\n"
        return titles as string
    end tell
end tell
"""


def _list_script(process_name: str) -> str:
    if not re.match(r"^[\w. ()-]+$", process_name):
        process_name = "Cursor"
    safe = process_name.replace("\\", "\\\\").replace('"', '\\"')
    return _BASE_LIST_SCRIPT.replace("Cursor", safe, 2)


def _normalize(title: str) -> str:
    """Strip the '●' unsaved-file indicator and surrounding whitespace.

    Cursor toggles this prefix as files get modified/saved, so using raw
    titles as selection identity makes the selection jump around.
    """
    if not title:
        return ""
    # Strip any leading combination of bullet/dots and spaces
    return re.sub(r"^[●•·\s]+", "", title).strip()


def _extract_project(title: str) -> str:
    # Cursor window titles usually look like:
    #   "filename.ext — project-name"
    #   "project-name"
    # Project is after the last em-dash / en-dash / hyphen-with-spaces.
    if not title:
        return ""
    parts = re.split(r"\s[—–-]\s", title)
    project = parts[-1].strip() if parts else title.strip()
    return project or title


def list_windows() -> list[CursorWindow]:
    global _last_list_error, _resolved_process
    last_fail: str | None = None
    procs: tuple[str, ...]
    if _resolved_process and _resolved_process in _APP_PROCESS_CANDIDATES:
        procs = (_resolved_process,) + tuple(
            p for p in _APP_PROCESS_CANDIDATES if p != _resolved_process
        )
    else:
        procs = _APP_PROCESS_CANDIDATES
    for proc in procs:
        try:
            raw = _osascript(_list_script(proc))
        except Exception as exc:
            last_fail = str(exc)[:500]
            continue
        if not raw:
            continue
        _last_list_error = None
        _resolved_process = proc
        windows: list[CursorWindow] = []
        seen = set()
        for line in raw.splitlines():
            title = _normalize(line.strip())
            if not title or title in seen:
                continue
            seen.add(title)
            windows.append(CursorWindow(title=title, project=_extract_project(title)))
        return windows
    _last_list_error = last_fail
    return []


def _focus_script(process_name: str, escaped_title: str) -> str:
    sp = process_name.replace("\\", "\\\\").replace('"', '\\"')
    return f"""
    tell application "System Events"
        if not (exists process "{sp}") then return "miss"
        tell process "{sp}"
            set frontmost to true
            set target to "{escaped_title}"
            repeat with w in every window
                set wName to name of w
                set normalized to wName
                repeat while normalized starts with "●" or normalized starts with "•" or normalized starts with " "
                    set normalized to text 2 thru -1 of normalized
                end repeat
                if normalized is equal to target then
                    perform action "AXRaise" of w
                    return "ok"
                end if
            end repeat
            return "miss"
        end tell
    end tell
    """


def focus_window(title: str) -> bool:
    """Raise a specific Cursor window to the front.

    Accepts a normalized title (no '●' prefix) and finds the matching
    window regardless of whether its actual title currently has the
    dirty-file indicator or not.
    """
    escaped = title.replace('"', '\\"')
    procs: tuple[str, ...]
    if _resolved_process and _resolved_process in _APP_PROCESS_CANDIDATES:
        procs = (_resolved_process,) + tuple(
            p for p in _APP_PROCESS_CANDIDATES if p != _resolved_process
        )
    else:
        procs = _APP_PROCESS_CANDIDATES
    for proc in procs:
        if not re.match(r"^[\w. ()-]+$", proc):
            continue
        try:
            out = _osascript(_focus_script(proc, escaped))
            if out == "ok":
                return True
        except Exception:
            continue
    return False
