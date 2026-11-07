# Spinfix — Build Plan

One milestone at a time. Each milestone ends with: tests green, a manual check list done,
a short summary to Vigesh, and **his approval** before the next one starts.

Legend: ☐ to do · ✅ done

---

## Phase 1 — v0.1 "It works for real people" (Windows)

### M0 · Repo foundation (≈ 1 day)
Goal: an empty but safe, well-set-up project.
- ✅ Create repo `Vigesh-VS/SpinFix` (public), set git author to Vigesh (see CLAUDE.md §1)
- ✅ `LICENSE` (MIT, Copyright (c) 2026 Vigesh), `SECURITY.md`, `THIRD_PARTY_NOTICES.md`,
  `.gitignore` (Python, PyInstaller, `.env`, `*.pfx`, `dist/`, `build/`), `.env.example`
- ✅ Folder structure from CLAUDE.md §7, `pyproject.toml`, `requirements.in` → hashed lock files
- ✅ Tooling: ruff, mypy, pytest, bandit, pip-audit, gitleaks, pre-commit hooks
- ✅ GitHub Actions on `windows-latest`: lint + types + tests + security scans; CodeQL; Dependabot
- **Done when:** CI is green on an empty app that prints its version.

### M1 · Core engine, no UI (≈ 3 days)
Goal: the "kitchen" works and is safe, testable from the command line.
- ✅ `core/filetype.py` — magic-byte detection (image kinds, PDF, ZIP, 7z, MP4/MOV/MKV, MP3…)
- ✅ `core/safe_io.py` — unique names, name sanitising, atomic commit, temp dir, cleanup
- ✅ `core/limits.py` — all caps in one place (pixels, pages, archive size/ratio/entries, timeouts)
- ✅ `core/registry.py` — action registry + `Action` base class
- ✅ `core/jobs.py` — job object, worker thread, progress, cancel, timeout
- ✅ `core/errors.py` — `UserError` vs internal errors; logging setup (no file contents)
- ✅ `cli.py` — `spinfix list <files>` and `spinfix run <action> <files>`
- ✅ Security tests: zip-slip sample, zip bomb sample, fake-extension file, huge-pixel PNG,
  file names with `&`, `-`, unicode, reserved names (`CON.txt`)
- **Done when:** a test action (e.g. "copy as PNG") runs from the CLI and all security tests pass.

### M2 · The wheel on Windows (≈ 4–5 days) — the riskiest part, prove it early
Goal: drag + Shift opens a wheel and the drop reaches the engine.
- ✅ `platform/windows/drag_watcher.py` — 15 ms polling, Explorer/Desktop source check,
  drag threshold, trigger key, Esc, "no file arrived → hide" timeout
- ✅ `app/wheel.py` — transparent, topmost, non-activating overlay; up to 8 slices;
  hover highlight; drop handling; Shift cycles wheels; centre/outside = cancel
- ✅ Multi-monitor and DPI scaling (100 %–200 %) handled
- ✅ Tray (in `app/main.py`) — Pick files, Pause/Resume, Settings, About, Quit
- ✅ Single instance + IPC named pipe (current-user only, validated JSON)
- ✅ Global hotkey Ctrl+Alt+Space + Explorer selection via COM
- ✅ `app/toast.py` — progress, result line, Open / Show in folder / Undo (Recycle Bin)
- ☐ **Manual check (Vigesh):** drag from Explorer, Desktop, Downloads, a network drive, a zip folder
  view; window-drag and text-select don't leave a stuck wheel; works at 150 % scaling.

### M3 · Image actions (≈ 4 days)
- ✅ Convert: PNG, JPG, WEBP, TIFF, BMP, GIF, PDF; HEIC/HEIF input (pi-heif — pillow-heif
  bundles GPL x265, so the decode-only pi-heif is used; see DOCUMENTATION §7)
- ✅ Respect EXIF orientation; keep or strip metadata per setting
- ✅ Compress (quality) and **compress to target size** (binary search on quality, then
  resolution; report best result if the target is impossible)
- ✅ Resize presets + custom size dialog
- ✅ Strip metadata: all / GPS only
- ✅ Combine several images into one PDF (order = selection order)
- ☐ Small dialog to re-order images before combining
- **Done when:** every image action has unit + malformed-file tests and works in batch.

