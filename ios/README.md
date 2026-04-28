# Blind Monkey iOS Shell

This folder is the native iPhone app starting point for the App Store build.

Current scope:
- SwiftUI shell with sign-in gate.
- Control surface that mirrors the web app layout: account status, swipeable Cursor cards, tap-to-dictate panel, and trackpad area.
- Placeholder session model ready to be wired to Supabase Auth and the account-aware relay.

Next native implementation steps:
- Add the Supabase Swift SDK and store the session in Keychain.
- Replace sample windows with relay state from the Mac.
- Port the web app's microphone, haptics, trackpad gesture, and dictation protocol into Swift.
- Add `NSMicrophoneUsageDescription` before TestFlight.
