# Hand Control

**Your phone, as a remote for dictating into multiple Cursor windows.**

Turn your phone into a touch-screen remote that lets you:

1. See every open Cursor window as a swipeable card.
2. Swipe to pick which window you want to talk to.
3. Press-and-hold anywhere on the card to dictate into it.
4. Let go — Wispr Flow transcribes and types into the window.
5. Two buttons light up at the bottom:
   - **Submit** → presses Option+Enter (queues the message in Cursor)
   - **Delete** → presses Cmd+Z (undoes the dictation)
6. If Wispr's "press enter" voice command auto-submits for you, the
   phone shows a green "✓ Sent" confirmation and skips the buttons.
7. Tap **Pad** in the header to flip the whole surface into a
   **trackpad** — drag to move the Mac cursor, tap to click. Handy
   when Cursor's chat input isn't focused and you need to click back
   into it without walking back to the keyboard.
8. Tap **Stick** in the header to turn the deck into a **virtual
   joystick**. Touch anywhere on the deck to drop the stick's
   origin there, drag to drive the Mac cursor (the farther you
   drag, the faster the cursor moves), release to stop. A quick
   tap without dragging is a left click. Toggle off to go back to
   normal swipe-and-hold behavior.

Your AirPods (connected to your Mac) are still the mic. The phone is just a
remote control — **no audio ever goes over the network**.

---

## Quick start (Mac)

### What you need

- **macOS** 11 or newer
- **Python 3.10+** — the installer will offer to install it for you
  via Homebrew if it's missing
