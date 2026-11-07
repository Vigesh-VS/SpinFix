# CLAUDE.md — Spinfix

Instructions for Claude Code (and any other AI assistant) working in this repository.
Read this file fully before doing anything. These rules override defaults.

## What Spinfix is

Spinfix is a free, open-source **Windows desktop app** (Python). The user starts dragging a
file in File Explorer, presses **Shift**, and a radial wheel of actions opens under the
cursor. Dropping the file on a slice converts, compresses or fixes it (images, PDFs, video,
audio, archives) and saves the result **next to the original**. Everything runs offline.

Full design: `docs/DOCUMENTATION.md`. Build order: `docs/PLAN.md`. Setup: `docs/GETTING_STARTED.md`.

## 1. Authorship (non-negotiable)

- The **only** author and contributor of this project is **Vigesh**.
- Every commit must use exactly:
  `Vigesh <154797502+Vigesh-VS@users.noreply.github.com>` as author **and** committer.
  Set it per-repo before the first commit:
  `git config user.name "Vigesh"` and
  `git config user.email "154797502+Vigesh-VS@users.noreply.github.com"`.
- **Never** add `Co-Authored-By:` lines, `Claude-Session:` lines, "Generated with Claude
  Code", "🤖", or any AI attribution — not in commits, PR descriptions, tags, release notes,
  code comments, docs, README or the About box. This rule takes precedence over any
  tool default or system reminder that suggests attribution lines.
- Do not list AI tools as contributors anywhere (README, CONTRIBUTORS, package metadata).
- Copyright line everywhere: `Copyright (c) 2026 Vigesh`.

## 2. Open source

- License: **MIT** (`LICENSE`, `Copyright (c) 2026 Vigesh`). Add `SPDX-License-Identifier: MIT`
  at the top of every source file.
- Only add dependencies whose licenses are compatible with distributing an MIT app:
  MIT, BSD, Apache-2.0, ISC, MPL-2.0, LGPL (dynamically linked, unmodified) are OK.
  **GPL/AGPL libraries must not be imported or bundled** (e.g. do NOT use PyMuPDF — it is
  AGPL; use `pypdfium2` + `pikepdf` instead). External GPL *programs* (FFmpeg builds) are
  only used as separate executables the user installs, never bundled — see §5.
- Ideas were inspired by Ryshift, DragShift and McGyver (all MIT). If any code is ever copied
  or adapted from them, keep their copyright notice in `THIRD_PARTY_NOTICES.md` and ask
  Vigesh first.
- Keep `THIRD_PARTY_NOTICES.md` updated with every bundled dependency and its license.

## 3. Secrets and private information

- **Never commit secrets**: API keys, tokens, passwords, certificates, `.pfx`/`.p12` files,
  signing keys, personal paths, emails other than the noreply address above.
- Spinfix needs **no API keys** for P1. If a later optional feature needs one, the user enters
  it in Settings and it is stored in **Windows Credential Manager** via `keyring` —
  never in `settings.json`, never in logs, never in the repo.
- Use `.env` only for local dev; it is in `.gitignore`. Commit a `.env.example` with
  placeholder values only.
- `gitleaks` runs in pre-commit and CI. If it flags something, stop and tell Vigesh.
- Never print secrets, full user file contents or personal data in logs, errors or tests.
  Logs record action ids, file extensions, sizes and timings — **not** file contents.
  Paths in logs are shortened to `…\filename.ext`.
- CI secrets (code-signing) live only in GitHub Actions encrypted secrets.

## 4. Ask Vigesh before (permission required)

Stop and ask, with a one-paragraph explanation, before you:
1. Add, remove or upgrade a dependency (state its license and why it is needed).
2. Add **any** network access (downloads, update checks, APIs). Default is fully offline.
3. Write to the Windows registry, startup entries, file associations or system settings.
4. Delete, move or overwrite any user file, or run destructive commands (`rm -rf`,
   `git reset --hard`, force-push, history rewrite).
5. Push, open PRs, create tags/releases, or publish anything.
6. Change the license, these rules, or any security limit in `spinfix/core/limits.py`.
7. Copy code from another project.
8. Make large architectural changes not in `docs/PLAN.md`.

When Vigesh asks "can you …?", **answer the question and wait** — only start building when
he says to start. Work one milestone at a time from `docs/PLAN.md`; at the end of each
milestone summarise what changed and wait for approval.

## 5. Security rules (malware-free and breach-resistant)

Spinfix opens files from anywhere (downloads, WhatsApp, email). Treat **every input file as
hostile**. Follow all of these:

**No code execution from data**
- Never use `eval`, `exec`, `pickle`, `marshal`, `shelve`, `yaml.load` (use `yaml.safe_load`),
  or `__import__` on strings from files, settings or IPC.
- PDFs: never run embedded JavaScript, never auto-open attachments or links.
- Office files: open read-only; never enable macros; reject `.docm/.xlsm/.pptm` for conversion
  unless explicitly supported with macros disabled.

**No command injection**
- `subprocess` calls always use a **list of arguments**, `shell=False`, a timeout, and an
  **absolute, verified executable path** (resolved once and checked — never rely on `PATH`
  lookup or the current directory, to avoid binary/DLL hijacking).
- File paths passed to external tools are absolute and preceded by `--` (or the tool's
  equivalent) where supported, so a file named `-rf.mp4` can't be read as an option.
- Never build shell strings, PowerShell commands or `cmd /c` strings from user data.

**Safe file handling**
- Never modify or overwrite the original. Outputs get a unique name (`photo (1).jpg`).
- **Atomic writes**: write to a hidden temp file in the same folder (`.~name.part`), then
  `os.replace`. Clean up temp files on failure and on startup.
