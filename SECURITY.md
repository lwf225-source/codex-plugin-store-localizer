# Security policy

## Reporting a vulnerability

Please do not open a public issue for a suspected security vulnerability. Contact the maintainers privately through the repository's security advisory channel and include a minimal reproduction, affected version, and impact.

## Security boundaries

- The launcher only targets `app://` pages from the verified desktop application.
- It uses a private Chromium debugging pipe and never opens a local network port.
- Translation payloads are validated JSON; arbitrary JavaScript is rejected.
- macOS requires expected code-signing identity and integrity; Windows requires a valid Authenticode signature.
- Runtime logs exclude DOM text, URLs with parameters, and conversation data.

Do not weaken these protections to make an unsupported app build run.
