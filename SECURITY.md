# Security Policy

Spinfix opens files from anywhere, so we take security seriously.

## Supported versions

Only the latest release of Spinfix receives security fixes.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

Report privately through GitHub:
**Security → Advisories → Report a vulnerability** on
<https://github.com/Vigesh-VS/SpinFix/security/advisories/new>.

Please include:
- what the problem is and what an attacker could do with it,
- steps or a sample file to reproduce it (zip it if needed),
- the Spinfix version and Windows version.

You can expect a first reply within 7 days. Once a fix is released, the advisory is
published and you are credited unless you prefer not to be.

## What Spinfix promises

- Fully offline by default: no telemetry, no tracking, no listening network sockets.
- Original files are never changed; outputs are written atomically next to them.
- Every input file is treated as hostile (magic-byte checks, size and bomb limits,
  zip-slip protection, no code execution from file data).
- No admin rights; per-user install; registry writes only under `HKCU`.

See `docs/DOCUMENTATION.md` §8 for the full security model.