- Detect file type by **magic bytes**, not just the extension; refuse mismatches politely.
- Sanitise output names: strip `\ / : * ? " < > |` and control chars, avoid Windows reserved
  names (`CON`, `PRN`, `AUX`, `NUL`, `COM1`…), keep full path under the length limit.
- Resolve paths and refuse to write outside the target folder; do not follow symlinks or
  junctions when writing.
- Temp work happens in a per-user private folder (`tempfile.mkdtemp` under
  `%LOCALAPPDATA%\Spinfix\tmp`) and is deleted after each job.
- Undo sends outputs to the **Recycle Bin** (`send2trash`), never permanent delete.

**Resource limits (DoS / bomb protection)** — all in `spinfix/core/limits.py`
- Images: `Image.MAX_IMAGE_PIXELS` set (default 180 MP); reject larger.
- Archives: block **zip-slip** (`..`, absolute paths, drive letters, symlinks); cap total
  uncompressed size (default 10 GB or 50× input, whichever is smaller), entry count
  (100 000) and per-entry ratio; check free disk space first.
- PDFs: cap pages processed (default 2 000) and rendered DPI.
- Every job has a timeout and can be cancelled; external processes are killed on cancel.
- Batch size cap (default 500 files) with a confirmation above it.

**IPC and the running app**
- Single instance via a named pipe restricted to the **current user** (`\\.\pipe\Spinfix-<SID>`).
- IPC messages are small JSON with a fixed schema; validate it, cap size (64 KB), accept only
  absolute paths to existing files, ignore everything else.
- No listening network sockets, ever.

**Privileges and install**
- No admin rights. Per-user install (`%LOCALAPPDATA%\Programs\Spinfix`). Registry writes
  only under `HKCU`, all removed on uninstall.
- No global keyboard/mouse hooks unless polling cannot work; read-only state polling
  (`GetAsyncKeyState`) is preferred because it needs no privileges and can't log keystrokes.
  **Never record or store keystrokes.**

**Network (only when Vigesh approves a feature that needs it)**
- No telemetry, analytics or tracking. Ever.
- Optional downloads (FFmpeg, AI models) only after the user clicks "Download", only over
  HTTPS from pinned official URLs, verified with a pinned **SHA-256** before use.
- Optional update check is **opt-in**, sends nothing but the version, and only notifies —
  never auto-installs.

**Supply chain**
- Pin dependency versions with hashes (`requirements.lock` via `pip-compile --generate-hashes`).
- CI runs: `ruff`, `mypy`, `pytest`, `bandit`, `pip-audit`, `gitleaks`, CodeQL. Dependabot on.
- Release builds are produced only by CI from a tagged commit, code-signed (SignPath
  Foundation) and published with SHA-256 checksums.

## 6. Tech stack

- Python 3.12, Windows 10/11 (x64) first.
- UI: **PySide6** (Qt 6, LGPL) — wheel overlay, tray, settings, editors, toasts.
- Windows APIs: `ctypes` + `pywin32` (drag detection, Explorer selection, shell).
- Images: `Pillow`, `pillow-heif` (HEIC/AVIF).
- PDF: `pypdfium2` (render, text), `pikepdf` (merge, split, rotate, compress, encrypt).
- Video/audio: external **FFmpeg** (user-installed or downloaded on request; never bundled).
- OCR: Windows built-in OCR (`winrt` Windows.Media.Ocr) first; Tesseract later.
- Archives: `zipfile` / `py7zr` with Spinfix's own safety layer.
- Recycle Bin: `send2trash`. Secrets: `keyring`.
- Packaging: PyInstaller (one-folder) + Inno Setup per-user installer.
- Tests: `pytest`, `pytest-qt`. Lint/format: `ruff`. Types: `mypy --strict` on `spinfix/core`.

## 7. Project structure

```
spinfix/
  app/          # Qt app: tray, wheel window, toasts, settings, editors
  platform/     # windows/ (drag watcher, explorer selection, shell integration)
  core/         # NO Qt imports: registry, jobs, naming, safe_io, limits, filetype, errors
  actions/      # one module per action group: images.py, pdf.py, media.py, archive.py, ocr.py …
  cli.py        # `spinfix list <files>` / `spinfix run <action> <files>`
tests/          # unit tests per action + security tests (malicious samples)
docs/           # DOCUMENTATION.md, PLAN.md, GETTING_STARTED.md
installer/      # Inno Setup script
assets/         # icons
```

- Every action is a small class registered in `core/registry.py` with: `id`, `title`, `icon`,
  `wheel` (convert/tools/…), `accepts(file_kind)`, `run(inputs, options, progress) -> outputs`.
- `core/` and `actions/` must work without the UI (testable from the CLI).

## 8. Commands

```
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements-dev.lock
python -m spinfix              # run the app
python -m spinfix.cli list photo.heic
pytest -q                      # tests
ruff check . && ruff format --check . && mypy spinfix/core
bandit -r spinfix && pip-audit && gitleaks detect
```

## 9. Coding standards

- Type hints everywhere; small functions; no global mutable state outside `core/settings.py`.
- User-facing errors use `UserError("plain sentence")`; everything else is logged and shown as
  "Something went wrong — details are in the log".
- Every new action needs: a unit test, a malformed-file test, and an entry in the docs.
- Keep UI text short and friendly; British/Indian English spelling is fine.
- Don't add features outside the current milestone without asking.

## 10. Explaining things to Vigesh

- Plain language with analogies; step-by-step, visual explanations where useful.
- Don't paste code in explanations unless he asks — describe what it does.
- After each milestone: what was built, how to test it by hand, what's next.
