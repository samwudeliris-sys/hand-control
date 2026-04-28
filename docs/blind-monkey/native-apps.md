# Blind Monkey Native App Milestones

## Scope

First public version:

- Native iPhone app in SwiftUI.
- Native Mac companion app in Swift/SwiftUI or AppKit.
- Mac-only companion support.
- Built-in backend relay for remote use.
- No Tailscale requirement.

## iPhone App Architecture

Recommended modules:

- `AppShell`: navigation, app lifecycle, deep links.
- `Auth`: Sign in with Apple, token storage, account state.
- `Pairing`: QR scanner, manual code entry, paired Mac list.
- `Control`: window cards, recording, trackpad.
- `Audio`: microphone capture, encoding, upload.
- `Relay`: local and remote command transport.
- `Billing`: entitlement and plan state.
- `Settings`: devices, privacy, support, delete account.

## iPhone Milestone 1: Project Foundation

- Create SwiftUI app target.
- Add App Store-safe bundle name: `Blind Monkey`.
- Add app icon and launch screen.
- Configure capabilities:
  - Sign in with Apple.
  - Local Network.
  - Microphone.
  - Camera, if pairing QR scanner is in-app.
- Add Keychain wrapper.
- Add environment config for dev/staging/prod API.

Definition of done:

- App launches on device.
- User can sign in with Apple.
- Tokens are stored in Keychain.

## iPhone Milestone 2: Pairing

- Build pairing scanner.
- Build manual pairing code fallback.
- Claim pairing session via backend.
- Store paired Mac metadata.
- Show connected/offline state.

Definition of done:

- A clean iPhone can pair with a clean Mac companion.
- Pairing survives app restart.
- User can remove paired Mac.

## iPhone Milestone 3: Control UI

- Build main two-panel layout:
  - Top: swipeable Cursor window cards.
  - Bottom: trackpad.
- Implement connection status.
- Implement compact submitted toast.
- Implement recording state and cancel `X`.

Definition of done:

- User can select a Cursor window card.
- User can use the trackpad.
- UI works in landscape and handles iPhone safe areas.

## iPhone Milestone 4: Audio And Transcription

- Request microphone permission with pre-permission explanation.
- Record audio only while user is actively recording.
- Stop and release mic immediately.
- Upload audio to backend transcription endpoint.
- Receive transcript.
- Send transcript to selected Mac/window.

Definition of done:

- Tap to record, tap to stop and send.
- Cancel discards audio.
- Empty transcript does not send.
- No visible system mic indicator remains after stop/cancel.

## iPhone Milestone 5: Billing And Settings

- Fetch entitlement from backend.
- Show usage and plan.
- Add upgrade/manage plan entry.
- Add privacy settings.
- Add device revoke.
- Add delete account.

Definition of done:

- User can see plan/usage.
- User can revoke Mac.
- User can delete account or start account deletion flow.

## Mac Companion Architecture

Recommended modules:

- `MenuBarApp`: status item, menu, windows.
- `Auth`: account login and token storage.
- `Pairing`: pairing QR/code and paired device list.
- `Permissions`: Accessibility and Automation onboarding.
- `CursorControl`: window discovery, focus, paste, submit.
- `PointerControl`: trackpad movement, clicks, scroll.
- `RelayClient`: backend WebSocket client.
- `LocalServer`: local network listener/discovery.
- `Updater`: app update mechanism.
- `Diagnostics`: logs and support bundle.

## Mac Milestone 1: Native Shell

- Create Mac app target.
- Menu bar app with status:
  - Not signed in.
  - Needs permissions.
  - Ready.
  - iPhone connected.
  - Offline/reconnecting.
- Sign in flow.
- Store tokens in Keychain.

Definition of done:

- User can launch Mac app without Terminal.
- Menu bar status accurately reflects setup state.

Current beta implementation:

- `Blind Monkey.app` now compiles a native Cocoa host from `mac-companion/BlindMonkeyCompanion.swift`.
- The app starts `./run.sh` in the background, captures logs, and exposes basic actions without opening Terminal.
- This is an MVP companion shell, not the final menu bar app rewrite.

## Mac Milestone 2: Permissions

- Accessibility primer and deep link to System Settings.
- Automation primer if AppleScript/System Events remains necessary.
- Permission status checks.
- Retry after permission granted.

Definition of done:

- Clean Mac user can grant required permissions from guided onboarding.
- App clearly explains why permissions are needed.

## Mac Milestone 3: Cursor Integration

- List Cursor windows.
- Focus selected Cursor window.
- Paste submitted text.
- Submit with selected key behavior.
- Avoid toggling Cursor panels.

Definition of done:

- Same behavior as prototype, but from native Mac companion.
- Errors are surfaced to the iPhone and menu bar diagnostics.

## Mac Milestone 4: Relay And Local Connection

- Register Mac device with backend.
- Create pairing sessions.
- Open relay WebSocket.
- Advertise local network service.
- Accept authenticated local iPhone session.
- Route incoming iPhone commands to Cursor/pointer control.

Definition of done:

- iPhone works locally when nearby.
- iPhone works remotely through relay when not nearby.
- Unknown devices cannot send commands.

Current beta implementation:

- `relay/main.py` provides a FastAPI/WebSocket relay MVP.
- `server/relay_client.py` connects the Mac server outbound to the relay when `BLIND_RELAY_URL`, `BLIND_DEVICE_ID`, and `BLIND_RELAY_TOKEN` are set.
- `phone/index.html` can opt into relay mode with `?relay=...&device=...&token=...`.

## Mac Milestone 5: Distribution

- Developer ID signing.
- Notarization.
- DMG or `.pkg` installer.
- Auto-update strategy.
- Website download page.
- Review/support instructions.

Definition of done:

- User can download, open, and install without Gatekeeper warnings.
- Updates do not require reinstalling from scratch.

## Shared Protocol Milestone

Create a shared protocol spec before coding native apps:

- JSON message envelopes.
- Command payload schemas.
- Error codes.
- Version negotiation.
- Heartbeat/reconnect behavior.
- Max payload sizes.

The protocol should be generated or validated on both apps to avoid drift.

## Beta Plan

### Internal Alpha

- 2-3 Macs.
- 2-3 iPhones.
- Local and remote relay tested daily.
- Manual logs acceptable.

### Private TestFlight

- 10-25 users.
- Notarized Mac companion download.
- Usage caps enabled.
- Support channel open.
- Collect onboarding friction and App Review risks.

### Public Launch Candidate

- Privacy policy live.
- Support site live.
- Billing/entitlement tested.
- Account deletion tested.
- App Store review notes written.
- Mac companion notarized and hosted.

## Implementation Order

1. Backend auth/devices/pairing.
2. Mac companion pairing and relay skeleton.
3. iPhone pairing and relay skeleton.
4. Cursor control in native Mac app.
5. iPhone control UI.
6. Audio/transcription through backend.
7. Billing readiness.
8. Brand polish, screenshots, review package.

## Definition Of Shippable V1

- No Tailscale setup.
- No Terminal setup.
- No certificate install flow.
- One-time pairing.
- Works on local Wi-Fi and through backend relay.
- iPhone mic recording is explicit and visible.
- Text sends into selected Cursor window.
- Trackpad supports click, right-click, scroll, and movement.
- User can revoke devices and delete account.
- Mac app is signed and notarized.
- iPhone app has a complete App Store review package.
