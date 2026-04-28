# Hand Control — Windows peer agent

This is the Windows companion to the Mac Hand Control server. You
run it on the PC that sits next to your Mac so the phone can drive
mouse, keyboard, and Wispr Flow on both machines from a single deck.

You don't talk to this agent directly from the phone — the Mac server
is the hub, and it forwards events here over HTTP.

## Prerequisites

- **Windows 10 or 11** (x64 or ARM64)
- **Python 3.10+** installed with "Add python.exe to PATH" ticked
- **Wispr Flow** running and signed in
- **Cursor** installed (so it has Cursor windows to focus)

## 1. Install

Clone the full Hand Control repo somewhere on the PC:

```
git clone https://github.com/spdoub/cursor-hand-control.git
cd cursor-hand-control
```

All the Windows-specific code lives in `peer\`.

## 2. Configure Wispr Flow's hotkey

Wispr needs to use the same key your Mac uses (Right Option on Mac
= **Right Alt** on Windows), so the phone's "hold to talk" gesture
feels identical on both machines.

1. Open Wispr Flow on the PC
2. Settings → Shortcuts → Dictation hotkey
3. Set it to **Right Alt** (aka `RAlt`, `AltGr` on some layouts)

If you'd rather use a different key, change the function
`right_alt_down`/`right_alt_up` in `peer\windows_ops.py` to press
whatever key you picked.

## 3. Start the agent

Double-click `peer\run.bat` — or from a terminal:

```
cd cursor-hand-control
peer\run.bat
```

First run will create `peer\.venv` and install dependencies
(FastAPI, pynput, pywin32). Subsequent runs boot in under a second.

You should see a banner like:

```
================================================================
  Hand Control PEER agent running.

  Set on your Mac:  HC_PEER_URL=http://MY-PC:8001
                     or  HC_PEER_URL=http://192.168.1.42:8001
  (no auth — trusted LAN only)
================================================================
```

Copy one of those URLs — you'll paste it on the Mac in step 4.

## 4. Tell the Mac about the PC

On your Mac, edit the environment (e.g. in your shell rc) or set
per-run:

```bash
export HC_PEER_URL=http://MY-PC:8001
export HC_PC_SIDE=left    # or right / above / below — where the PC sits
./run.sh
```

You can also add a shared-secret token on both machines (optional,
good for shared living spaces):

```bash
# On the Mac: export HC_PEER_TOKEN=some-random-string
# On the PC:  set HC_PEER_TOKEN=some-random-string (before running run.bat)
```

That's it — your phone's trackpad will now edge-cross into the PC,
and the card deck will show Cursor windows from both machines.

## Troubleshooting

- **"ImportError: pynput is required"** → the first-run deps install
  failed. Re-run `peer\run.bat`; check the output for pip errors.
- **Cursor doesn't come to the front on the PC** → Windows protects
  foreground-window takeovers from unrelated processes. Click once
  on the PC to "bless" the agent's session, then try again.
- **Wispr doesn't pick up when held from phone** → confirm the
  dictation hotkey is Right Alt (not Left Alt). Test by pressing
  Right Alt on the PC's keyboard directly.
- **Mouse moves feel laggy** → check the Mac ↔ PC ping on LAN:
  `ping <PC-hostname>`. Anything under 5 ms should feel native. If
  you're on Wi-Fi with lots of interference, an ethernet cable to
  the PC fixes it instantly.
- **Port 8001 in use** → run with `set PORT=8002` (and update
  `HC_PEER_URL` on the Mac to match).
