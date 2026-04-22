"""Hand Control — Mac server.

Serves the phone UI and handles phone → Mac control events over WebSocket.

Control flow:
    phone hold_start
        → focus selected Cursor window
        → press-and-hold Right Option (Wispr Flow hotkey)

    phone hold_end
        → release Right Option
        → wait for Wispr to finish typing (CGEventTap keystroke watcher)
        → send "transcription_ready" to phone so it enables Submit / Delete

    phone submit        → press Option+Enter (Cursor's "queue message"
                          shortcut — message is appended after the current
                          agent run instead of interrupting it)
    phone delete        → press Cmd+Z (undo Wispr's last insertion)

    phone switch_prev / switch_next / select
        → update the server-side selected window index
        → focus that window immediately so user can see which one is active
"""

from __future__ import annotations

import asyncio
import json
import os
import platform
import socket
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional


def _fail_fast_if_wrong_platform() -> None:
    """Hand Control uses AppleScript, CoreGraphics, and CGEventTap — all
    macOS-only. Fail with a clear, friendly message if we're elsewhere,
    rather than letting the user hit a cryptic `ImportError` on pyobjc.
    """
    if platform.system() != "Darwin":
        sys.stderr.write(
            "\nHand Control only runs on macOS.\n"
            "It drives AppleScript, CoreGraphics, and CGEventTap, which are\n"
            f"Apple-only APIs. Current platform: {platform.system()}.\n\n"
        )
        sys.exit(1)


_fail_fast_if_wrong_platform()

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .ax_focus import FocusSnapshot, compute_transcription, read_focus
from .cursor_windows import CursorWindow, focus_window, list_windows
from .key_control import (
    press_cmd_z,
    press_enter,
    press_option_enter,
    right_option_down,
    right_option_up,
)
from .keystroke_watcher import KeystrokeWatcher

PHONE_DIR = Path(__file__).resolve().parent.parent / "phone"
POLL_INTERVAL_S = 1.0
ENTER_IDLE_MS = 400
ENTER_MAX_WAIT_S = 8.0

# Cursor keyboard behavior:
#   Enter         → submit (may interrupt current agent run)
#   Option+Enter  → queue message to run after current task finishes
#   Cmd+Enter     → "stop & send" (explicitly interrupt)
#
# Set to True to always queue. If the agent is idle, Option+Enter just
# submits normally, so this is the safe default for agent workflows.
QUEUE_INSTEAD_OF_INTERRUPT = True


def _sort_key(w: CursorWindow) -> tuple[str, str]:
    """Stable sort: alphabetical by project (then title) so box positions
    on the phone don't shuffle every time we focus a window."""
    return (w.project.lower(), w.title.lower())


class State:
    def __init__(self) -> None:
        self.windows: list[CursorWindow] = []
        # Track the selected window by title (identity), not index — macOS
        # reorders the window list whenever we focus something.
        self.selected_title: Optional[str] = None
        self.clients: set[WebSocket] = set()
        self.watcher = KeystrokeWatcher()
        self.lock = asyncio.Lock()
        self.hold_start_ts: Optional[float] = None
        self.baseline_focus: Optional[FocusSnapshot] = None

    def _selected_index(self) -> int:
        if not self.windows:
            return -1
        if self.selected_title is not None:
            for i, w in enumerate(self.windows):
                if w.title == self.selected_title:
                    return i
        return 0

    def selected_window(self) -> Optional[CursorWindow]:
        idx = self._selected_index()
        if idx < 0:
            return None
        return self.windows[idx]

    def to_payload(self) -> dict:
        return {
            "type": "state",
            "windows": [
                {"title": w.title, "project": w.project} for w in self.windows
            ],
            "selected": self._selected_index(),
        }


state = State()


async def broadcast(payload: dict) -> None:
    message = json.dumps(payload)
    dead: list[WebSocket] = []
    for client in state.clients:
        try:
            await client.send_text(message)
        except Exception:
            dead.append(client)
    for c in dead:
        state.clients.discard(c)


