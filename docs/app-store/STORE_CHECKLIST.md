# Blind Monkey — App Store and distribution checklist

## iPhone (App Store / TestFlight)

- **Bundle ID**: set a single reverse-DNS id in Xcode and in App Store Connect.
- **Privacy Nutrition Labels**: Microphone (on when the user records), network (relay and Supabase), and account sign-in (Supabase email link).
- **Usage strings** (required in the app target):
  - `NSMicrophoneUsageDescription` — already stubbed in `ios/project.yml` via `INFOPLIST_KEY_NSMicrophoneUsageDescription`.
- **Account lifecycle**: users can sign out in the web/PWA flow via Supabase; document that account deletion is available through Supabase / your privacy policy contact.
- **Export compliance**: standard encryption (HTTPS) — answer the annual questionnaire as for other apps using TLS.

## Mac (recommended: Developer ID + notarization)

The Mac app controls Cursor via Accessibility. That use case is a poor match for the **Mac App Store** sandbox, so the practical path is a **notarized** app outside the store (direct download or your own site).

- **Developer ID** signing, **Hardened Runtime**, and **notarization** (see `scripts/notarize-mac.sh` for a template).
- **Entitlements**: `com.apple.security.app-sandbox` should remain **off** for the current control architecture (see `mac-native/BlindMonkeyMac.entitlements`).

## Public relay (Railway or other)

- Set **`SUPABASE_JWT_SECRET`** (from Supabase project → Settings → API → JWT Secret).
- Set **`BLIND_RELAY_SESSION_SECRET`** (or rely on the same as JWT secret) for minted relay session tokens.
- Set **`SUPABASE_URL`** and **`SUPABASE_ANON_KEY`** so the hosted PWA can load `/config.js` with `accountPairing: true`.
- CORS: default `*` is enabled for the session mint `POST` from the phone browser; restrict with `BLIND_RELAY_CORS` in production if needed.

## Environment summary

| Variable | Where |
|----------|--------|
| `BLIND_RELAY_URL` | Mac server — WebSocket base (`wss://...`) |
| `BLIND_SUPABASE_ACCESS_TOKEN` | Mac server — same-user session as the phone (or `BLIND_RELAY_TOKEN` for dev rooms) |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | Mac server and relay — phone sign-in and `/config.js` |
| `SUPABASE_JWT_SECRET` | Relay — verify Supabase JWTs and sign short-lived relay tokens |
