"""Outbound Blind Monkey relay client for the Mac control server."""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from typing import cast
from urllib.parse import quote, urlencode

import httpx
import websockets

Packet = dict[str, object]


class RelayClientConnection:
    def __init__(self, websocket: websockets.WebSocketClientProtocol) -> None:
        self.websocket = websocket

    async def send_text(self, message: str) -> None:
        await self.websocket.send(message)

    async def close(self) -> None:
        await self.websocket.close()


async def _mint_relay_session_token(base: str, supabase_access_token: str) -> str | None:
    mint_url = f"{base}/v1/relay/sessions"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                mint_url,
                json={"role": "mac"},
                headers={"Authorization": f"Bearer {supabase_access_token}"},
            )
        response.raise_for_status()
        data = cast(dict[str, object], response.json())
        minted = data.get("access_token")
        if isinstance(minted, str) and minted:
            print("[relay] minted short-lived relay session token")
            return minted
    except Exception as exc:
        print(f"[relay] session mint failed (using bearer as-is): {exc}")
    return None


async def connect_relay_forever(
    *,
    relay_url: str,
    device_id: str,
    token: str,
    mint_relay_session: bool = False,
    on_connect: Callable[[RelayClientConnection], Awaitable[None]],
    on_packet: Callable[[RelayClientConnection, Packet], Awaitable[None]],
    on_disconnect: Callable[[RelayClientConnection], Awaitable[None]],
) -> None:
    base = relay_url.rstrip("/")
    want_mint = mint_relay_session and os.environ.get(
        "BLIND_PREFER_RELAY_SESSION", "1"
    ).lower() in ("1", "true", "yes")
    delay = 1.0

    while True:
        conn: RelayClientConnection | None = None
        try:
            token_use = token
            if want_mint:
                minted = await _mint_relay_session_token(base, token)
                if minted:
                    token_use = minted
            query = urlencode({"access_token": token_use})
            url = f"{base}/relay/mac/{quote(device_id)}?{query}"
            print(f"[relay] connecting to {base} as {device_id}")
            async with websockets.connect(url, max_size=None) as websocket:
                conn = RelayClientConnection(websocket)
                await on_connect(conn)
                print("[relay] connected")
                delay = 1.0

                async for message in websocket:
                    if isinstance(message, bytes):
                        await on_packet(conn, {"bytes": message})
                    else:
                        await on_packet(conn, {"text": message})
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"[relay] disconnected: {exc}")
        finally:
            if conn is not None:
                await on_disconnect(conn)

        await asyncio.sleep(delay)
        delay = min(delay * 1.6, 20.0)