- **[Cursor](https://cursor.com)** — the app Hand Control drives
- **[Wispr Flow](https://wisprflow.ai)** — for the actual voice-to-
  text; set its dictation hotkey to **Right Option**
- **A phone** (iPhone or Android) on the same Wi-Fi as your Mac

### Install

Open Terminal, paste this:

```bash
git clone https://github.com/samwudeliris-sys/hand-control.git
cd hand-control
./install.sh
```

The installer is a 6-step guided walkthrough — Python check, deps
install, cert pre-generation, `Hand Control.app` bundle build,
Wispr Flow detection, and macOS Accessibility prompt. Everything
is idempotent — rerun any time.

### Launch

Cmd+Space → type **Hand Control** → Return. A Terminal window opens
with a QR code. Scan it with your iPhone camera and tap the
notification to open the phone remote.

**One-time on your phone (~45 seconds)** — stop Safari nagging
"Not Private" on every launch:

1. Visit `https://<your-mac>.local:8000/install` (the banner on
   the Mac prints the exact URL).
2. Tap **Download cert** → Safari asks if you want to download a
   configuration profile → **Allow**.
3. Open **Settings** → at the top tap **Profile Downloaded** →
   **Install** → passcode → **Install** → **Done**.
4. **Settings → General → About → Certificate Trust Settings** →
   toggle **Hand Control** on.

Reload the Hand Control tab. Warning gone forever. Tap the
Safari share icon → **Add to Home Screen** for a proper app icon.

**That's it.** Swipe between Cursor windows, press-and-hold to
dictate, tap **Submit** to queue the message in Cursor.

Right-click the Dock icon → *Options → Keep in Dock* for one-click
future launches.

### Running from the terminal directly

You can still do `./run.sh` from the repo directory — that's what
the `.app` calls internally, and is useful for debugging.

---

## Want to control a Windows PC too?

If you also have a PC next to your Mac, Hand Control can drive both
from the same phone remote — one unified deck of Cursor windows
from both machines, and a trackpad that edge-crosses between them.

On the **PC**, clone the repo and run:

```
peer\install.bat
```

That sets up Python deps, creates a Start Menu + Desktop shortcut,
and prints the two lines you paste into your **Mac's** Terminal
before `./run.sh`:

```bash
export HC_PEER_URL=http://<PC-hostname>:8001
export HC_PC_SIDE=left    # or right / above / below
```

See the full walkthrough in **"Two-machine mode (Mac + PC)"** below.

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
5. A global `CGEventTap` watches keystrokes. When Wispr has been quiet
   for 400ms (i.e., finished typing), the server tells the phone the
   Submit / Delete buttons are ready. For apps that don't route
   dictated text through visible keystrokes (Cursor's chat input, most
   Electron apps), the server falls back to a heuristic delay based on
   how long you held — typically 0.4–2s.
6. You tap one:
   - **Submit** → server presses **Option+Enter** — Cursor's
     "queue message" shortcut. If the agent is busy, your message
     is appended to the queue to run after the current task finishes.
     If the agent is idle, it just submits normally.
   - **Delete** → server presses Cmd+Z to undo Wispr's insertion.
7. If Wispr's "press enter" voice command auto-submitted for you
   (i.e. you said "...press enter" at the end of your dictation), the
   server notices the Return keystroke and the phone shows a green
   "✓ Sent via 'press enter'" confirmation instead — no buttons to tap.

If you'd rather have Submit interrupt the current agent run, set
`QUEUE_INSTEAD_OF_INTERRUPT = False` in `server/main.py` to fall back
to plain Enter.

> **Why no transcription preview on the phone?**
> An earlier version of Hand Control tried to show the transcribed
> text on the phone by reading Cursor's chat input via the macOS
> Accessibility API. Cursor (like most Electron apps) hides its text
> content from external AX observers, and Wispr's text insertion
> doesn't always generate visible keystrokes. The result was false
> "no text detected" warnings on dictations that actually worked.
> Rather than show unreliable data, the phone now just shows the
> Submit / Delete buttons and trusts you to glance at your Mac.

---

## Setup reference

The **Quick start** above is the path most people should follow.
Below is the longer-form detail if something goes sideways or you
want to understand what's happening.

### macOS permissions in detail

Hand Control needs two macOS permissions. `install.sh` opens the
Accessibility pane for you; the Automation prompt appears the
first time you launch.

**1. Accessibility** — *System Settings → Privacy & Security →
Accessibility.* Enable the terminal app you launched `./run.sh` or
`Hand Control.app` from (Terminal.app, iTerm, etc.). This is what
lets the server simulate key presses on your behalf. If you don't
see the app listed, run `./run.sh` once first to trigger the prompt,
then enable it and restart the server.

**2. Automation → System Events** — the first time Hand Control
lists your Cursor windows, macOS will prompt: *"Terminal wants
access to control System Events."* Click **OK**. If you accidentally
click Don't Allow, fix it at *System Settings → Privacy & Security →
Automation → your terminal → enable System Events.*

### Wispr Flow configuration

- **Activation hotkey** → `Right Option` (the Alt/Option key on the
  right side of your keyboard). Chosen because it's a single
  physical key, rarely bound to anything else, and cleanly
  simulatable programmatically (unlike `Fn`).
- **Input device** → your AirPods, or "System default" if your
  AirPods are already the Mac's default mic.

### The HTTPS cert, in more detail

The server uses HTTPS with a self-signed cert so the phone PWA runs
in a "secure context" (required for reliable bookmark/service-worker
behavior on iOS). `install.sh` pre-generates the cert so the
`/install` cert-trust flow works the first time you open the URL.

The cert is a self-signed CA (`basicConstraints: CA:TRUE`) — this
is what makes iOS's **Certificate Trust Settings** toggle actually
enable full SSL trust for the installed profile. It's stored in
`./certs/server.crt` on your Mac, valid for 5 years, and only
regenerated if your Mac's Bonjour hostname changes. Switching
Wi-Fi networks does **not** invalidate the cert.

### Stable URL

The banner prints a stable `.local` URL like
`https://MacBook-Air.local:8000`. That's your Mac's Bonjour/mDNS
hostname — it stays the same across networks and DHCP renewals.
Bookmark it once on your phone and it keeps working.

### Add to Home Screen

In Safari, tap the Share button → **Add to Home Screen**. Hand
Control has a proper PWA manifest, so launching from the home
screen icon:

- opens **fullscreen** (no browser bars)
- **locks to landscape**
- uses the app icon and name "Hand Control"

If you had an old HTTP bookmark from a previous version, remove it
and re-add from the new `https://…` URL.

---

## Using it

The phone UI has two modes toggled by the **Deck** / **Pad** tabs in
the top-right of the header.

### Deck mode (dictate)

```
┌─────────────────────────────────────────────────────┐
│ ● CONNECTED     [DECK][pad]        ━━ ○ ○ ○        │   ← status · tabs · pager
│ (Push) (Continue) (Fix) (Tests) (Plan) (Approve)    │   ← preset pills
├─────┬─────────────────────────────────────────┬─────┤
│     │                                         │     │
│peek │                                         │ peek│
│ ◂▬▸ │            PROJECT-A                    │ ◂▬▸ │
│     │                                         │     │
│     │           ●   hold to talk              │     │
│     │                                         │     │
│     ├──────────────────┬──────────────────────┤     │
│     │      DELETE      │       SUBMIT         │     │
│     │       (✕)        │        (↵)           │     │
└─────┴──────────────────┴──────────────────────┴─────┘
```

- **Pager dots** (top right) — one dot per Cursor window, active dot
  stretches into an accent-colored pill. Tap a dot to jump directly.
- **Preset pills** (below status bar) — one-tap canned prompts (see
  [Presets](#presets) below). Fully customizable.
- **Card deck** (main area) — one full-bleed card per Cursor window.
  Adjacent cards peek at the edges so you always know there's more.
  - **Swipe horizontally** → glide to the previous / next card.
  - **Press and hold** anywhere on the card → dictate into that window.
    A short (~140 ms) commit delay disambiguates swipe from hold
    automatically; it feels instant.
  - When you hold, the active card glows accent-red and a pulse
    ripples outward so you can tell at a glance the mic is live.
- **Bottom buttons** — light up after Wispr finishes typing:
  - **Delete (✕)** — tap to undo (Cmd+Z).
  - **Submit (↵)** — tap to send Option+Enter.
- **Green "✓ Sent" pill** — appears inside the card when Wispr's
  "press enter" voice command already submitted the message, then
  auto-dismisses after a few seconds.

Changing card — whether by swipe or pager-dot tap — also raises that
Cursor window to the front on your Mac, so you always see which one
you're about to dictate to.

While waiting for Wispr to finish, the buttons pulse; once ready, they
become solid and tappable.

### Pad mode (trackpad)

Tap **Pad** in the header to turn the phone into a trackpad for the
Mac cursor. Useful when Cursor's chat input has lost focus — a quick
tap to click it back, then flip to Deck and keep dictating.

```
┌─────────────────────────────────────────────────────┐
│ ● CONNECTED     [deck][PAD]                         │
├─────────────────────────────────────────────────────┤
│  ╭───────────────────────────────────────────────╮  │
│  │                                               │  │
│  │              · · · · · · · · · · ·            │  │
│  │                                               │  │
│  │                 TRACKPAD                      │  │
│  │      drag to move · tap to click              │  │
│  │           two fingers to scroll               │  │
│  │                                               │  │
│  │              · · · · · · · · · · ·            │  │
│  │                                               │  │
│  ╰───────────────────────────────────────────────╯  │
├──────────────────┬──────────────────────────────────┤
│     L-CLICK      │          R-CLICK                 │
└──────────────────┴──────────────────────────────────┘
```

- **Drag** anywhere on the pad → moves the Mac cursor (sensitivity ≈ 2×).
- **Tap** (quick down-up, no drag) → left click at the cursor's position.
- **Two-finger drag** → scroll (follows macOS natural-scroll direction).
- **L-Click / R-Click** buttons at the bottom → explicit left / right
  click. Always available; handy when you want to right-click without
  a second finger.

Pad mode cleanly suspends any in-flight dictation (releases Right
Option, resets the post-dictation state), so flipping between modes
is always safe.

### Joystick mode (on the Deck page)

Tap the **Stick** pill in the header (next to the Deck / Pad tabs
while you're on the Deck page). The deck turns into a virtual
joystick — think of it as a dedicated left-stick surface, no
calibration, no sensors, no nonsense.

- **Touch anywhere on the deck** → the stick's origin drops right
  under your thumb (you see a translucent ring + center nub).
- **Drag out from the origin** → the Mac cursor moves in that
  direction at a speed proportional to how far you've dragged
  (ease-in curve, so small offsets feel gentle and full-throw
  gives you top speed). There's a small dead zone around the
  origin to keep a resting thumb from sliding the cursor.
- **Release** → stick disappears, cursor stops immediately.
- **Quick tap without dragging** → left click at the current
  cursor position.
- **Tap Stick again** → toggle off; cards return to swipe + hold.

Under the hood, the phone computes a per-frame pixel delta based
on the current stick offset (`RAF` at ~60/120 Hz) and ships
`{type:'mouse_move', dx, dy}` messages to the Mac, which posts them
as `kCGEventMouseMoved` events. Same wire format and server code
path as Pad mode — the only thing new is the on-deck input.

Swipe-to-change-card and hold-to-dictate are suspended while
joystick is on (the deck is a dedicated control surface). Use the
**pager dots** at the top-right of the header to switch cards, or
toggle the stick off.

---

## Two-machine mode (Mac + PC)

Running Hand Control on a **Mac + Windows PC sitting side by side** turns
the phone into a universal controller. Key abilities:

- **Unified card deck** — Cursor windows from *both* machines appear in
  the same swipeable deck, each tagged with a `MAC` or `PC` badge. Hold
  to dictate works on either machine (each runs its own Wispr Flow).
- **Edge-crossing trackpad** — in Pad mode, drag the Mac cursor off
  the configured edge and it seamlessly picks up on the PC. A pill in
  the corner of the trackpad (`MAC` / `PC`) shows which machine
  currently owns the cursor.
- **Preset prompts** — one-tap presets fire against whichever card
  you have selected, on whichever machine it lives on.

### Setup

1. **Clone** the repo on *both* machines (same branch).

2. **On the Windows PC**, one-command install:

   ```
   peer\install.bat
   ```

   It checks Python (with a helpful download link if missing),
   creates the venv, installs `fastapi`, `pynput`, `pywin32`,
   creates Start Menu + Desktop shortcuts for the peer, and prints
   the exact two lines to paste on your Mac.

   Then configure **Wispr Flow on Windows** to use **Right Alt**
   as its dictation hotkey (Settings → Shortcuts → Dictation).
   Launch the peer by clicking the new **Hand Control Peer**
   desktop shortcut (or run `peer\run.bat`).

3. **On the Mac**, paste the two lines the PC printed, then run:

   ```bash
   export HC_PEER_URL=http://<PC-hostname>:8001
   export HC_PC_SIDE=left      # or right / above / below
   ./run.sh
   ```

4. **On your phone:** reload the PWA. You'll see `MAC` / `PC`
   badges on every card in the deck, and Pad mode will show a
   `MAC` / `PC` pill indicating which machine currently owns
   the cursor.

### Network basics

Both machines must be on the **same LAN**. Use the PC hostname if
Bonjour is installed on the PC (e.g. via iTunes or Spotify), or a
static LAN IP otherwise. The peer agent prints both options at
startup.

### Optional: shared-secret auth

For shared living spaces, set the same `HC_PEER_TOKEN` on both
machines. The Mac sends it as a header; the PC rejects requests
without it. Skip this on a home network.

## Configuration

### Change the "Wispr is done" detection delay

Edit the defaults on `KeystrokeWatcher.wait_for_typing_to_settle` in
`server/keystroke_watcher.py`:

```python
idle_ms=400,              # how long Wispr must be quiet before buttons light up
first_key_timeout_s=2.5,  # give up waiting for the first keystroke after this
max_wait_s=10.0,          # hard cap on total wait
```

When the event tap can see Wispr's keystrokes, these knobs control when
the Submit / Delete buttons appear. When it can't (Cursor's chat input,
most Electron apps), the server falls back to a heuristic
`0.4s + 30% of hold duration` instead.

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

### Presets

Presets are one-tap buttons on the phone that type a canned prompt into
the currently-selected Cursor window. They're perfect for the tiny
handful of phrases you repeat all day (`continue`, `please fix it`,
`commit and push to github`, etc.) so you don't have to dictate them
every time.

**Built-in defaults** (shown in the preset row out of the box):

| Label | What it types | Submit |
| --- | --- | --- |
| Push | `commit all changes with a clear, concise message and push to github` | queue |
| Continue | `continue` | send |
| Fix | `please fix it` | send |
| Tests | `run the tests and fix any failures` | queue |
| Plan | `before making changes, lay out a short step-by-step plan` | queue |
| Approve | `y` | send |

**Customize them:**

```bash
cp presets.example.json presets.json
# Edit presets.json — server reads it on startup
./run.sh
```

`presets.json` is gitignored so your customizations won't collide with
future updates of this repo.

Each preset is an object:

```json
{
  "label": "Push",
  "text": "commit and push",
  "submit": "queue"
}
```

- `label` (required) — short text on the button.
- `text` (required) — what gets typed into the focused field.
- `submit` (optional, default `"queue"`) — one of:
  - `"queue"` — press **Option+Enter** after typing, so Cursor appends
    the message to the agent's queue instead of interrupting.
  - `"send"` — press plain **Enter**. Submits immediately; may
    interrupt an agent that's currently running.
  - `"none"` — just type; leave the field for further editing.

You can also point to a preset file outside the repo with
`HC_PRESETS_PATH=/path/to/my-presets.json ./run.sh`.

To debug a custom file, hit `https://<mac>.local:8000/presets` from any
browser on your LAN to see exactly what the server loaded.

---

## Troubleshooting

**The server prints `Failed to create event tap`.**
Accessibility permission isn't granted, or the terminal binary that's
actually running Python doesn't have it. Check System Settings →
Accessibility, make sure your terminal app is enabled, then restart the
server. Without the event tap, the server falls back to a heuristic
delay before lighting up the Submit / Delete buttons — it still works,
just less precisely.

**Phone shows "No Cursor windows detected".**
Either Cursor isn't running, or Automation permission for System Events
isn't granted. Open **System Settings → Privacy & Security → Automation**
and enable "System Events" under your terminal.

**Phone can't reach the URL.**
Make sure both devices are on the same Wi-Fi. Some guest / corporate
networks isolate clients — try a personal hotspot to confirm. macOS
firewall may also need to allow incoming connections to Python.

**Phone says "This Connection Is Not Private" every single launch.**
That's Safari not trusting the self-signed cert. Permanent fix:
open **`https://<your-mac>.local:8000/install`** on the phone and
follow the 4-step install (see the note under the "Open it on your
phone" step, above). After the cert is installed and fully trusted,
Safari never nags again. The cert lives in `./certs/` on your Mac,
never leaves your machine, is marked as a self-signed CA (so iOS's
Certificate Trust Settings toggle actually enables SSL trust for
it), and stays valid for 5 years. It's only regenerated if your
Mac's Bonjour hostname changes — adding a new Wi-Fi network does
**not** invalidate your installed cert.

**I installed the cert but Safari still shows the warning.**
Two common causes: (1) you installed the profile but didn't enable
full trust. Go to **Settings → General → About → Certificate Trust
Settings** and toggle **Hand Control** on. (2) You renamed your
Mac (which changes the `.local` hostname) after installing the
cert. The cert gets regenerated — delete the old Hand Control
profile in **Settings → General → VPN & Device Management** and
re-run the `/install` flow.

**Joystick nub doesn't appear when I touch the deck.**
Make sure the **Stick** pill is lit (accent color, filled dot).
If it's off, the deck is in its normal swipe/hold mode. Also
confirm you're on the **Deck** tab, not **Pad** — the stick is
deck-only, since the Pad tab already provides a full trackpad.

**Cursor moves but in the wrong direction.**
The joystick is rate-based and relative: drag direction from your
touch origin = cursor direction. If you expected "touch a spot,
cursor jumps there", that's not this mode — use the **Pad** tab
for absolute-style dragging.

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
Adjust the defaults on `wait_for_typing_to_settle` in
`server/keystroke_watcher.py`. For slower / longer transcriptions, try
`idle_ms=600` — `800`.

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
  key_control.py           CoreGraphics: simulate keys (Right Option,
                           Enter, Option+Enter, Cmd+Z, Unicode typing)
  keystroke_watcher.py     CGEventTap: detect when Wispr stops typing
                           and when Wispr auto-presses Return
  mouse_control.py         CoreGraphics: simulate cursor moves, clicks,
                           and scroll wheel events (trackpad mode)
  peer.py                  HTTP client for the Windows peer agent
                           (window polling, mouse forwarding, dictation)
  virtual_cursor.py        Virtual cursor state for cross-machine
                           edge crossing (Mac + PC unified coords)
  presets.py               Load + validate one-tap preset prompts
peer/
  main.py                  FastAPI app (runs on the Windows PC)
  windows_ops.py           Windows port of keys / mouse / windows /
                           keystroke watcher (pynput + pywin32)
  run.bat                  Windows bootstrap — venv + deps + server
  requirements.txt         Windows-specific dependencies
phone/
  index.html               Single-file landscape remote UI
  manifest.json            PWA manifest (fullscreen, landscape-locked)
  icon-180.png             Apple Touch icon
  icon-192.png             PWA icon
  icon-512.png             PWA icon
scripts/
  make_icons.py            Regenerate icons (stdlib-only, no deps)
presets.example.json       Starter set of one-tap presets; copy to
                           presets.json and edit to customize
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
