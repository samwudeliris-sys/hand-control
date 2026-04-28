"""Blind Monkey — Mac server.

Serves the phone UI and handles phone → Mac control events over WebSocket.

Control flow (audio is phone mic → OpenAI Whisper, not the Mac’s mic):

    phone hold_start   → focus selected Cursor window, clear audio buffer
    phone hold_end     → transcribe audio via Whisper, push final_transcript
    phone submit       → paste + Option+Enter (queue) or Enter (send)
    phone delete       → Cmd+Z (Mac) / peer delete (PC)
    switch / select     → refocus the chosen Cursor window
    mouse_move / click / scroll → synthetic HID events (requires Accessibility
                          for the **Python** process that runs this server)
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
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def _fail_fast_if_wrong_platform() -> None:
    """Hand Control uses AppleScript, CoreGraphics, and CGEventTap — all
    macOS-only. Fail with a clear, friendly message if we're elsewhere,
    rather than letting the user hit a cryptic `ImportError` on pyobjc.
    """
    if platform.system() != "Darwin":
        sys.stderr.write(
            "\nBlind Monkey only runs on macOS.\n"
            "It drives AppleScript, CoreGraphics, and CGEventTap, which are\n"
            f"Apple-only APIs. Current platform: {platform.system()}.\n\n"
        )
        sys.exit(1)


_fail_fast_if_wrong_platform()

# Make stdout / stderr line-buffered so our diagnostic prints (startup
# banner, debug logs, etc.) appear immediately even when the server is
# launched via a wrapper that pipes stdout into a file or terminal tail.
try:
    sys.stdout.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
    sys.stderr.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
except Exception:
    pass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

# Used for primary-display size + cursor warp. These live in Quartz
# on modern pyobjc, but some shells expose them through different
# submodules — import them best-effort so a stub install doesn't
# take down the whole server.
try:
    from Quartz import (
        CGDisplayBounds,
        CGMainDisplayID,
        CGWarpMouseCursorPosition,
    )
    _QUARTZ_DISPLAY_OK = True
except Exception:  # pragma: no cover
    _QUARTZ_DISPLAY_OK = False

from .certs import ensure_cert, get_tailscale_sans
from .clipboard import paste_text
from .cursor_windows import (
    CursorWindow,
    focus_window,
    last_list_error,
    list_windows,
)
from .mouse_control import mouse_click, mouse_move_by, mouse_scroll
from .key_control import (
    press_cmd_z,
    press_enter,
    press_option_enter,
    type_string,
)
from .peer import Peer, PeerWindow
from .presets import Preset, load_presets
from .relay_client import RelayClientConnection, connect_relay_forever
from .transcribe import TranscriptionError, transcribe_m4a
from .virtual_cursor import ScreenLayout, VirtualCursor

PHONE_DIR = Path(__file__).resolve().parent.parent / "phone"
POLL_INTERVAL_S = 1.0
# Throttle log lines when the user is moving the on-phone trackpad without AX.
_AX_INPUT_LOG_INTERVAL_S = 8.0
_last_ax_input_warn: float = 0.0

# Cursor keyboard behavior:
#   Enter         → submit (may interrupt current agent run)
#   Option+Enter  → queue message to run after current task finishes
#   Cmd+Enter     → "stop & send" (explicitly interrupt)
#
# Set to True to always queue. If the agent is idle, Option+Enter just
# submits normally, so this is the safe default for agent workflows.
QUEUE_INSTEAD_OF_INTERRUPT = True


# Delay between raising a window and typing/pasting into it. macOS /
# Windows propagate frontmost-app changes asynchronously; without this
# the synthesized paste/type can race ahead to whatever app was
# frontmost BEFORE Cursor.
_FOCUS_SETTLE_DELAY_S = (
    max(0, int(os.environ.get("HC_FOCUS_SETTLE_DELAY_MS", "120").strip()))
    / 1000.0
)


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
        self.selected_host: str = "mac"  # 'mac' | 'pc'
        self.clients: set[object] = set()
        self.lock = asyncio.Lock()
        self.hold_start_ts: Optional[float] = None
        # Audio buffer for the currently-in-flight hold. The phone
        # streams ``audio/mp4`` (AAC) chunks as WebSocket binary frames
        # between ``hold_start`` and ``hold_end``; we append them here
        # and hand the whole blob to Whisper when the hold ends.
        # Single-phone assumption — if two phones hold at once, the
        # later one wins. That's fine for a personal tool.
        self.audio_buffer: bytearray = bytearray()
        # Presets are loaded once at startup. Users who edit
        # presets.json while the server is running can restart to pick
        # up changes.
        self.presets: list[Preset] = load_presets()
        self._presets_by_id: dict[str, Preset] = {p.id: p for p in self.presets}
        # Peer (Windows PC) — created at startup if HC_PEER_URL is set.
        self.peer: Optional[Peer] = None
        # Virtual cursor — initialized in lifespan() once we know both
        # screens' sizes. None until then.
        self.vcur: Optional[VirtualCursor] = None

    def preset(self, preset_id: str) -> Optional[Preset]:
        return self._presets_by_id.get(preset_id)

    def _all_windows(self) -> list[dict]:
        """Unified list of Cursor windows from Mac + (optionally) PC.

        Mac windows come first, then PC windows alphabetical. Each
        entry is a small dict that matches what the phone expects:
        ``{title, project, host}``. We derive project from title on
        the PC side (same as Mac's AppleScript does).
        """
        out: list[dict] = []
        for w in self.windows:
            out.append({"title": w.title, "project": w.project, "host": "mac"})
        if self.peer and self.peer.state.healthy:
            for pw in self.peer.state.windows:
                out.append(
                    {
                        "title": pw.title,
                        "project": _project_from_title(pw.title),
                        "host": "pc",
                    }
                )
        return out

    def _selected_index(self) -> int:
        """Index of the currently-selected card in the unified deck
        (Mac windows then PC windows)."""
        all_w = self._all_windows()
        if not all_w:
            return -1
        if self.selected_title is not None:
            for i, w in enumerate(all_w):
                if w["title"] == self.selected_title and w["host"] == self.selected_host:
                    return i
        return 0

    def selected_window(self) -> Optional[dict]:
        """Return the currently-selected card as a dict with host info."""
        idx = self._selected_index()
        if idx < 0:
            return None
        return self._all_windows()[idx]

    def to_payload(self) -> dict:
        peer_info = None
        if self.peer and self.peer.state.enabled:
            peer_info = {
                "configured": True,
                "healthy": self.peer.state.healthy,
                "hostname": self.peer.state.hostname,
                "side": self.peer.state.side,
            }
        lerr = last_list_error()
        return {
            "type": "state",
            "windows": self._all_windows(),
            "selected": self._selected_index(),
            "accessibility": {"trusted": _check_accessibility()},
            "list_windows_error": lerr,
            # Send only the public-safe view (id, label, submit mode) —
            # the actual prompt text stays server-side.
            "presets": [p.to_public_dict() for p in self.presets],
            "peer": peer_info,
            "cursor_host": self.vcur.host if self.vcur else "mac",
        }


def _project_from_title(title: str) -> str:
    """Heuristic: Cursor's window title is usually ``"file - project -
    Cursor"``. Grab the middle segment; fall back to the whole title
    if the format doesn't match."""
    parts = [p.strip() for p in title.split(" - ")]
    if len(parts) >= 3 and parts[-1].lower() == "cursor":
        return parts[-2]
    return title


state = State()


async def broadcast(payload: dict) -> None:
    message = json.dumps(payload)
    dead: list[object] = []
    for client in state.clients:
        try:
            await client.send_text(message)
        except Exception:
            dead.append(client)
    for c in dead:
        state.clients.discard(c)


async def _send_to_client(client: object, payload: dict) -> None:
    await client.send_text(json.dumps(payload))


async def poll_windows() -> None:
    """Periodically refresh the list of open Cursor windows.

    Re-broadcasts not only when the window list changes but also when
    **Accessibility** trust or the last AppleScript list error changes
    (same window set, but user just toggled a permission) — otherwise the
    phone can stay on \"Mac access needed\" forever.
    """
    global _last_ax_input_warn
    prev_key: tuple = ()
    prev_ax: Optional[bool] = None
    prev_err: Optional[str] = None
    while True:
        try:
            windows = list_windows()
        except Exception as exc:
            print(f"[poll_windows] error: {exc}")
            windows = []

        # Stable order so phone box positions don't shuffle as z-order changes.
        windows.sort(key=_sort_key)

        key = tuple((w.title, w.project) for w in windows)
        ax = _check_accessibility()
        err = last_list_error()
        list_changed = key != prev_key
        meta_changed = ax != prev_ax or err != prev_err
        if list_changed or meta_changed:
            if ax and not (prev_ax is True):
                # User likely just granted AX — allow immediate trackpad log again.
                _last_ax_input_warn = 0.0
            if list_changed:
                async with state.lock:
                    state.windows = windows
                    titles = {w.title for w in windows}
                    if state.selected_title not in titles:
                        state.selected_title = windows[0].title if windows else None
                    prev_key = key
                print(
                    f"[windows] updated ({len(windows)}): "
                    + ", ".join(f"{i}={w.project}" for i, w in enumerate(windows))
                )
            elif meta_changed:
                print(
                    f"[state] trust={ax} (was {prev_ax}) "
                    f"list_error={err!r} (was {prev_err!r})"
                )
            prev_ax = ax
            prev_err = err
            await broadcast(state.to_payload())
        await asyncio.sleep(POLL_INTERVAL_S)


# --- Trackpad: virtual cursor dispatch --------------------------------------
#
# The phone always sends raw (dx, dy) deltas; we decide here whether
# each delta affects the Mac cursor or the PC cursor based on the
# virtual cursor position relative to the configured screen layout.


async def _broadcast_cursor_host(host: str) -> None:
    """Notify the phone that the cursor is now on `host` so the pad
    UI can show the right label/accent color."""
    await broadcast({"type": "cursor_host", "host": host})


async def _dispatch_mouse_move(dx: float, dy: float) -> None:
    if not _ax_allows_synthetic_input():
        return
    vcur = state.vcur
    peer = state.peer
    peer_ok = bool(peer and peer.state.healthy)

    # Single-host mode: no peer, just move the Mac cursor directly.
    if vcur is None or not peer_ok or vcur.layout.pc_w == 0:
        try:
            mouse_move_by(dx, dy)
        except Exception as exc:
            print(f"[mouse_move] error: {exc}")
        return

    prev_host = vcur.host
    new_host, local_x, local_y = vcur.apply_delta(dx, dy)
    crossed = new_host != prev_host

    if new_host == "mac":
        if crossed:
            # Just came back from PC — warp the native cursor to the
            # correct Mac-side edge so it doesn't jump to wherever
            # we left it before crossing.
            ex, ey = vcur.mac_edge_on_cross_from_pc()
            if _QUARTZ_DISPLAY_OK:
                try:
                    CGWarpMouseCursorPosition((ex, ey))
                except Exception as exc:
                    print(f"[vcur] mac warp failed: {exc}")
            asyncio.create_task(_broadcast_cursor_host("mac"))
        else:
            try:
                mouse_move_by(dx, dy)
            except Exception as exc:
                print(f"[mouse_move] error: {exc}")
    else:  # new_host == "pc"
        if crossed:
            ex, ey = vcur.pc_edge_on_cross_from_mac()
            # Warp PC cursor so it picks up at the matching edge row.
            asyncio.create_task(peer.warp_cursor(ex, ey))  # type: ignore[union-attr]
            # Also snug the Mac native cursor right to the edge so it
            # doesn't visibly sit mid-screen during the crossing.
            if _QUARTZ_DISPLAY_OK:
                mx0, my0, mx1, my1 = vcur.layout.mac_box()
                if vcur.layout.side == "left":
                    edge_x = 0
                elif vcur.layout.side == "right":
                    edge_x = mx1 - mx0 - 1
                elif vcur.layout.side == "above":
                    edge_x = int(max(0, min(mx1 - mx0 - 1, vcur.x - mx0)))
                else:
                    edge_x = int(max(0, min(mx1 - mx0 - 1, vcur.x - mx0)))
                if vcur.layout.side in ("left", "right"):
                    edge_y = int(max(0, min(my1 - my0 - 1, vcur.y - my0)))
                elif vcur.layout.side == "above":
                    edge_y = 0
                else:
                    edge_y = my1 - my0 - 1
                try:
                    CGWarpMouseCursorPosition((edge_x, edge_y))
                except Exception:
                    pass
            asyncio.create_task(_broadcast_cursor_host("pc"))
        else:
            # Fast-path: forward delta to PC. Fire-and-forget.
            asyncio.create_task(peer.mouse_move(dx, dy))  # type: ignore[union-attr]


async def _dispatch_mouse_click(button: str) -> None:
    if not _ax_allows_synthetic_input():
        return
    vcur = state.vcur
    peer = state.peer
    if vcur and vcur.host == "pc" and peer and peer.state.healthy:
        await peer.mouse_click(button)
    else:
        await asyncio.to_thread(mouse_click, button)


async def _dispatch_mouse_scroll(dx: float, dy: float) -> None:
    if not _ax_allows_synthetic_input():
        return
    vcur = state.vcur
    peer = state.peer
    if vcur and vcur.host == "pc" and peer and peer.state.healthy:
        await peer.mouse_scroll(dx, dy)
    else:
        try:
            mouse_scroll(dy, dx)
        except Exception as exc:
            print(f"[mouse_scroll] error: {exc}")


async def handle_hold_start() -> None:
    """Phone began holding — make sure the target Cursor window's chat
    input is focused so by the time the user releases and we paste,
    keystrokes land in the right place. Audio is streamed from the
    phone as WebSocket binary frames; we just reset the buffer here."""
    state.hold_start_ts = time.monotonic()
    state.audio_buffer = bytearray()
    win = state.selected_window()
    if win is None:
        return
    await _focus_selected(win)


async def handle_hold_end() -> None:
    """Phone released — take the accumulated audio blob, send it to
    Whisper, and broadcast the transcript back so the phone can show
    its editable preview."""
    audio = bytes(state.audio_buffer)
    state.audio_buffer = bytearray()

    if not audio:
        await broadcast({"type": "final_transcript", "text": ""})
        return

    try:
        text = await transcribe_m4a(audio)
    except TranscriptionError as exc:
        print(f"[transcribe] {exc}")
        await broadcast({"type": "transcribe_error", "message": str(exc)})
        return
    except Exception as exc:
        print(f"[transcribe] unexpected: {exc}")
        await broadcast(
            {"type": "transcribe_error", "message": f"Unexpected error: {exc}"}
        )
        return

    print(f"[transcribe] {len(audio)} bytes -> {len(text)} chars")
    await broadcast({"type": "final_transcript", "text": text})


async def handle_submit(text: str) -> None:
    """Phone tapped Send with the reviewed text. Paste it into whatever
    input is currently focused inside the selected window, then
    submit / queue."""
    text = (text or "").strip()
    if not text:
        print("[submit] empty text, skipping")
        return

    win = state.selected_window()
    if win is None:
        print("[submit] no window selected, skipping")
        return

    on_pc = win["host"] == "pc" and state.peer and state.peer.state.healthy

    if not on_pc and not _ax_allows_synthetic_input():
        await broadcast(
            {
                "type": "action_blocked",
                "action": "submit",
                "reason": "accessibility",
            }
        )
        return

    if on_pc:
        await state.peer.focus_window(win["title"])  # type: ignore[union-attr]
        await asyncio.sleep(_FOCUS_SETTLE_DELAY_S)
        await state.peer.type_string(text)  # type: ignore[union-attr]
        await asyncio.sleep(0.05)
        if QUEUE_INSTEAD_OF_INTERRUPT:
            await state.peer.submit()  # type: ignore[union-attr]
        else:
            await state.peer.press_enter()  # type: ignore[union-attr]
    else:
        focus_window(win["title"])
        await asyncio.sleep(_FOCUS_SETTLE_DELAY_S)
        await asyncio.to_thread(paste_text, text)
        await asyncio.sleep(0.08)
        if QUEUE_INSTEAD_OF_INTERRUPT:
            press_option_enter()
        else:
            press_enter()

    print(
        f"[submit] [{win['host']}] {win['project']!r} "
        f"chars={len(text)} queue={QUEUE_INSTEAD_OF_INTERRUPT}"
    )
    await broadcast({"type": "submit_ack"})


async def handle_delete() -> None:
    """Best-effort Cmd+Z on Mac (or peer.delete() on PC). The phone's
    new editor has its own X that clears the textarea locally without
    ever hitting the Mac; this handler stays for backwards-compat with
    any older phone client and as a manual 'undo' escape hatch."""
    win = state.selected_window()
    if win and win["host"] == "pc" and state.peer and state.peer.state.healthy:
        await state.peer.delete()
        return
    if not _ax_allows_synthetic_input():
        await broadcast(
            {
                "type": "action_blocked",
                "action": "delete",
                "reason": "accessibility",
            }
        )
        return
    press_cmd_z()


async def handle_preset(preset_id: str) -> None:
    """One-tap preset: focus the selected Cursor window, type the canned
    prompt into its focused input, then submit / queue / do nothing per
    the preset's ``submit`` mode."""
    preset = state.preset(preset_id)
    if preset is None:
        print(f"[preset] unknown id: {preset_id!r}")
        return

    win = state.selected_window()
    if win is None:
        print(f"[preset] no selected window; ignoring {preset.label!r}")
        await broadcast(
            {
                "type": "preset_result",
                "id": preset.id,
                "ok": False,
                "reason": "no_window",
            }
        )
        return

    on_pc = win["host"] == "pc" and state.peer and state.peer.state.healthy

    if not on_pc and not _ax_allows_synthetic_input():
        await broadcast(
            {
                "type": "action_blocked",
                "action": "preset",
                "reason": "accessibility",
                "id": preset_id,
            }
        )
        return

    if on_pc:
        await state.peer.focus_window(win["title"])  # type: ignore[union-attr]
        await asyncio.sleep(_FOCUS_SETTLE_DELAY_S)
        await state.peer.type_string(preset.text)  # type: ignore[union-attr]
        await asyncio.sleep(0.05)
        if preset.submit == "queue":
            await state.peer.submit()  # type: ignore[union-attr]
        elif preset.submit == "send":
            await state.peer.press_enter()  # type: ignore[union-attr]
    else:
        focus_window(win["title"])
        # Let the WM actually transfer focus before we start firing keys.
        await asyncio.sleep(_FOCUS_SETTLE_DELAY_S)
        # Typing is blocking (~4ms per char × message length). Run in a
        # worker thread so the event loop stays responsive and other
        # clients (or another preset tap) don't queue up behind it.
        await asyncio.to_thread(type_string, preset.text)
        # Small beat so the app registers all typed chars before we submit.
        await asyncio.sleep(0.05)
        if preset.submit == "queue":
            press_option_enter()
        elif preset.submit == "send":
            press_enter()
        # "none" → just leave the text in the field

    print(
        f"[preset] {preset.label!r} → [{win['host']}] "
        f"window={win['project']!r} submit={preset.submit} "
        f"chars={len(preset.text)}"
    )
    await broadcast(
        {
            "type": "preset_result",
            "id": preset.id,
            "ok": True,
            "submit": preset.submit,
            "window": win["project"],
            "host": win["host"],
        }
    )


async def _focus_selected(win: dict) -> None:
    """Focus a window, routing to the correct host. We intentionally do
    NOT try to auto-select Cursor's chat box; the phone UI now exposes
    a permanent trackpad so the user can click the exact field they
    want without us toggling sidebars behind their back."""
    if win["host"] == "pc" and state.peer and state.peer.state.healthy:
        await state.peer.focus_window(win["title"])
    else:
        focus_window(win["title"])


async def handle_select(index: int) -> None:
    async with state.lock:
        all_w = state._all_windows()
        if 0 <= index < len(all_w):
            win = all_w[index]
            state.selected_title = win["title"]
            state.selected_host = win["host"]
            await broadcast(state.to_payload())
        else:
            win = None
    if win is not None:
        await _focus_selected(win)


async def handle_switch(delta: int) -> None:
    async with state.lock:
        all_w = state._all_windows()
        if not all_w:
            return
        current = state._selected_index()
        if current < 0:
            current = 0
        new_idx = (current + delta) % len(all_w)
        win = all_w[new_idx]
        state.selected_title = win["title"]
        state.selected_host = win["host"]
        print(
            f"[switch] delta={delta:+d} {current} -> {new_idx} "
            f"([{win['host']}] {win['project']})"
        )
        await broadcast(state.to_payload())
    await _focus_selected(win)


def _mac_screen_size() -> tuple[int, int]:
    """Primary Mac display size in points. Falls back to 1920x1080 if
    Quartz isn't available (shouldn't happen on a normal install)."""
    if not _QUARTZ_DISPLAY_OK:
        return (1920, 1080)
    try:
        b = CGDisplayBounds(CGMainDisplayID())
        return (int(b.size.width), int(b.size.height))
    except Exception:
        return (1920, 1080)


async def _on_peer_windows_change() -> None:
    """Called by the Peer when its window list changes; rebroadcasts
    the merged deck so all connected phones update."""
    async with state.lock:
        # If the previously-selected PC window disappeared, fall back.
        all_titles = {
            (w["host"], w["title"]) for w in state._all_windows()
        }
        current = (state.selected_host, state.selected_title or "")
        if current not in all_titles:
            if state._all_windows():
                first = state._all_windows()[0]
                state.selected_title = first["title"]
                state.selected_host = first["host"]
            else:
                state.selected_title = None
                state.selected_host = "mac"
        await broadcast(state.to_payload())


def _init_virtual_cursor(mac_w: int, mac_h: int) -> VirtualCursor:
    """Build the virtual cursor from current configuration.

    Called at startup. If there's no peer yet, we use a 0x0 PC region
    which effectively disables edge crossing — once the peer reports
    its size we rebuild the layout.
    """
    peer = state.peer
    if peer and peer.state.healthy:
        pw, ph = peer.state.screen_w or 1920, peer.state.screen_h or 1080
        side = peer.state.side
    else:
        # Pretend the PC is 0-wide so the layout math degenerates to
        # Mac-only until the peer comes online.
        pw, ph = 0, 0
        side = peer.state.side if peer else "right"
    layout = ScreenLayout(
        mac_w=mac_w, mac_h=mac_h, pc_w=pw, pc_h=ph, side=side  # type: ignore[arg-type]
    )
    return VirtualCursor.centered_on_mac(layout)


@asynccontextmanager
async def lifespan(_: FastAPI):
    mac_w, mac_h = _mac_screen_size()
    state.peer = Peer.from_env(on_windows_change=_on_peer_windows_change)
    if state.peer:
        print(f"[peer] configured → {state.peer.state.base_url} (side={state.peer.state.side})")
        await state.peer.start()

    state.vcur = _init_virtual_cursor(mac_w, mac_h)

    # Rebuild the virtual-cursor layout once the peer health comes in
    # with real screen dimensions. Simple approach: check once a few
    # seconds after startup.
    async def _refresh_layout() -> None:
        await asyncio.sleep(2.0)
        if state.peer and state.peer.state.healthy:
            state.vcur = _init_virtual_cursor(mac_w, mac_h)
            print(
                f"[vcur] layout updated: mac={mac_w}x{mac_h}, "
                f"pc={state.peer.state.screen_w}x{state.peer.state.screen_h}, "
                f"side={state.peer.state.side}"
            )
            await broadcast(state.to_payload())

    task = asyncio.create_task(poll_windows())
    layout_task = asyncio.create_task(_refresh_layout())
    relay_task: Optional[asyncio.Task] = None
    relay_url = os.environ.get("BLIND_RELAY_URL", "").strip()
    supabase_for_relay = os.environ.get("BLIND_SUPABASE_ACCESS_TOKEN", "").strip()
    legacy_token = os.environ.get("BLIND_RELAY_TOKEN", "").strip()
    relay_token = supabase_for_relay or legacy_token
    if supabase_for_relay:
        relay_device_id = (os.environ.get("BLIND_DEVICE_ID") or "account").strip() or "account"
    else:
        relay_device_id = os.environ.get("BLIND_DEVICE_ID", "").strip()
    if relay_url and relay_token and (supabase_for_relay or relay_device_id):
        mint_session = bool(supabase_for_relay)
        relay_task = asyncio.create_task(
            connect_relay_forever(
                relay_url=relay_url,
                device_id=relay_device_id,
                token=relay_token,
                mint_relay_session=mint_session,
                on_connect=_relay_connected,
                on_packet=_process_client_packet,
                on_disconnect=_relay_disconnected,
            )
        )
    elif relay_url and not relay_token:
        print("[relay] Set BLIND_SUPABASE_ACCESS_TOKEN (account) or BLIND_RELAY_TOKEN (dev) to use the relay.")
    elif relay_token and not relay_url and (supabase_for_relay or legacy_token):
        print(
            "[relay] Set BLIND_RELAY_URL (and for dev pairing also BLIND_DEVICE_ID) to reach the public relay."
        )
    elif relay_url and (supabase_for_relay or legacy_token) and not supabase_for_relay and not relay_device_id:
        print("[relay] Set BLIND_DEVICE_ID for dev relay pairing, or use BLIND_SUPABASE_ACCESS_TOKEN for account mode.")
    try:
        yield
    finally:
        task.cancel()
        layout_task.cancel()
        if relay_task:
            relay_task.cancel()
        if state.peer:
            await state.peer.stop()


app = FastAPI(lifespan=lifespan)


@app.get("/", response_class=HTMLResponse)
async def index() -> FileResponse:
    return FileResponse(
        PHONE_DIR / "index.html",
        headers={
            "Cache-Control": "no-store, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.get("/manifest.json")
async def manifest() -> FileResponse:
    return FileResponse(PHONE_DIR / "manifest.json", media_type="application/manifest+json")


@app.get("/config.js")
async def config_js() -> HTMLResponse:
    config = {
        "supabaseUrl": os.environ.get("SUPABASE_URL", "").strip(),
        "supabaseAnonKey": os.environ.get("SUPABASE_ANON_KEY", "").strip(),
        "relayUrl": os.environ.get("BLIND_RELAY_URL", "").strip(),
    }
    config["accountPairing"] = bool(
        config["supabaseUrl"] and config["supabaseAnonKey"] and config["relayUrl"]
    )
    return HTMLResponse(
        "window.BLIND_MONKEY_CONFIG = " + json.dumps(config) + ";\n",
        media_type="application/javascript",
        headers={"Cache-Control": "no-store"},
    )


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


@app.get("/trust.crt")
async def trust_crt() -> FileResponse:
    """Serve the self-signed cert as a downloadable iOS configuration
    profile. The ``application/x-x509-ca-cert`` MIME type is what
    makes Safari on iOS show the "This website is trying to download
    a configuration profile" prompt instead of just downloading a
    random file. After the user taps Allow, iOS takes them straight
    to the Profile Installation screen.

    On Android (Chrome), the same MIME triggers the system Credential
    Storage installer.

    Safe to expose: a cert's public half is, by definition, public.
    Nothing here leaks the private key — that lives in ``certs/server.key``
    and is only used inside the uvicorn process.
    """
    from .certs import CERT_DIR

    cert_path = CERT_DIR / "server.crt"
    if not cert_path.exists():
        # Shouldn't happen because ``main()`` generates the cert
        # before uvicorn starts; guard anyway so a stale/broken state
        # returns a clean 404 instead of an opaque 500.
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Cert not found")
    return FileResponse(
        cert_path,
        media_type="application/x-x509-ca-cert",
        filename="HandControl.crt",
    )


# Minimal HTML walkthrough for installing + trusting the cert. Kept
# inline (not templated into a separate file) so the page works even
# if something in ``phone/`` is broken, and so there's nothing extra
# to ship/serve.
_INSTALL_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="theme-color" content="#000000">
  <title>Install Blind Monkey cert</title>
  <style>
    :root {
      --bg: #000;
      --panel: #0e0e0e;
      --text: #f0f0f0;
      --muted: #8a8a8a;
      --accent: #f25f4c;
      --accent-soft: rgba(242, 95, 76, 0.35);
      --border: #1e1e1e;
    }
    *, *::before, *::after { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; background: var(--bg); color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI",
                   system-ui, sans-serif; }
    body { padding: max(28px, env(safe-area-inset-top)) max(22px, env(safe-area-inset-right))
                   max(28px, env(safe-area-inset-bottom)) max(22px, env(safe-area-inset-left));
      max-width: 640px; margin: 0 auto; line-height: 1.55; }
    h1 { font-size: 26px; font-weight: 800; letter-spacing: -0.01em;
      margin: 0 0 8px; }
    .lede { font-size: 15px; color: var(--muted); margin-bottom: 28px; }
    .cta {
      display: block; text-align: center; margin: 6px 0 22px;
      padding: 18px 22px; font-size: 15px; font-weight: 700; letter-spacing: 0.06em;
      text-transform: uppercase; text-decoration: none;
      background: var(--accent); color: #000; border-radius: 14px;
      box-shadow: 0 10px 30px rgba(242, 95, 76, 0.25);
      transition: transform 0.12s;
    }
    .cta:active { transform: scale(0.98); }
    ol { padding-left: 20px; margin: 0; }
    ol li { margin: 14px 0; }
    ol li b { color: var(--text); }
    .panel {
      background: var(--panel); border: 1px solid var(--border);
      border-radius: 14px; padding: 18px 20px; margin-bottom: 18px;
    }
    .tag {
      display: inline-block; padding: 2px 8px; font-size: 11px; font-weight: 700;
      letter-spacing: 0.08em; text-transform: uppercase;
      background: rgba(242, 95, 76, 0.12); color: var(--accent);
      border: 1px solid var(--accent-soft); border-radius: 999px;
      margin-right: 8px; vertical-align: 2px;
    }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      background: #181818; padding: 1px 6px; border-radius: 5px; font-size: 13px; }
    a { color: var(--accent); }
    .after {
      margin-top: 26px; padding-top: 18px; border-top: 1px solid var(--border);
      color: var(--muted); font-size: 13px;
    }
  </style>
</head>
<body>
  <h1>Install Blind Monkey certificate</h1>
  <p class="lede">
    One-time setup so Safari stops showing a "Not Private" warning
    every time you open the remote.
  </p>

  <a class="cta" href="/trust.crt" download>Download cert</a>

  <div class="panel">
    <p><span class="tag">iPhone / iPad</span></p>
    <ol>
      <li>Tap <b>Download cert</b> above. When Safari asks
        <i>"This website is trying to download a configuration
        profile"</i>, tap <b>Allow</b>.</li>
      <li>Open <b>Settings</b> → at the top you'll see
        <b>Profile Downloaded</b>. Tap it.
        (If it's not there: <b>Settings → General → VPN &amp; Device
        Management</b> → <b>Blind Monkey</b>.)</li>
      <li>Tap <b>Install</b> in the top-right, enter your passcode,
        tap <b>Install</b> again when it warns about the profile
        being unverified, and <b>Done</b>.</li>
      <li>Go to <b>Settings → General → About → Certificate Trust
        Settings</b>. Under "Enable full trust for root certificates",
        toggle <b>Blind Monkey</b> <b>on</b>. Confirm.</li>
      <li>Reload the Blind Monkey tab in Safari. No more warning.</li>
    </ol>
  </div>

  <div class="panel">
    <p><span class="tag">Android</span></p>
    <ol>
      <li>Tap <b>Download cert</b> above.</li>
      <li>Open the file (or <b>Settings → Security → Encryption &amp;
        credentials → Install a certificate → CA certificate</b>).</li>
      <li>Accept the warning and install. The site will be trusted
        immediately.</li>
    </ol>
  </div>

  <p class="after">
    The cert is generated locally by your Mac (<code>./certs/server.crt</code>),
    never leaves your machine, and stays valid for 5 years. Reinstall
    only if you rename your Mac (the Bonjour hostname in the cert
    changes).
  </p>
</body>
</html>
"""


@app.get("/install", response_class=HTMLResponse)
async def install_page() -> HTMLResponse:
    """Step-by-step page that walks the user through installing the
    self-signed cert on their phone. Links to ``/trust.crt`` for the
    actual download."""
    return HTMLResponse(content=_INSTALL_HTML)


@app.get("/presets")
async def presets_endpoint() -> dict:
    """Inspect the loaded presets (handy when debugging a custom
    ``presets.json``). Includes ``text`` for local debugging since the
    server only listens on the LAN."""
    return {
        "count": len(state.presets),
        "presets": [
            {
                "id": p.id,
                "label": p.label,
                "text": p.text,
                "submit": p.submit,
            }
            for p in state.presets
        ],
    }


@app.get("/health")
async def health_endpoint() -> dict:
    """Small status endpoint for the native Mac companion UI."""
    ax = _check_accessibility()
    err = last_list_error()
    return {
        "ok": True,
        "accessibility": {"trusted": ax},
        "process": {
            "python": sys.executable,
        },
        "windows_count": len(state._all_windows()),
        "list_windows_error": err,
        "accessibility_hint": None
        if ax
        else (
            f"System Settings → Privacy & Security → Accessibility: enable this "
            f"Python ({sys.executable}), and Blind Monkey if shown. Then restart the server."
        ),
        "relay": {
            "configured": bool(
                os.environ.get("BLIND_RELAY_URL", "").strip()
                and (
                    os.environ.get("BLIND_SUPABASE_ACCESS_TOKEN", "").strip()
                    or (
                        os.environ.get("BLIND_DEVICE_ID", "").strip()
                        and os.environ.get("BLIND_RELAY_TOKEN", "").strip()
                    )
                )
            ),
        },
    }


app.mount("/static", StaticFiles(directory=str(PHONE_DIR)), name="static")


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    state.clients.add(websocket)
    try:
        await _send_to_client(websocket, state.to_payload())
        while True:
            # receive() returns either {"text": "..."} or {"bytes": b"..."}
            # depending on the frame type. Phones send JSON control
            # messages as text and audio chunks as binary.
            packet = await websocket.receive()
            if packet.get("type") == "websocket.disconnect":
                break
            await _process_client_packet(websocket, packet)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[ws] error: {exc}")
    finally:
        state.clients.discard(websocket)


async def _process_client_packet(client: object, packet: dict) -> None:
    if "bytes" in packet and packet["bytes"] is not None:
        chunk = packet["bytes"]
        if chunk:
            state.audio_buffer.extend(chunk)
        return

    raw = packet.get("text")
    if raw is None:
        return
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        return
    await _handle_client_message(client, msg)


async def _handle_client_message(client: object, msg: dict) -> None:
    kind = msg.get("type")
    if kind == "hold_start":
        await handle_hold_start()
    elif kind == "hold_end":
        await handle_hold_end()
    elif kind == "submit":
        text = msg.get("text")
        if isinstance(text, str):
            await handle_submit(text)
    elif kind == "cancel":
        state.audio_buffer = bytearray()
        state.hold_start_ts = None
        print("[ws] cancel")
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
    elif kind == "preset":
        pid = msg.get("id")
        if isinstance(pid, str):
            await handle_preset(pid)
    elif kind == "mouse_move":
        dx = msg.get("dx")
        dy = msg.get("dy")
        if isinstance(dx, (int, float)) and isinstance(dy, (int, float)):
            await _dispatch_mouse_move(float(dx), float(dy))
    elif kind == "mouse_click":
        btn = msg.get("button")
        if btn in ("left", "right"):
            await _dispatch_mouse_click(btn)
    elif kind == "mouse_scroll":
        dx = msg.get("dx") or 0
        dy = msg.get("dy") or 0
        if isinstance(dx, (int, float)) and isinstance(dy, (int, float)):
            await _dispatch_mouse_scroll(float(dx), float(dy))
    elif kind == "ping":
        await _send_to_client(client, {"type": "pong"})
    elif kind == "request_state":
        await _send_to_client(client, state.to_payload())


async def _relay_connected(client: RelayClientConnection) -> None:
    state.clients.add(client)
    await _send_to_client(client, state.to_payload())


async def _relay_disconnected(client: RelayClientConnection) -> None:
    state.clients.discard(client)


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


def _check_accessibility(prompt: bool = False) -> bool:
    try:
        if prompt:
            from ApplicationServices import (  # type: ignore
                AXIsProcessTrustedWithOptions,
                kAXTrustedCheckOptionPrompt,
            )

            options = {
                kAXTrustedCheckOptionPrompt.takeUnretainedValue(): True,
            }
            return bool(AXIsProcessTrustedWithOptions(options))

        from ApplicationServices import AXIsProcessTrusted  # type: ignore

        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def _ax_allows_synthetic_input() -> bool:
    """CoreGraphics/AppleScript input works only for Accessibility-trusted
    processes. Throttle stderr so a dragging finger on the phone does not
    flood the log.
    """
    global _last_ax_input_warn
    if _check_accessibility():
        return True
    now = time.monotonic()
    if now - _last_ax_input_warn >= _AX_INPUT_LOG_INTERVAL_S:
        _last_ax_input_warn = now
        print(
            f"[tcc] Synthetic input ignored — enable this binary in System Settings"
            f" → Privacy & Security → Accessibility: {sys.executable}"
        )
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
    """Check whether ``port`` is actually bound by a live listener.

    We mirror uvicorn's own socket setup (``SO_REUSEADDR``) so a recently-
    closed socket still in ``TIME_WAIT`` doesn't trigger a false
    "port in use" error.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
            f"  • If Blind Monkey is already running, just use that instance.\n"
            f"  • Otherwise run on another port:  PORT=8080 ./run.sh\n\n"
        )
        sys.exit(1)

    ip = get_lan_ip()
    hostname = get_mdns_hostname()
    ts_dns, ts_ips = get_tailscale_sans()
    trusted = _check_accessibility(
        prompt=os.environ.get("BLIND_PROMPT_ACCESSIBILITY", "").lower()
        in {"1", "true", "yes"}
    )

    # Generate (or reuse) a self-signed TLS cert. We use HTTPS so
    # the phone PWA runs in a "secure context" (required for reliable
    # bookmark + service-worker behavior on iOS) and so installing
    # the cert once on the phone eliminates the per-launch warning.
    try:
        cert = ensure_cert()
        use_https = True
    except Exception as exc:
        print(f"[certs] failed to generate TLS cert: {exc}")
        print("[certs] falling back to HTTP")
        cert = None
        use_https = False

    scheme = "https" if use_https else "http"

    print("\n" + "=" * 64)
    print("  Blind Monkey running.")
    print()
    if hostname:
        print(f"  Phone URL (stable):  {scheme}://{hostname}:{port}")
        print(f"  Phone URL (by IP):   {scheme}://{ip}:{port}")
        print()
        print(f"  Bookmark the stable URL on your phone — the .local")
        print(f"  hostname won't change when your Wi-Fi does.")
    else:
        print(f"  Phone URL:  {scheme}://{ip}:{port}")
    if ts_dns or ts_ips:
        print()
        print("  Tailscale (same phone, any network):")
        for h in ts_dns:
            print(f"    {scheme}://{h}:{port}")
        for tip in ts_ips:
            if tip.startswith("100."):
                print(f"    {scheme}://{tip}:{port}")
        print("    Start Tailscale on this Mac (`tailscale up`) and on your")
        print("    phone. Trust the cert once per hostname — visit /install")
        print("    using the Tailscale URL if Safari warns.")
    print("=" * 64)
    if trusted:
        print("  Accessibility: OK")
    else:
        print("  Accessibility: NOT GRANTED (this exact process is untrusted).")
        print(f"  → Python: {sys.executable}")
        print("  → System Settings → Privacy & Security → Accessibility")
        print("    Enable Blind Monkey, and the Python at the path above, then")
        print("    restart this server. (The menu-bar app is not the same process.)")
    if os.environ.get("OPENAI_API_KEY", "").strip():
        model = os.environ.get("HC_TRANSCRIBE_MODEL", "whisper-1").strip() or "whisper-1"
        print(f"  OpenAI:        OK (transcription model: {model})")
    else:
        print("  OpenAI:        NO KEY — phone dictation will fail.")
        print("    Add OPENAI_API_KEY to ~/.hand-control.env or export it,")
        print("    then restart. (Other features work without it.)")
    if use_https:
        # Compose a pointer to /install using the stable hostname when
        # we have one, or the raw IP otherwise.
        install_host = hostname if hostname else ip
        install_url = f"{scheme}://{install_host}:{port}/install"
        print("=" * 64)
        print("  ONE-TIME SETUP — kill the 'Not Private' warning:")
        print(f"    Visit on your phone:  {install_url}")
        if ts_dns:
            ts_install = f"{scheme}://{ts_dns[0]}:{port}/install"
            print(f"    (Tailscale: same steps at  {ts_install} )")
        print("    Follow the 4-step install (takes ~45 seconds).")
        print("    After that Safari trusts the site permanently —")
        print("    no more warnings on every launch.")
        print()
        print("  If you'd rather skip it (quick test, etc.):")
        print("    Open the phone URL, tap 'Show Details' →")
        print("    'Visit this website'. You'll re-see this prompt")
        print("    on every future launch until you install the cert.")
    print("=" * 64 + "\n")

    # Scannable QR of the phone URL. Point your phone camera at the
    # terminal and tap the notification that pops up — beats typing a
    # ``.local`` URL into Safari, especially on iOS where there's no
    # history-based autocomplete for ``.local`` hosts.
    #
    # HC_QR_HOST=my-mac.local            — force QR to a specific host
    # HC_QR_USE_TAILSCALE=1             — dev fallback for direct Tailscale testing
    # BLIND_RELAY_URL / BLIND_DEVICE_ID / BLIND_RELAY_TOKEN append relay config
    qr_override = os.environ.get("HC_QR_HOST", "").strip().rstrip(".")
    phone_app_url = os.environ.get("BLIND_PHONE_APP_URL", "").strip()
    relay_url = os.environ.get("BLIND_RELAY_URL", "").strip()
    relay_device_id = os.environ.get("BLIND_DEVICE_ID", "").strip()
    relay_token = os.environ.get("BLIND_RELAY_TOKEN", "").strip()
    account_pairing = bool(
        os.environ.get("SUPABASE_URL", "").strip()
        and os.environ.get("SUPABASE_ANON_KEY", "").strip()
        and relay_url
    )
    prefer_ts = os.environ.get("HC_QR_USE_TAILSCALE", "").lower() in (
        "1",
        "true",
        "yes",
    )
    if qr_override:
        phone_url = f"{scheme}://{qr_override}:{port}"
    elif account_pairing and phone_app_url:
        phone_url = phone_app_url
    elif relay_url and relay_device_id and relay_token and phone_app_url:
        phone_url = phone_app_url
    elif prefer_ts and ts_dns:
        phone_url = f"{scheme}://{ts_dns[0]}:{port}"
    elif hostname:
        phone_url = f"{scheme}://{hostname}:{port}"
    else:
        phone_url = f"{scheme}://{ip}:{port}"
    if relay_url and relay_device_id and relay_token and not account_pairing:
        parts = urlsplit(phone_url)
        query = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key not in {"relay", "device", "token"}
        ]
        query.extend(
            [
                ("relay", relay_url),
                ("device", relay_device_id),
                ("token", relay_token),
            ]
        )
        phone_url = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )
    try:
        import qrcode  # type: ignore

        qr = qrcode.QRCode(
            border=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
        )
        qr.add_data(phone_url)
        qr.make(fit=True)
        print(f"  Scan with your phone camera → {phone_url}\n")
        # ``invert=True`` draws dark modules as whitespace, which looks
        # right on a dark terminal (the default on macOS). The half-
        # block characters keep the QR compact — roughly 20 rows tall
        # for a typical ``.local`` URL.
        qr.print_ascii(invert=True)
        print("")
    except ImportError:
        # qrcode is in requirements.txt but if someone is on an older
        # install we don't want to crash. The URL is still printed in
        # the banner so they can type it manually.
        pass
    except Exception as exc:
        print(f"[qr] couldn't draw QR: {exc}")

    try:
        if use_https and cert is not None:
            uvicorn.run(
                "server.main:app",
                host="0.0.0.0",
                port=port,
                log_level="info",
                ssl_keyfile=str(cert.key_path),
                ssl_certfile=str(cert.cert_path),
            )
        else:
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
