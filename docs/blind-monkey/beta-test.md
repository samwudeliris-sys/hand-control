# Blind Monkey Pre-App-Store Beta

This beta lets us test the customer experience before building the native App Store app.

It is not the final App Store architecture yet. It uses the current Mac server, a native Mac host app, a relay MVP, and an installable iPhone web app, but the visible flow should feel close to:

1. Install/open the Mac companion.
2. Open the phone app from the Home Screen.
3. Add it to the Home Screen during first setup.
4. Dictate into Cursor from the phone.

## What This Beta Tests

- Blind Monkey branding.
- Mac companion launch from Dock/Spotlight.
- Installable phone app behavior through Safari Add to Home Screen.
- Phone microphone dictation.
- Cursor window cards.
- Trackpad control.
- Tap-to-record, tap-to-stop-and-send.
- Cancel recording with the small `X`.

## What This Beta Does Not Yet Test

- App Store installation.
- Native SwiftUI iPhone app.
- Native Mac menu bar companion.
- Backend relay remote access in production form.
- Account login.
- Billing.
- Device pairing accounts.

Those are covered in the production docs in this folder.

## Mac Test Flow

1. Click `Blind Monkey` in the Dock or launch it from Spotlight.
2. The native Mac app opens and starts the Python control server in the background.
3. Use `Show QR / Link` if you need the beta phone URL again.
4. Use `Open Logs` if you need to inspect server output.

## iPhone Test Flow

1. Open the Blind Monkey Home Screen app if already installed, or scan the QR fallback once.
2. If Safari warns about the local certificate, complete the `/install` trust flow once.
3. Tap Share.
4. Tap Add to Home Screen.
5. Confirm the app name is `Blind Monkey`.
6. Launch from the new Home Screen icon.
7. Test in landscape orientation.

## Core Test Script

1. Open Cursor on the Mac.
2. Open at least two Cursor windows.
3. Launch Blind Monkey on the Mac.
4. Open Blind Monkey on the iPhone.
5. Confirm the connection says connected.
6. Swipe between Cursor cards.
7. Tap a card to start recording.
8. Say a short message.
9. Tap the card again to stop and send.
10. Confirm the message lands in the selected Cursor window.
11. Start another recording and tap the `X`.
12. Confirm nothing is sent.
13. Use the trackpad to move, click, right-click, and scroll.

## Pass Criteria

- No manual URL typing.
- No Tailscale setup.
- The phone app is launchable from Home Screen.
- The Mac app is launchable from Dock or Spotlight.
- Mic activates only during recording.
- Mic releases after stop/cancel.
- The selected Cursor window receives the transcript.
- The submitted toast does not block another recording.
- The app feels understandable without reading Terminal logs.

## Relay Mode Test Flow

The relay MVP proves the no-Tailscale connection shape, but still uses a simple shared token for beta testing.

Terminal 1, start the relay:

```bash
BLIND_RELAY_TOKEN=dev-relay-token ./run-relay.sh
```

Terminal 2, start the Mac server with an outbound relay connection:

```bash
BLIND_RELAY_URL=ws://127.0.0.1:8765 \
BLIND_DEVICE_ID=sam-mac \
BLIND_RELAY_TOKEN=dev-relay-token \
./run.sh
```

Open the phone web app with relay config:

```text
https://MacBook-Air.local:8000/?relay=ws://127.0.0.1:8765&device=sam-mac&token=dev-relay-token
```

For a real remote phone, the relay URL must be deployed somewhere reachable from the phone, for example `wss://relay.yourdomain.com`.

To clear relay mode on the phone and return to local nearby mode:

```text
https://MacBook-Air.local:8000/?clearRelay=1
```

## Known Gaps Before Public Beta

- The app still depends on local network or manually configured remote access.
- The Mac companion is native-feeling but still hosts the Python control server rather than being a full Swift rewrite.
- There is no customer account or billing.
- The backend relay is an MVP with a shared token and in-memory rooms.
- The iPhone app is still a web app, not a native App Store app.

## Next Upgrade After This Beta

Build the backend pairing/relay MVP, then replace the phone web app with a native SwiftUI app and the Terminal-backed Mac wrapper with a menu bar companion.