### M4 · PDF actions (≈ 4 days)
- ✅ PDF → JPG/PNG per page (pypdfium2), PDF → TXT
- ✅ Merge (drop several), split (every page / ranges), extract pages, rotate (pikepdf)
- ✅ Compress (image downsampling + object streams) and **compress to target size**
- ✅ Password-protected PDFs: clear message (unlock comes in P2)
- **Done when:** tests cover a 1-page, 300-page, scanned, encrypted and broken PDF.

### M5 · Video/audio, archives, OCR, clipboard (≈ 4 days)
- ✅ FFmpeg finder: absolute path from settings → `%LOCALAPPDATA%\Spinfix\tools` → winget
  location. If missing: friendly "Install with winget" message
- ☐ **Download** button for FFmpeg (pinned URL + SHA-256) — **needs Vigesh's approval** (network)
- ✅ Video → MP3/M4A; compress for WhatsApp/email presets (2-pass bitrate from target size)
- ✅ Progress from FFmpeg's `-progress` output; cancel kills the process
- ✅ Zip (files/folders) and unzip with the safety layer
- ✅ Copy text from image (Windows OCR) → clipboard + toast preview
- ✅ Copy path / copy file to clipboard
- **Done when:** a 1 GB video compresses with progress and can be cancelled cleanly.
  ☐ Not verified yet — FFmpeg isn't installed on the dev PC.

### M6 · Editors (≈ 5 days)
Floating window per editor; save as `name Cropped.jpg` etc.
- ✅ Crop (ratios Free/1:1/4:5/9:16/16:9/A4, pixel readout)
- ✅ Edit (rotate, flip, brightness, contrast, saturation, resize)
- ✅ Annotate (pen, arrow, box, highlighter, text, numbered steps, undo)
- ✅ Redact (black box / pixelate — pixels are really destroyed, not overlaid)
- ✅ Add background (gradients/solid, padding, corners, shadow, aspect ratio)

### M7 · Settings, installer, release v0.1 (≈ 3 days)
- ✅ Settings window (all P1 settings, saved instantly, validated)
- ✅ First-run welcome: 3-step "how to use" + "Start with Windows?" question
- ✅ Right-click "Spinfix…" and Send To (HKCU, removed on uninstall)
- ✅ PyInstaller one-folder build + Inno Setup per-user installer + portable zip
- ✅ CI release workflow on tag: build → SHA-256 → GitHub Release (draft)
- ☐ Code signing: apply to SignPath Foundation, then fill in the signing step (Vigesh)
- ☐ Install → use → uninstall test on a clean Windows VM; check nothing is left behind (Vigesh)
- ✅ Write `HOWTO.md` (install, use, uninstall, FAQ) and `README.md`
- ☐ Screenshots / GIF of the wheel in README (needs a real screen recording)
- **Done when:** Vigesh approves the draft release and publishes it himself.

---

## Phase 2 — v0.2 / v0.3 "The India-specific edge"
- Passport/ID photo maker (presets: Indian passport, PAN, visa, exam portals)
- Signature cleaner
- PDF unlock/protect (AES-256), editors on any PDF page, PDF ↔ Word, searchable PDF (OCR)
- Watermark, AVIF/ICO output, remove background (opt-in model download)
- Video trim/mute/GIF/9:16, audio convert + normalise
- Pin/hide/reorder slices, recipes, history panel
- Smart rename, QR code, pinned "Move to" folders
- Tamil + Hindi UI translations

## Phase 3 — later
- Transcribe → subtitles (Whisper), summarise/ask a PDF (local model), translate in image
- Auto-redact personal numbers, watch folders, custom script slices (sandboxed)
- Send to phone, macOS and Linux versions, Microsoft Store listing, winget package

---

## Risks and how we handle them
| Risk | Plan |
|---|---|
| Drag detection flaky on some PCs | Prove in M2 first; always keep hotkey + right-click as fallbacks |
| SmartScreen warns on unsigned exe | Apply to SignPath Foundation early (M0); explain in HOWTO |
| Antivirus false positives (PyInstaller) | One-folder build, signed, no UPX packing, submit to Microsoft for analysis |
| FFmpeg licensing | Never bundle; user installs or downloads on request |
| Scope creep | Only the current milestone; new ideas go to Phase 2/3 list |

## Definition of done (every feature)
- Works in single and batch mode · never touches the original · cancellable
- Unit test + malformed-input test · documented in DOCUMENTATION.md
- Ruff, mypy, bandit, pip-audit, gitleaks all clean
