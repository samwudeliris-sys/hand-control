#!/usr/bin/env python3
"""Print or share the Blind Monkey phone URL without starting the server."""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from server.certs import ensure_cert


def get_lan_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except Exception:
        return "127.0.0.1"


def get_mdns_hostname() -> str | None:
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


def resolve_port() -> int:
    raw = os.environ.get("PORT", "8000").strip()
    try:
        return int(raw)
    except ValueError:
        return 8000


def choose_phone_url() -> str:
    port = resolve_port()
    ip = get_lan_ip()
    hostname = get_mdns_hostname()

    try:
        ensure_cert()
        scheme = "https"
    except Exception:
        scheme = "http"

    qr_override = os.environ.get("HC_QR_HOST", "").strip().rstrip(".")
    if qr_override:
        base_url = f"{scheme}://{qr_override}:{port}"
    elif os.environ.get("BLIND_PHONE_APP_URL", "").strip():
        base_url = os.environ["BLIND_PHONE_APP_URL"].strip()
    elif hostname:
        base_url = f"{scheme}://{hostname}:{port}"
    else:
        base_url = f"{scheme}://{ip}:{port}"

    relay = os.environ.get("BLIND_RELAY_URL", "").strip()
    device = os.environ.get("BLIND_DEVICE_ID", "").strip()
    token = os.environ.get("BLIND_RELAY_TOKEN", "").strip()
    account_pairing = bool(
        os.environ.get("SUPABASE_URL", "").strip()
        and os.environ.get("SUPABASE_ANON_KEY", "").strip()
        and relay
    )
    if relay and device and token and not account_pairing:
        parts = urlsplit(base_url)
        query = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key not in {"relay", "device", "token"}
        ]
        query.extend([("relay", relay), ("device", device), ("token", token)])
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
        )

    return base_url


def print_qr(phone_url: str, running: bool = True) -> None:
    if running:
        print("\nBlind Monkey is already running.")
    print(f"Scan with your phone camera -> {phone_url}\n")
    try:
        import qrcode  # type: ignore

        qr = qrcode.QRCode(
            border=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
        )
        qr.add_data(phone_url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
        print("")
    except Exception as exc:
        print(f"[qr] couldn't draw QR: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--running", action="store_true")
    args = parser.parse_args()

    phone_url = choose_phone_url()
    print_qr(phone_url, running=args.running)


if __name__ == "__main__":
    main()