async def poll_windows() -> None:
    """Periodically refresh the list of open Cursor windows."""
    prev_key: tuple = ()
    while True:
        try:
            windows = list_windows()
        except Exception as exc:
            print(f"[poll_windows] error: {exc}")
            windows = []

        # Stable order so phone box positions don't shuffle as z-order changes.
        windows.sort(key=_sort_key)

        key = tuple((w.title, w.project) for w in windows)
        async with state.lock:
            if key != prev_key:
                state.windows = windows
                # If the previously selected window went away, fall back to
                # the first available. Otherwise the selection sticks with
                # the same window by title.
                titles = {w.title for w in windows}
                if state.selected_title not in titles:
                    state.selected_title = windows[0].title if windows else None
                prev_key = key
                print(
                    f"[windows] updated ({len(windows)}): "
                    + ", ".join(f"{i}={w.project}" for i, w in enumerate(windows))
                )
                await broadcast(state.to_payload())
        await asyncio.sleep(POLL_INTERVAL_S)


async def handle_hold_start() -> None:
    state.hold_start_ts = time.monotonic()
    win = state.selected_window()
    if win is not None:
        focus_window(win.title)
        # Give the WM a beat before pressing the modifier so focus has
        # actually settled before we start reading AX attributes.
        await asyncio.sleep(0.08)

    # Snapshot the currently focused text field. We'll diff against this
    # after Wispr finishes so the phone can show what got transcribed.
    state.baseline_focus = read_focus()
    await broadcast(
        {
            "type": "focus_status",
            "has_text_field": state.baseline_focus.has_text_field,
            "role": state.baseline_focus.role,
        }
    )

    right_option_down()


async def handle_hold_end() -> None:
    right_option_up()
    release_ts = time.monotonic()
    hold_duration = (
        release_ts - state.hold_start_ts if state.hold_start_ts else 0.0
    )
    # Block until Wispr has finished typing. Runs in a worker thread so we
    # don't stall the event loop.
    await asyncio.to_thread(
        state.watcher.wait_for_typing_to_settle,
        release_ts,
        hold_duration,
        ENTER_IDLE_MS,
        2.5,
        ENTER_MAX_WAIT_S,
    )

    # Snapshot the focused text field again, diff against the baseline
    # to recover exactly what Wispr typed. This is what the user sees
    # as the preview on their phone.
    final_focus = read_focus()
    baseline = state.baseline_focus or FocusSnapshot.empty()
    transcription = compute_transcription(baseline.text, final_focus.text)

    await broadcast(
        {
            "type": "transcription_ready",
            "text": transcription,
            "had_text_field": baseline.has_text_field and final_focus.has_text_field,
        }
    )


async def handle_submit() -> None:
    if QUEUE_INSTEAD_OF_INTERRUPT:
        press_option_enter()
    else:
        press_enter()


async def handle_delete() -> None:
    press_cmd_z()


async def handle_select(index: int) -> None:
    async with state.lock:
        if 0 <= index < len(state.windows):
            win = state.windows[index]
            state.selected_title = win.title
            await broadcast(state.to_payload())
        else:
            win = None
    if win is not None:
        focus_window(win.title)


async def handle_switch(delta: int) -> None:
    async with state.lock:
        if not state.windows:
            return
        current = state._selected_index()
        if current < 0:
            current = 0
        new_idx = (current + delta) % len(state.windows)
        win = state.windows[new_idx]
        state.selected_title = win.title
        print(
            f"[switch] delta={delta:+d} {current} -> {new_idx} "
            f"({win.project})"
        )
        await broadcast(state.to_payload())
    focus_window(win.title)


@asynccontextmanager
async def lifespan(_: FastAPI):
    state.watcher.start()
    task = asyncio.create_task(poll_windows())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def index() -> FileResponse:
    return FileResponse(PHONE_DIR / "index.html")


@app.get("/manifest.json")
async def manifest() -> FileResponse:
    return FileResponse(PHONE_DIR / "manifest.json", media_type="application/manifest+json")


@app.get("/apple-touch-icon.png")
async def apple_touch_icon() -> FileResponse:
    return FileResponse(PHONE_DIR / "icon-180.png", media_type="image/png")


@app.get("/apple-touch-icon-precomposed.png")
async def apple_touch_icon_precomposed() -> FileResponse:
    return FileResponse(PHONE_DIR / "icon-180.png", media_type="image/png")


