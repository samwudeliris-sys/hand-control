# Contributing

Thanks for helping improve Hand Control.

## Getting started

1. Fork the repository and clone your fork.
2. On macOS, run `./install.sh` or `./run.sh` from the repo root after setting `OPENAI_API_KEY` (see README).
3. Keep changes focused; match existing style and naming in the files you touch.

## Pull requests

- Open a PR against `main` with a clear description of behavior changes.
- For Mac server work, verify `./run.sh` starts and the phone UI loads over HTTPS on your LAN.
- For the Windows peer, verify `peer\\run.bat` after changes under `peer/`.

## Scope

- **Security**: This project runs a LAN-accessible control plane. Changes that widen exposure or weaken TLS should include a clear rationale and README updates.

## License

By contributing, you agree your contributions are licensed under the same [MIT License](LICENSE) as the project.
