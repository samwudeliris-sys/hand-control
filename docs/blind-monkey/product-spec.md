# Blind Monkey Product Spec

## One-Line Product

Blind Monkey turns an iPhone into a voice and touch remote for a user's own Mac, optimized for dictating into Cursor and moving between active coding agents without sitting at the keyboard.

## Target User

- Developers using Cursor on macOS.
- Solo builders and agency operators who run multiple Cursor windows or agents.
- Users who want to walk around, think out loud, and send messages to a selected Cursor window from their phone.

The first shippable version is Mac-only. Windows support is out of scope for v1.

## Core User Promise

The user installs Blind Monkey on their iPhone and Mac, pairs them once, and then can open the iPhone app any time to:

1. See their paired Mac.
2. Swipe between available Cursor windows.
3. Tap a recording card to dictate.
4. Tap again to stop.
5. Have the transcript automatically sent to the selected Cursor window.
6. Use the lower half of the phone as a trackpad when they need to click or focus something manually.

## Primary Jobs To Be Done

- "I want to talk to a Cursor agent while pacing or away from my desk."
- "I want to switch between Cursor windows from my phone."
- "I want a phone microphone that sends my words into the right Cursor window."
- "I want enough trackpad control to fix focus or click a UI element without returning to the Mac."
- "I do not want to configure Tailscale, certificates, local IP addresses, or terminal commands."

## User-Facing App Names

- iPhone app: `Blind Monkey`.
- Mac app: `Blind Monkey Mac`.
- Backend/service: `Blind Monkey`.

Avoid user-facing references to `Hand Control`, Tailscale, OpenAI keys, raw WebSocket URLs, or environment variables.

## Onboarding Flow

### iPhone App

1. Welcome screen: explains "Voice and touch remote for your own Mac."
2. Sign in with Apple.
3. Microphone permission primer.
4. Local network permission primer.
5. Pairing screen with camera scanner and manual code entry.
6. First paired Mac appears as a card.
7. Short interactive tutorial:
   - Swipe between Cursor windows.
   - Tap to record.
   - Tap again to send.
   - Use the trackpad area to click/focus.

### Mac Companion

1. Download from website.
2. Open app and sign in with Apple.
3. Show pairing QR and short code.
4. Guide the user through macOS permissions:
   - Accessibility for keyboard/mouse control.
   - Automation/System Events for Cursor window discovery, if needed.
   - Local network if a native Mac framework requires it.
5. Confirm Cursor is detected.
6. Confirm the iPhone is paired.
7. Menu bar status becomes `Ready`.

## Main iPhone Screens

### Home / Control Screen

- Top status: connected Mac, local/remote connection state, battery-friendly status.
- Top half: swipeable Cursor window cards.
- Recording card:
  - Idle: "Tap to talk."
  - Recording: visible recording animation and small `X` cancel button on the right.
  - Transcribing: compact progress animation.
  - Submitted: small non-blocking corner toast.
- Bottom half: trackpad.

### Pairing Screen

- Camera scanner for Mac QR.
- Manual code entry fallback.
- Shows paired Macs after success.

### Settings

- Account.
- Paired Macs.
- Subscription/plan.
- Privacy controls.
- Support and troubleshooting.
- Delete account.

## Recording Behavior

- Microphone must only activate after a clear user action.
- The user must always see a visible recording state.
- The app must release the microphone immediately after stop/cancel.
- Cancel must discard audio and not send it for transcription.
- By default, audio is not stored after transcription.
- Empty transcripts should not send anything.

## Trackpad Behavior

- One-finger move controls cursor movement.
- One-finger tap left-clicks.
- Two-finger tap right-clicks.
- Two-finger drag scrolls.
- Trackpad is user-controlled only; no hidden clicks.

## Cursor Control Behavior

- The Mac companion lists Cursor windows.
- The iPhone app shows them as cards.
- Selecting a card focuses that Cursor window.
- Dictation sends text to the selected window.
- The system should not force-open or toggle Cursor UI panels.
- If focus is wrong, the user can use the phone trackpad to click the desired input.

## App Store Positioning

Recommended description:

> Blind Monkey lets you use your iPhone as a voice and touch remote for your own Mac. Pair your Mac companion app, choose a Cursor window, dictate from your phone, and keep moving.

Avoid:

- "Control any computer."
- "Remote control without permission."
- "Automate other apps invisibly."
- "Hack Cursor."

## Review Notes For Apple

Include:

- Mac companion download URL.
- Step-by-step pairing instructions.
- Test account.
- Explanation that the app controls only a paired Mac the user owns.
- Explanation that recording is user-initiated and visible.
- Explanation that audio is transcribed by the backend and not stored by default.
- Support contact and privacy policy URL.

## Approval Risks And Mitigations

- Microphone access: show a permission primer and record only during explicit action.
- Local network access: explain it is used to find the user's paired Mac.
- Remote control concerns: use explicit pairing and clear in-app status.
- Third-party transcription: disclose in privacy labels and policy.
- Billing: use Apple-compliant purchase flow for iOS digital features.

## V1 Acceptance Criteria

- A new user can install both apps and pair in under three minutes.
- No Tailscale, terminal command, certificate trust flow, or manual URL typing is required.
- The iPhone app can control a paired Mac on local Wi-Fi.
- The iPhone app can control a paired Mac remotely through backend relay.
- Dictation is billed/metered through the backend, not a client-shipped API key.
- App review demo can be completed from a clean Mac and iPhone.