@app.get("/icon-180.png")
async def icon_180() -> FileResponse:
    return FileResponse(PHONE_DIR / "icon-180.png", media_type="image/png")


@app.get("/icon-192.png")
async def icon_192() -> FileResponse:
    return FileResponse(PHONE_DIR / "icon-192.png", media_type="image/png")


@app.get("/icon-512.png")
async def icon_512() -> FileResponse:
    return FileResponse(PHONE_DIR / "icon-512.png", media_type="image/png")


@app.get("/favicon.ico")
async def favicon() -> FileResponse:
    return FileResponse(PHONE_DIR / "icon-192.png", media_type="image/png")


app.mount("/static", StaticFiles(directory=str(PHONE_DIR)), name="static")


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    state.clients.add(websocket)
    try:
        await websocket.send_text(json.dumps(state.to_payload()))
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue
            kind = msg.get("type")
            if kind == "hold_start":
                await handle_hold_start()
            elif kind == "hold_end":
                await handle_hold_end()
            elif kind == "submit":
                await handle_submit()
            elif kind == "delete":
                await handle_delete()
            elif kind == "switch_prev":
                await handle_switch(-1)
            elif kind == "switch_next":
                await handle_switch(+1)
            elif kind == "select":
                idx = msg.get("index")
                if isinstance(idx, int):
                    await handle_select(idx)
            elif kind == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[ws] error: {exc}")
    finally:
        state.clients.discard(websocket)
        # Safety: if the phone disconnects mid-hold, release the modifier.
        try:
            right_option_up()
        except Exception:
            pass


def get_lan_ip() -> str:
    """Best-effort LAN IP discovery."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_mdns_hostname() -> Optional[str]:
    """Return this Mac's Bonjour / mDNS hostname like "MyMac.local".

    This address is stable — it doesn't change when you switch Wi-Fi
    networks or your Mac gets a new DHCP lease — so it's ideal for
    bookmarking the phone UI as an app.
    """
    try:
        result = subprocess.run(
            ["scutil", "--get", "LocalHostName"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            name = result.stdout.strip()
            if name:
                return f"{name}.local"
    except Exception:
        pass
    return None


def _check_accessibility() -> bool:
    try:
        from ApplicationServices import AXIsProcessTrusted  # type: ignore
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def _resolve_port() -> int:
    raw = os.environ.get("PORT", "8000").strip()
    try:
        port = int(raw)
    except ValueError:
        sys.stderr.write(f"PORT must be a number, got: {raw!r}\n")
        sys.exit(1)
    if not (1 <= port <= 65535):
        sys.stderr.write(f"PORT out of range: {port}\n")
        sys.exit(1)
    return port


def _port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
        except OSError:
            return True
    return False


def main() -> None:
    import uvicorn

    port = _resolve_port()
    if _port_in_use(port):
        sys.stderr.write(
            f"\nPort {port} is already in use.\n"
            f"  • If Hand Control is already running, just use that instance.\n"
            f"  • Otherwise run on another port:  PORT=8080 ./run.sh\n\n"
        )
        sys.exit(1)

    ip = get_lan_ip()
    hostname = get_mdns_hostname()
    trusted = _check_accessibility()

    print("\n" + "=" * 64)
    print("  Hand Control running.")
    print()
    if hostname:
        print(f"  Phone URL (stable):  http://{hostname}:{port}")
        print(f"  Phone URL (by IP):   http://{ip}:{port}")
        print()
        print(f"  Bookmark the stable URL on your phone — the .local")
        print(f"  hostname won't change when your Wi-Fi does.")
    else:
        print(f"  Phone URL:  http://{ip}:{port}")
    print("=" * 64)
    if trusted:
        print("  Accessibility: OK (precise Enter timing enabled)")
    else:
        print("  Accessibility: NOT GRANTED")
        print("  → System Settings → Privacy & Security → Accessibility")
        print("    Enable your terminal app, then restart this server.")
        print("  Using hold-duration heuristic for Enter timing until then.")
    print("=" * 64 + "\n")

    try:
        uvicorn.run(
            "server.main:app",
            host="0.0.0.0",
            port=port,
            log_level="info",
        )
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
