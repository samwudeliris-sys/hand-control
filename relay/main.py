"""Blind Monkey relay MVP.

This service is intentionally message-agnostic: it authenticates a Mac
and a phone into the same device room, then forwards text and binary
WebSocket frames unchanged. Cursor control stays on the Mac.
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import jwt

Role = Literal["mac", "phone"]

app = FastAPI(title="Blind Monkey Relay", version="0.1.0")
PHONE_DIR = Path(__file__).resolve().parent.parent / "phone"

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("BLIND_RELAY_CORS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_MAX_TEXT_BYTES = int(os.environ.get("BLIND_RELAY_MAX_TEXT_BYTES", "262144"))
_MAX_BINARY_BYTES = int(os.environ.get("BLIND_RELAY_MAX_BINARY_BYTES", "30000000"))
# Phone trackpad events are flushed on requestAnimationFrame, so normal use can
# legitimately approach 60 messages/sec before audio/control messages are added.
_MAX_MESSAGES_PER_SECOND = float(os.environ.get("BLIND_RELAY_MAX_MSG_PER_SECOND", "180"))


@dataclass
class Peer:
    websocket: WebSocket
    role: Role
    device_id: str
    connected_at: float
    message_count: int = 0
    window_started_at: float = 0.0


class Room:
    def __init__(self, device_id: str) -> None:
        self.device_id = device_id
        self.mac: Optional[Peer] = None
        self.phone: Optional[Peer] = None
        self.lock = asyncio.Lock()

    def peer_for(self, role: Role) -> Optional[Peer]:
        return self.mac if role == "mac" else self.phone

    def set_peer(self, peer: Peer) -> Optional[Peer]:
        if peer.role == "mac":
            old, self.mac = self.mac, peer
        else:
            old, self.phone = self.phone, peer
        return old

    def remove_peer(self, peer: Peer) -> None:
        if peer.role == "mac" and self.mac is peer:
            self.mac = None
        if peer.role == "phone" and self.phone is peer:
            self.phone = None

    def other(self, peer: Peer) -> Optional[Peer]:
        return self.phone if peer.role == "mac" else self.mac


rooms: dict[str, Room] = {}


@dataclass(frozen=True)
class AuthContext:
    room_id: str
    user_id: str
    mode: Literal["supabase", "dev", "relay"]


def _public_relay_url() -> str:
    configured = os.environ.get("BLIND_PUBLIC_RELAY_URL", "").strip().rstrip("/")
    if configured:
        return configured
    railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if railway_domain:
        return f"wss://{railway_domain}"
    return os.environ.get("BLIND_RELAY_URL", "").strip().rstrip("/")


def _relay_session_secret() -> str:
    return (
        os.environ.get("BLIND_RELAY_SESSION_SECRET", "").strip()
        or os.environ.get("SUPABASE_JWT_SECRET", "").strip()
    )


def _relay_session_ttl_seconds() -> int:
    return int(os.environ.get("BLIND_RELAY_SESSION_TTL", "3600"))


def _sign_relay_access_token(
    *, user_id: str, room_id: str, role: Role, ttl: int
) -> str:
    secret = _relay_session_secret()
    if not secret:
        raise ValueError("BLIND_RELAY_SESSION_SECRET (or SUPABASE_JWT_SECRET) is not set")
    now = int(time.time())
    payload = {
        "iss": "blind-monkey-relay",
        "sub": user_id,
        "room": room_id,
        "role": role,
        "typ": "bm_relay",
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def _verify_relay_access_token(token: str) -> Optional[AuthContext]:
    secret = _relay_session_secret()
    if not secret:
        return None
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_exp": True},
        )
    except jwt.PyJWTError:
        return None
    if claims.get("typ") != "bm_relay":
        return None
    user_id = str(claims.get("sub") or "").strip()
    room_id = str(claims.get("room") or "").strip()
    if not user_id or not room_id:
        return None
    return AuthContext(room_id=room_id, user_id=user_id, mode="relay")


def _decode_supabase_user(token: str) -> Optional[str]:
    jwt_secret = os.environ.get("SUPABASE_JWT_SECRET", "").strip()
    if not jwt_secret or not token:
        return None
    try:
        claims = jwt.decode(
            token,
            jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
            options={"verify_exp": True},
        )
    except jwt.InvalidAudienceError:
        try:
            claims = jwt.decode(
                token,
                jwt_secret,
                algorithms=["HS256"],
                options={"verify_aud": False, "verify_exp": True},
            )
        except jwt.PyJWTError:
            return None
    except jwt.PyJWTError:
        return None
    user_id = str(claims.get("sub") or "").strip()
    return user_id or None


def _configured_token() -> str:
    return os.environ.get("BLIND_RELAY_TOKEN", "dev-relay-token").strip()


def _token_ok(token: str | None) -> bool:
    expected = _configured_token()
    return bool(expected and token and token == expected)


def _auth_context(*, role: Role, device_id: str, token: str | None) -> Optional[AuthContext]:
    """Authorize a WebSocket: short-lived relay JWT, Supabase access JWT, or dev token."""
    if token:
        relay_ctx = _verify_relay_access_token(token)
        if relay_ctx is not None:
            return relay_ctx
        supabase_sub = _decode_supabase_user(token)
        if supabase_sub:
            return AuthContext(
                room_id=f"acct:{supabase_sub}",
                user_id=supabase_sub,
                mode="supabase",
            )
    if _token_ok(token):
        return AuthContext(
            room_id=f"dev:{device_id}",
            user_id="dev",
            mode="dev",
        )

    return None


def _room(device_id: str) -> Room:
    if device_id not in rooms:
        rooms[device_id] = Room(device_id)
    return rooms[device_id]


async def _close_old_peer(old: Optional[Peer]) -> None:
    if not old:
        return
    try:
        await old.websocket.close(code=4001, reason="Replaced by a newer connection")
    except Exception:
        pass


def _rate_limited(peer: Peer) -> bool:
    now = time.monotonic()
    if now - peer.window_started_at >= 1:
        peer.window_started_at = now
        peer.message_count = 0
    peer.message_count += 1
    return peer.message_count > _MAX_MESSAGES_PER_SECOND


async def _forward_loop(room: Room, peer: Peer) -> None:
    while True:
        packet = await peer.websocket.receive()
        if packet.get("type") == "websocket.disconnect":
            break
        if _rate_limited(peer):
            await peer.websocket.close(code=4408, reason="Rate limited")
            break

        target = room.other(peer)
        if not target:
            continue

        text = packet.get("text")
        if text is not None:
            if len(text.encode("utf-8")) > _MAX_TEXT_BYTES:
                await peer.websocket.close(code=4409, reason="Text frame too large")
                break
            await target.websocket.send_text(text)
            continue

        data = packet.get("bytes")
        if data is not None:
            if len(data) > _MAX_BINARY_BYTES:
                await peer.websocket.close(code=4409, reason="Binary frame too large")
                break
            await target.websocket.send_bytes(data)


async def _handle_connection(
    websocket: WebSocket,
    *,
    role: Role,
    device_id: str,
    token: str | None,
) -> None:
    auth = _auth_context(role=role, device_id=device_id, token=token)
    if not auth:
        await websocket.close(code=4401, reason="Invalid relay token")
        return

    await websocket.accept()
    room = _room(auth.room_id)
    peer = Peer(
        websocket=websocket,
        role=role,
        device_id=auth.room_id,
        connected_at=time.time(),
        window_started_at=time.monotonic(),
    )

    async with room.lock:
        old = room.set_peer(peer)
    await _close_old_peer(old)

    print(f"[relay] {role} connected room={auth.room_id} mode={auth.mode}")
    try:
        await _forward_loop(room, peer)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        print(f"[relay] {role} room={auth.room_id} error: {exc}")
    finally:
        async with room.lock:
            room.remove_peer(peer)
        print(f"[relay] {role} disconnected room={auth.room_id}")


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {
            "ok": True,
            "session_ttl_seconds": _relay_session_ttl_seconds(),
            "rooms": {
                device_id: {
                    "mac": room.mac is not None,
                    "phone": room.phone is not None,
                }
                for device_id, room in rooms.items()
            },
        }
    )


class _RelaySessionBody(BaseModel):
    role: str = Field("phone", description="mac or phone (WebSocket role)")


@app.post("/v1/relay/sessions")
async def mint_relay_session(
    body: _RelaySessionBody,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing Authorization: Bearer <supabase access token>")
    supabase = authorization[7:].strip()
    user_id = _decode_supabase_user(supabase)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired Supabase access token")
    role_norm = (body.role or "phone").strip().lower()
    if role_norm not in ("mac", "phone"):
        raise HTTPException(status_code=400, detail='role must be "mac" or "phone"')
    ws_role: Role = "mac" if role_norm == "mac" else "phone"
    room_id = f"acct:{user_id}"
    ttl = _relay_session_ttl_seconds()
    try:
        token = _sign_relay_access_token(
            user_id=user_id,
            room_id=room_id,
            role=ws_role,
            ttl=ttl,
        )
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return JSONResponse(
        {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": ttl,
            "room_id": room_id,
        }
    )


@app.get("/config.js")
async def config_js() -> Response:
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_anon_key = os.environ.get("SUPABASE_ANON_KEY", "").strip()
    relay_url = _public_relay_url()
    body = (
        "window.BLIND_MONKEY_CONFIG = "
        + __import__("json").dumps(
            {
                "supabaseUrl": supabase_url,
                "supabaseAnonKey": supabase_anon_key,
                "relayUrl": relay_url,
                "accountPairing": bool(supabase_url and supabase_anon_key and relay_url),
            }
        )
        + ";\n"
    )
    return Response(body, media_type="application/javascript")


@app.get("/")
async def phone_app() -> FileResponse:
    return FileResponse(
        PHONE_DIR / "index.html",
        headers={"Cache-Control": "no-store"},
    )


@app.websocket("/relay/mac/{device_id}")
async def relay_mac(
    websocket: WebSocket,
    device_id: str,
    token: str | None = None,
    access_token: str | None = None,
) -> None:
    await _handle_connection(
        websocket,
        role="mac",
        device_id=device_id,
        token=access_token or token,
    )


@app.websocket("/relay/phone/{device_id}")
async def relay_phone(
    websocket: WebSocket,
    device_id: str,
    token: str | None = None,
    access_token: str | None = None,
) -> None:
    await _handle_connection(
        websocket,
        role="phone",
        device_id=device_id,
        token=access_token or token,
    )


def main() -> None:
    import uvicorn

    port = int(os.environ.get("PORT", os.environ.get("BLIND_RELAY_PORT", "8765")))
    uvicorn.run("relay.main:app", host="0.0.0.0", port=port)


app.mount("/", StaticFiles(directory=str(PHONE_DIR)), name="phone-static")


if __name__ == "__main__":
    main()
