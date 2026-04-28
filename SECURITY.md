# Security policy

Hand Control starts a **local HTTPS server** bound to all interfaces (`0.0.0.0`) so your phone can reach it. Anyone on the same trusted network can interact with it. **Use trusted Wi‑Fi or Tailscale**; there is no built-in authentication for local control.

Audio for transcription is sent **phone → your Mac → OpenAI** over HTTPS; see the README **Security notes** section.

## Reporting a vulnerability

Please report security issues **privately**:

1. Open a **GitHub Security Advisory** on this repository (**Security → Advisories → Report a vulnerability**), or  
2. Contact the maintainers through GitHub with minimal details if Advisories are unavailable.

Please do **not** open public issues for undisclosed security problems.

We aim to acknowledge reports within a few business days.
