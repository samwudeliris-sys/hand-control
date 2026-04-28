# Blind Monkey

This folder is the productization package for turning the current Hand Control prototype into `Blind Monkey`: an App Store iPhone app, a notarized Mac companion, and a backend relay/billing/transcription system.

## Documents

- [Product Spec](product-spec.md): user flows, onboarding, permissions, App Store review positioning, and v1 acceptance criteria.
- [Architecture](architecture.md): iPhone app, Mac companion, backend relay, pairing, transcription, and security model.
- [Brand Pack](brand-pack.md): name, mascot direction, App Store-safe icon guidance, colors, copy, and screenshot plan.
- [Backend MVP](backend-mvp.md): auth, pairing, relay, transcription proxy, metering, billing readiness, and admin tools.
- [Native Apps](native-apps.md): SwiftUI iPhone app and signed/notarized Mac companion milestones.
- [Pre-App-Store Beta](beta-test.md): the current test flow using the branded Mac launcher and installable iPhone web app.

## Core Decisions

- First release is Mac-only.
- Customers should not need Tailscale.
- Built-in remote access is handled through a backend relay.
- The iPhone app ships through the App Store.
- The Mac companion ships as a signed and notarized direct download.
- The transcription API key lives only on the backend.
- Billing can come later, but usage metering must exist before beta.

## Current MVP State

- `Blind Monkey.app` is now a native Cocoa host that starts the existing Python Mac server in the background instead of opening Terminal.
- `relay/main.py` is a relay MVP that forwards the current phone WebSocket protocol between a phone and Mac connection.
- Local nearby mode still works by default.
- Relay mode is opt-in for beta testing with `BLIND_RELAY_URL`, `BLIND_DEVICE_ID`, and `BLIND_RELAY_TOKEN`.

## Recommended Build Order

1. Backend auth, devices, pairing.
2. Mac companion pairing and relay skeleton.
3. iPhone pairing and relay skeleton.
4. Native Mac Cursor control.
5. Native iPhone control UI.
6. Backend transcription proxy and usage metering.
7. Billing readiness.
8. Brand polish and App Store review package.
