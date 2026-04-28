# Hand Control

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20peer-lightgrey.svg)](./peer/README.md)

**Your phone, as a mic + remote for dictating into multiple Cursor windows.**

Public repo: **[github.com/spdoub/cursor-hand-control](https://github.com/spdoub/cursor-hand-control)** (formerly `hand-control`).

Turn your phone into a touch-screen remote that lets you:

1. See every open Cursor window as a swipeable card.
2. Swipe to pick which window you want to talk to.
3. Press-and-hold anywhere on the card to dictate into it — your
   **phone's microphone** is recording.
4. Let go — the audio uploads to your Mac, gets transcribed by OpenAI
   Whisper, and the text appears in an editable textarea on your
   phone a second later.
5. Two buttons at the bottom:
   - **Send (↵)** → pastes the (possibly edited) text into the
     selected Cursor window and queues it with Option+Enter.
   - **X** → first tap clears the textarea so you can re-type or
     re-hold; second tap cancels the whole utterance.
6. By default, Hand Control leaves Cursor's current layout alone when
   you switch windows. If you want the old "try to jump straight into
   chat" behavior, you can opt into it with `HC_AUTO_FOCUS_CHAT=1`
   (see configuration below).
7. Tap **Pad** in the header to flip the whole surface into a
   **trackpad** — drag to move the Mac cursor, tap to click.
8. Tap **Stick** in the header to turn the deck into a **virtual
   joystick**. Touch anywhere on the deck to drop the stick's
   origin there, drag to drive the Mac cursor (the farther you
   drag, the faster the cursor moves), release to stop. A quick
   tap without dragging is a left click. Toggle off to go back to
   normal swipe-and-hold behavior.

The phone becomes the mic; your AirPods (or any other Mac mic) aren't
involved in this flow. If you're just coding on your Mac without the
phone in hand, you can still use **Wispr Flow** as usual — Hand
Control doesn't touch the Right Option key when no phone is driving.

---

## Quick start (Mac)

### What you need

- **macOS** 11 or newer
- **Python 3.10+** — the installer will offer to install it for you
  via Homebrew if it's missing
- **[Cursor](https://cursor.com)** — the app Hand Control drives
- An **OpenAI API key** — the phone's mic is transcribed via
  [Whisper](https://platform.openai.com/docs/guides/speech-to-text).
  Grab one at [platform.openai.com/api-keys](https://platform.openai.com/api-keys).
  The installer asks for it and writes it to `~/.hand-control.env`
  (gitignored). You can also just export `OPENAI_API_KEY` in your shell.
- **A phone** (iPhone or Android) on the same Wi-Fi as your Mac, or
  connected via [Tailscale](#tailscale) if you're off your home network.
- *(Optional)* **[Wispr Flow](https://wisprflow.ai)** — handy for
  the times you're coding on your Mac without the phone. Hand Control
  doesn't drive Wispr itself; you just use its Right Option hotkey
  directly as you always did.

### Install

Open Terminal, paste this:

```bash
git clone https://github.com/spdoub/cursor-hand-control.git
cd cursor-hand-control
./install.sh
```

The installer is a 6-step guided walkthrough — Python check, deps
install, cert pre-generation, `Hand Control.app` bundle build,
OpenAI API key setup, and macOS Accessibility prompt. Everything
is idempotent — rerun any time.

### Launch

From this doc, click:

<p>
  <a href="./Start%20Blind%20Monkey.command"><strong>Start Blind Monkey</strong></a>
</p>

That shortcut opens Terminal, starts Blind Monkey if it is not already
running, and shows the phone link/QR fallback for this beta. In the
real native version, users will just open the Blind Monkey app on
their phone.

You can also use Spotlight: Cmd+Space → type **Blind Monkey** →
Return. It uses the same launch flow: text the link when configured,
or show the QR fallback.

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
dictate, release, review/edit the transcript that appears, tap
**Send** to queue the message in Cursor.

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

If you juggle multiple Cursor windows and want to dictate into them
while you're away from the keyboard (or even just lounging on the
couch), you know the dance: walk back to the Mac, click into the
right window, click the chat box, dictate, tap Enter. Hand Control
collapses all of that into a single touch-and-hold on your phone.
You can be on the couch or even on another network — as long as the
phone can reach the Mac, you can queue up messages.

---

## How it works

```
┌────────────────────┐      WebSocket       ┌────────────────────────┐
│  Phone (browser)   │                      │  Mac (Python server)   │
│  • mic capture     │ ───── audio blob ──► │                        │
│  • level meter     │                      │  ┌──────────────────┐  │
│  • transcript edit │ ◄──  transcript ──── │  │ OpenAI Whisper   │  │
│  • Send / X        │                      │  │ (HTTPS API)      │  │
└────────────────────┘ ───── text on send ► │  └──────────────────┘  │
                                            │  ┌──────────────────┐  │
                                            │  │ Focus window     │  │
                                            │  │ Cmd+L chat focus │  │
                                            │  │ Paste + Opt+Ent  │  │
                                            │  └──────────────────┘  │
                                            └────────────────────────┘
```

When you hold on a card:

1. Phone requests mic permission (first time only), then starts a
   `MediaRecorder` against `navigator.mediaDevices.getUserMedia`. The
   active card shows a live level meter so you can see the mic is
   actually picking you up.
2. Server focuses the selected Cursor window (AppleScript). If you've
   opted into `HC_AUTO_FOCUS_CHAT=1`, it also presses **Cmd+L** to try
   to move focus into Cursor's chat input.

When you release:

3. Phone stops the recorder, sends the whole audio blob over the
   WebSocket (one binary frame), then a `hold_end` JSON message.
4. Server forwards the blob to OpenAI Whisper. Whisper returns text.
5. Server pushes the text back to the phone. The card flips to an
   editable textarea with the keyboard up.

Now it's your move:

6. **Edit** anything that came out wrong (it's a normal textarea —
   tap, select, backspace, type). The Mac hasn't typed anything yet.
7. **X** wipes the textarea (first tap) or cancels the whole
   utterance (second tap / already-empty).
8. **Send** ships the final text to the Mac, which:
   - focuses the selected Cursor window,
   - pastes the text via the clipboard (unicode-safe, instant),
   - presses **Option+Enter** — Cursor's "queue message" shortcut. If
     the agent is busy, your message is appended to the queue; if
     it's idle, it just submits.

If you'd rather have Send interrupt the current agent run, set
`QUEUE_INSTEAD_OF_INTERRUPT = False` in `server/main.py` to fall back
to plain Enter.

### Using Wispr Flow on the Mac without the phone

Hand Control no longer touches the Right Option modifier, so Wispr
Flow keeps working exactly like it always did — just press Right
Option on your Mac keyboard when you're coding without the phone in
hand. The two flows coexist cleanly.

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

### OpenAI / Whisper configuration

- **`OPENAI_API_KEY`** — required. `install.sh` writes it to
  `~/.hand-control.env`, and `run.sh` sources that file at startup.
  You can also just `export OPENAI_API_KEY=…` in the shell that
  launches `./run.sh`.
- **`HC_TRANSCRIBE_MODEL`** — defaults to `whisper-1`. For higher
  quality and often lower cost on short clips, set it to
  `gpt-4o-mini-transcribe` or `gpt-4o-transcribe`.
- **`HC_TRANSCRIBE_LANGUAGE`** — optional ISO-639-1 hint (e.g. `en`)
  if Whisper keeps mis-detecting your language on noisy short clips.
- **`HC_WHISPER_PROMPT`** — optional bias string (max ~224 tokens for
  `whisper-1`). Useful for nudging toward code-heavy vocabulary:
  `export HC_WHISPER_PROMPT="async, useEffect, FastAPI, kubectl"`.

The phone never records audio to disk and never sends it anywhere
except your Mac; your Mac forwards it to OpenAI over HTTPS.

### Wispr Flow (optional, Mac-only fallback)

Hand Control doesn't drive Wispr at all anymore. If you want to
dictate from the Mac itself without the phone in hand, just install
Wispr Flow and use its Right Option hotkey as normal — the two flows
coexist.

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

### Tailscale

Use this when the phone is not on the same Wi‑Fi. The server already
listens on all interfaces (`0.0.0.0`). With [Tailscale](https://tailscale.com)
on the Mac and the phone:

1. Run **`tailscale up`** on the Mac (and sign in the phone app).
2. Start Hand Control — the banner lists **Tailscale** URLs (MagicDNS
   and `100.x`). The TLS cert **includes** those names automatically
   when Tailscale is running; if you start Tailscale *after* the first
   cert was created, restart Hand Control once so it can regenerate.
3. On the phone, open the **`/install`** URL shown for Tailscale in the
   banner and complete the same cert-trust steps as on LAN — you need
   a profile per hostname you use (`.local` vs Tailscale name).
4. Optional: **`HC_QR_USE_TAILSCALE=1 ./run.sh`** makes the terminal
   QR encode the MagicDNS URL instead of `.local`. **`HC_QR_HOST=…`**
   forces a specific host.

Manual SAN overrides (e.g. CLI can’t see MagicDNS): **`HC_TAILSCALE_DNS`**
and **`HC_TAILSCALE_IP`** (comma-separated).

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
│peek │            PROJECT-A                    │ peek│
│ ◂▬▸ │    ╭───────────────────────────────╮    │ ◂▬▸ │
│     │    │  Hey, could you fix the bug   │    │     │
│     │    │  in foo.py where the async    │    │     │
│     │    │  handler drops the first msg? │    │     │
│     │    ╰───────────────────────────────╯    │     │
│     ├──────────────────┬──────────────────────┤     │
│     │        X         │         SEND         │     │
│     │       (✕)        │         (↵)          │     │
└─────┴──────────────────┴──────────────────────┴─────┘
```

- **Pager dots** (top right) — one dot per Cursor window, active dot
  stretches into an accent-colored pill. Tap a dot to jump directly.
- **Preset pills** (below status bar) — one-tap canned prompts (see
  [Presets](#presets) below). Fully customizable.
- **Card deck** (main area) — one full-bleed card per Cursor window.
  Adjacent cards peek at the edges so you always know there's more.
  - **Swipe horizontally** → glide to the previous / next card.
  - **Press and hold** anywhere on the card → start recording on the
    phone's mic. A short (~140 ms) commit delay disambiguates swipe
    from hold. The card glows accent-red and a live **level meter**
    confirms the mic is picking you up. First hold prompts iOS for
    mic permission — allow it once.
  - **Release** → audio uploads to the Mac, Whisper transcribes, and
    the card flips to an **editable textarea** with the software
    keyboard up. Takes ~1–2 s over LAN/Tailscale.
- **Bottom buttons** (in edit mode):
  - **X (✕)** — first tap clears the textarea; second tap (or tap on
    an already-empty textarea) cancels the utterance entirely.
  - **Send (↵)** — pastes the text into the selected Cursor window
    and presses Option+Enter (queue) / Enter.

Changing card — whether by swipe or pager-dot tap — raises that
Cursor window to the front on your Mac. If you enable
`HC_AUTO_FOCUS_CHAT=1`, Hand Control also tries Cursor's chat-focus
shortcut after the window switch.

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

Pad mode cleanly suspends any in-flight dictation (stops the
recorder, clears the transcript preview), so flipping between modes
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
  the same swipeable deck, each tagged with a `MAC` or `PC` badge.
  Hold to dictate works for either machine; the phone captures audio
  once, transcribes via Whisper on the Mac, then the text is typed into
  whichever machine owns the selected window (via the peer for PC).
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

### Transcription tweaks

See [OpenAI / Whisper configuration](#openai--whisper-configuration)
above for `HC_TRANSCRIBE_MODEL`, `HC_TRANSCRIBE_LANGUAGE`, and
`HC_WHISPER_PROMPT`.

### Enable the legacy auto-focus of Cursor's chat input

Older versions of Hand Control pressed **Cmd+L** after every window
focus so a fresh hold would try to land in Cursor's chat input rather
than the code editor. In newer Cursor layouts, `Cmd+L` can behave like
an AI-sidebar toggle, which means it may close an already-open chat
box. So this behavior is now **off by default**.

If you still want it, opt in with:

```bash
export HC_AUTO_FOCUS_CHAT=1
```

You can also tune the delay between raising the window and firing
the hotkey with `HC_AUTO_FOCUS_CHAT_DELAY_MS` (default `120`).

### Change the target app

Edit `server/cursor_windows.py` — replace `"Cursor"` in the AppleScript
with another app name (e.g., `"Code"` for VS Code, `"iTerm2"` for iTerm).

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

**The server prints `OpenAI: NO KEY`.**
Set `OPENAI_API_KEY` in `~/.hand-control.env` or export it in the
shell that runs `./run.sh`. Dictation needs it; everything else
(swipe, Pad mode, presets) still works without.

**Phone says "Microphone permission denied".**
On iOS: Settings → Safari → Microphone → allow for the Hand Control
site. If you added to Home Screen, the permission is per-PWA — long-
press the icon to delete it, reload the site in Safari, grant mic,
then re-add to Home Screen.

**Transcription error "HTTP 401".**
Invalid or missing OpenAI key. Check `~/.hand-control.env` and retry.

**Transcription is slow.**
Each hold ends with a single Whisper request; round-trip on a good
connection is 1–2 s. If it's routinely >4 s, try
`export HC_TRANSCRIBE_MODEL=gpt-4o-mini-transcribe` which is usually
faster than `whisper-1` on short clips.

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

**Send lands in the code editor, not Cursor's chat input.**
If you have `HC_AUTO_FOCUS_CHAT=1` enabled, the Cmd+L auto-focus may
have fired before Cursor was actually frontmost. Bump the delay:
`HC_AUTO_FOCUS_CHAT_DELAY_MS=200 ./run.sh`.

**Clipboard got overwritten.**
Hand Control saves and restores the clipboard around each paste.
If you notice something missing, it's likely because you copied
something else *during* the ~250 ms paste window. Copy again.

---

## Project structure

```
server/
  main.py                  FastAPI app, WebSocket endpoint, orchestration
  certs.py                 Self-signed TLS certs (Bonjour + Tailscale SANs)
  clipboard.py             NSPasteboard save/restore + Cmd+V paste helper
  transcribe.py            OpenAI Whisper client (httpx, no SDK)
  cursor_windows.py        AppleScript: list + focus Cursor windows
  key_control.py           CoreGraphics: simulate keys (Enter, Option+Enter,
                           Cmd+L, Cmd+Z, Unicode typing)
  keystroke_watcher.py     CGEventTap (kept for optional hotkeys; no longer
                           used in the phone dictation path)
  mouse_control.py         CoreGraphics: simulate cursor moves, clicks,
                           and scroll wheel events (trackpad mode)
  peer.py                  HTTP client for the Windows peer agent
                           (window polling, mouse forwarding, typing)
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
  Run on trusted networks only, or use Tailscale.
- There is no authentication. This is a tool for your own laptop.
- Audio flow: phone → your Mac (WebSocket binary frame) → OpenAI
  Whisper (HTTPS) → transcript back. Audio is held in memory on the
  Mac only long enough to POST it to OpenAI and is never written to
  disk. If you don't want to send audio to OpenAI, don't set
  `OPENAI_API_KEY` and Hand Control's trackpad / preset / window
  focus features still work without dictation.

If you want to use the phone off your home Wi‑Fi, use **Tailscale** on
the Mac and phone — see [Tailscale](#tailscale) above.
Traffic stays inside your tailnet; there is still no login on Hand Control
itself, so only trusted devices should be in that tailnet.

---

## License

MIT. See [LICENSE](./LICENSE).
