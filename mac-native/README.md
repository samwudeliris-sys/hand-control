# Blind Monkey Native Mac Shell

This folder is the signing-ready direction for the Mac companion.

Current scope:
- SwiftUI dashboard shell sized to the existing 820x820 product UI.
- Explicit account, Accessibility, relay, and Cursor-window status slots.
- Placeholder actions for sign-in and opening the phone app.

Migration path:
- Move the current `mac-companion/BlindMonkeyCompanion.swift` launcher responsibilities into this app target.
- Add Keychain-backed Supabase session storage.
- Register the Mac device after sign-in and pass the Supabase access token to the Python control engine as `BLIND_SUPABASE_ACCESS_TOKEN`.
- Keep the Python server as the control engine until the Accessibility and Cursor-control pieces are migrated safely into Swift.
- Ship Mac outside the Mac App Store first with Developer ID signing and notarization because Cursor Accessibility control is unlikely to fit App Sandbox review constraints.
