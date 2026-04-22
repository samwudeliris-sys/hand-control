# Hand Control

**Your phone, as a remote for dictating into multiple Cursor windows.**

Turn your phone into a touch-screen remote that lets you:

1. See every open Cursor window as a tappable box.
2. Pick which window you want to talk to.
3. Press-and-hold a big button on your phone to dictate into it.
4. Let go — Wispr Flow transcribes and types into the window.
5. When it's done, two buttons at the bottom of your phone light up:
   - **Submit** → presses Option+Enter (queues the message in Cursor)
   - **Delete** → presses Cmd+Z (undoes the dictation)

Your AirPods (connected to your Mac) are still the mic. The phone is just a
remote control — **no audio ever goes over the network**.

---

## Quick start

```bash
git clone https://github.com/samwudeliris-sys/hand-control.git
cd hand-control
./run.sh
```

On first run, grant **Accessibility** and **Automation** permissions when
macOS prompts (full details in [Setup](#setup)), then open the `.local`
URL the server prints on your phone. Add it to your home screen and you
have a landscape remote control app for dictating into Cursor.

**Requires:** macOS, Python 3.10+, Cursor, Wispr Flow (or any hold-to-talk
dictation tool), and a phone on the same Wi-Fi.

---

## Why?

If you dictate code with Wispr Flow and juggle multiple Cursor windows, you
know the dance: click into a window, hold `Fn`, talk, release, press Enter,
repeat for the next window. Hand Control collapses that into a single
touch-and-hold on your phone while you keep your eyes on your Mac screen.

---

## How it works

```
┌────────────────────┐     WebSocket      ┌────────────────────────┐
│   Phone (browser)  │  ◄──────────────►  │  Mac (Python server)   │
│   landscape remote │                    │                        │
└────────────────────┘                    │  ┌──────────────────┐  │
                                          │  │   AppleScript    │  │
                                          │  │ (list + focus    │  │
                                          │  │  Cursor windows) │  │
                                          │  └──────────────────┘  │
                                          │  ┌──────────────────┐  │
                                          │  │  CoreGraphics    │  │
                                          │  │  (simulate Right │  │
                                          │  │  Option + Enter) │  │
                                          │  └──────────────────┘  │
                                          │  ┌──────────────────┐  │
                                          │  │  CGEventTap      │  │
                                          │  │  (know when      │  │
                                          │  │  Wispr stops     │  │
                                          │  │  typing)         │  │
                                          │  └──────────────────┘  │
                                          └────────────────────────┘
                                                     │
                                                     ▼
                                            ┌──────────────────┐
                                            │   Wispr Flow     │
                                            │   (activated by  │
                                            │   Right Option)  │
                                            └──────────────────┘
```

When you hold on the phone:

1. Server focuses the currently-selected Cursor window (AppleScript).
2. Server presses and holds **Right Option** — Wispr Flow's activation
   hotkey.
3. You talk. Your AirPods send audio to your Mac. Wispr transcribes.
4. You release on the phone. Server releases Right Option.
5. A global `CGEventTap` watches keystrokes. When Wispr has been quiet for
   400ms (i.e., finished typing), the server tells the phone, which
   enables the Submit / Delete buttons.
6. You tap one:
   - **Submit** → server presses **Option+Enter** — Cursor's
     "queue message" shortcut. If the agent is busy, your message
     is appended to the queue to run after the current task finishes.
     If the agent is idle, it just submits normally.
   - **Delete** → server presses Cmd+Z to undo Wispr's insertion.

If you'd rather have Submit interrupt the current agent run, set
`QUEUE_INSTEAD_OF_INTERRUPT = False` in `server/main.py` to fall back
to plain Enter.

---

## Requirements

- **macOS** (Apple Silicon or Intel). Uses AppleScript, CoreGraphics,
  CGEventTap — all macOS-only APIs.
- **Python 3.10+** (3.11 or newer recommended).
- **[Cursor](https://cursor.com)** — this is built around focusing Cursor
  windows. Could be adapted to any app with light changes.
- **[Wispr Flow](https://wisprflow.ai)** — or any dictation tool that
  activates on a hold-to-talk hotkey and types into the focused window.
- **A phone** on the same Wi-Fi network. Any phone with a modern browser
  (iOS Safari / Android Chrome).

---

## Setup

> Tip: you can run every command below by pasting it into Terminal.

### 1. Clone and install

```bash
git clone https://github.com/samwudeliris-sys/hand-control.git
cd hand-control
./run.sh
```

`run.sh` will:

- Create a Python virtualenv in `.venv/`
- Install dependencies (`fastapi`, `uvicorn`, `pyobjc`)
- Start the server on port **8000**

Leave it running. The first start will print something like:

```
Hand Control running.

  Phone URL (stable):  http://MacBook-Air.local:8000
  Phone URL (by IP):   http://192.168.1.42:8000

  Bookmark the stable URL on your phone — the .local
  hostname won't change when your Wi-Fi does.
```

Use the **stable URL** (the `.local` one) — it uses your Mac's
Bonjour/mDNS hostname and stays the same across networks and
DHCP renewals. You can bookmark it once and forget about it.

### 2. Configure Wispr Flow

Open Wispr Flow settings and change:

- **Activation hotkey** → `Right Option` (the Option/Alt key on the right
  side of your keyboard).
- **Input device** → your AirPods, or "System default" if your AirPods are
  already the Mac's default mic.

The Right Option key is used because (a) it's a single physical key,
perfect for press-and-hold, (b) it's rarely bound to anything else, and
(c) unlike `Fn`, it can be cleanly simulated programmatically.

### 3. Grant macOS permissions

The server simulates key presses and watches global keystrokes, so it
needs two permissions.

#### A. Accessibility

> **System Settings → Privacy & Security → Accessibility**

Enable the app you launched `./run.sh` from (Terminal.app, iTerm, or
Cursor's built-in terminal).

If you don't see it listed, try running `./run.sh` once first — macOS may
prompt you automatically.

After granting, **restart the server** (`Ctrl+C` and `./run.sh` again).

#### B. Automation → System Events

The first time the server lists your Cursor windows, macOS will prompt:

> "Terminal.app wants access to control System Events."

Click **OK**. (If you accidentally click Don't Allow, fix it at
**System Settings → Privacy & Security → Automation** → your terminal →
enable "System Events".)

### 4. Open the phone UI

On your phone's browser, open the **stable URL** the server printed, e.g.:

```
http://MacBook-Air.local:8000
```

(Substitute your Mac's own hostname, shown in the startup banner.)

Hold your phone in **landscape**.

### 5. Add to Home Screen (recommended)

In Safari (iOS) or Chrome (Android), tap the Share button → **Add to
Home Screen**. Hand Control has a proper PWA manifest, so launching
from the home screen icon:

- opens **fullscreen** (no browser bars)
- **locks to landscape**
- uses the app icon and name "Hand Control"

From then on, it's just an icon on your home screen — tap, hold, talk.

---

## Using it

The phone UI:

```
┌─────────────────────────────────────────────────────┐
│ ●  [ project-a ] [ project-b ] [ project-c ]        │   ← top strip: tap to pick
├─────┬─────────────────────────────────────────┬─────┤
│     │                                         │     │
│  ◀  │           HOLD TO TALK                  │  ▶  │
│     │       (pulses while holding)            │     │
│     │                                         │     │
│     ├──────────────────┬──────────────────────┤     │
│     │     DELETE       │       SUBMIT         │     │
│     │      (✕)         │        (↵)           │     │
└─────┴──────────────────┴──────────────────────┴─────┘
```

- **Top strip** — one box per open Cursor window. Tap to select.
- **Left edge (◀)** — previous window.
- **Right edge (▶)** — next window.
- **Center area** — press and hold to dictate.
- **Bottom buttons** — light up after Wispr finishes typing:
  - **Delete (✕)** — tap to undo (Cmd+Z).
  - **Submit (↵)** — tap to send Enter.

Selecting any window also raises that Cursor window to the front on your
Mac, so you always know which one you're about to dictate to.

While waiting for Wispr to finish, the buttons pulse; once ready, they
become solid and tappable.

---

## Configuration

### Change the "Wispr is done" detection delay

Edit `server/main.py`:

```python
ENTER_IDLE_MS = 400     # how long Wispr must be quiet before buttons light up
ENTER_MAX_WAIT_S = 8.0  # safety cap — give up waiting after this
```

### Change the activation hotkey

Edit `server/key_control.py` — change `KEYCODE_RIGHT_OPTION` to a different
keycode (see
[this list](https://eastmanreference.com/complete-list-of-applescript-key-codes))
and set the matching hotkey in Wispr Flow's settings.

### Change the target app

Edit `server/cursor_windows.py` — replace `"Cursor"` in the AppleScript
with another app name (e.g., `"Code"` for VS Code, `"iTerm2"` for iTerm).

### Control a different hold-to-talk tool

The server is Wispr-agnostic. Any dictation tool that activates on a hold
hotkey and types into the focused window works.

### Run on a different port

Port 8000 is the default. To override:

```bash
PORT=8080 ./run.sh
```

The startup banner updates to show the new URL. If port 8000 is already
in use, the server exits with a friendly message telling you to pick
another port.

---

## Troubleshooting

**The server prints `Failed to create event tap`.**
Accessibility permission isn't granted, or the terminal binary that's
actually running Python doesn't have it. Check System Settings →
Accessibility, make sure your terminal app is enabled, then restart the
server. If Enter never fires, the event tap isn't running — the hard cap
(`ENTER_MAX_WAIT_S`) will still eventually fire Enter.

**Phone shows "No Cursor windows detected".**
Either Cursor isn't running, or Automation permission for System Events
isn't granted. Open **System Settings → Privacy & Security → Automation**
and enable "System Events" under your terminal.

**Phone can't reach the URL.**
Make sure both devices are on the same Wi-Fi. Some guest / corporate
networks isolate clients — try a personal hotspot to confirm. macOS
firewall may also need to allow incoming connections to Python.

**Server says "Port 8000 is already in use."**
Another process is bound to that port (possibly a stale Hand Control).
Either stop the other process or pick a new port:
`PORT=8080 ./run.sh`.

**The `.local` URL doesn't resolve on my phone.**
Some networks block mDNS / Bonjour between clients. Fall back to the IP
URL printed in the banner. If Bonjour works but is slow, it may take
a couple of seconds the first time.

**Holding works but Wispr doesn't start.**
Wispr Flow isn't running, or its hotkey isn't `Right Option`. Double-check
the hotkey in Wispr's settings.

**Submit button lights up too early or too late.**
Adjust `ENTER_IDLE_MS` in `server/main.py`. For slower / longer
transcriptions, try 600–800ms.

**Delete doesn't fully remove the dictation.**
Delete sends Cmd+Z (undo), which works if Wispr pastes text in one shot.
If Wispr simulated keystrokes in a way the app groups differently, Cmd+Z
may only undo part of it. Tap Delete again to continue undoing.

**The server kills any held modifier on disconnect.**
Intentional. If your phone drops Wi-Fi mid-hold, we release Right Option
so you aren't stuck with a modifier pressed forever.

---

## Project structure

```
server/
  main.py                  FastAPI app, WebSocket endpoint, orchestration
  cursor_windows.py        AppleScript: list + focus Cursor windows
  key_control.py           CoreGraphics: simulate Right Option + Enter + Cmd+Z
  keystroke_watcher.py     CGEventTap: detect when Wispr stops typing
phone/
  index.html               Single-file landscape remote UI
  manifest.json            PWA manifest (fullscreen, landscape-locked)
  icon-180.png             Apple Touch icon
  icon-192.png             PWA icon
  icon-512.png             PWA icon
scripts/
  make_icons.py            Regenerate icons (stdlib-only, no deps)
requirements.txt
run.sh                     One-shot bootstrap + run script
```

No build step, no frontend framework, no database. Single
`./run.sh` to go from fresh clone to working remote.

---

## Security notes

- The server binds to `0.0.0.0:8000` so your phone on the LAN can reach
  it. Anyone on the same Wi-Fi network can also reach it — including
  anyone who could type keys into your Cursor windows through it.
  Run on trusted networks only.
- There is no authentication. This is a tool for your own laptop.
- All audio stays on your Mac. The phone never records or transmits
  audio.

If you want to expose this beyond your LAN, put it behind Tailscale — it
"just works" and adds authentication and encryption for free.

---

## License

MIT. See [LICENSE](./LICENSE).
