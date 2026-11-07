# Spinfix — Product & Technical Documentation

> **Spin. Drop. Fixed.**
> Drag any file, press Shift, drop it on a wheel. Spinfix converts, compresses or fixes it
> right next to the original — offline, free and open source.

Version: design v1 (pre-release) · Author: Vigesh · License: MIT

---

## 1. The problem

Everyday file jobs are annoying on Windows:

- A portal says "photo must be under 200 KB, 35×45 mm, white background".
- A PDF is too big to email, is locked with a password, or needs pages merged or split.
- An iPhone photo is `.heic` and nothing opens it.
- A video is too big for WhatsApp; you only want the audio as MP3.
- You need the text out of a screenshot.

Today people upload private files to ad-filled websites (iLovePDF, online converters), wait,
and download again. Spinfix does all of it **on the PC, in one drag**.

## 2. Who it's for

- Students and job seekers (exam/college/government/placement portals with strict limits).
- Freelancers and small shops (product photos, watermarks, invoices as PDF).
- Anyone who shares files on WhatsApp, email and social media.

## 3. How it feels to use

### 3.1 Drag + Shift (main way)
1. Start dragging a file (or several) in File Explorer or on the Desktop.
2. While still dragging, press **Shift**. A round glass wheel appears under the cursor.
3. Move onto a slice — it lights up. Release the mouse to drop.
4. A small toast shows progress, then the result: *"2.4 MB → 610 KB · 75 % smaller"*
   with **Open**, **Show in folder** and **Undo**.
5. Tap **Shift** again while dragging to switch wheels (Convert → Tools → Smart → Share).
6. Drop on the centre or outside the wheel, or press **Esc**, to cancel.

### 3.2 Other ways in
- **Hotkey:** select files in Explorer, press **Ctrl + Alt + Space** → wheel at the mouse.
  Click a slice or press its number (1–8).
- **Right-click** a file → **Spinfix…** (and **Send to → Spinfix**).
- **Tray icon:** double-click to pick files.

### 3.3 Rules users can trust
- The original file is **never changed**.
- Results go next to the original (or into a `Spinfix` subfolder — setting).
- Name clashes become `name (1).ext`, `name (2).ext`.
- Undo moves results to the Recycle Bin.
- Nothing is uploaded. No account. No ads. No tracking.

## 4. Features

Priority: **P1** = first public version (v0.1), **P2** = v0.2–0.3, **P3** = later.

### 4.1 Core experience
| Feature | Priority |
|---|---|
| Drag + Shift wheel (Explorer + Desktop) | P1 |
| Hotkey wheel for selected files | P1 |
| Right-click "Spinfix…" and Send To | P1 |
| Tray icon: Pause/Resume, Settings, Quit | P1 |
| Settings: trigger key, output location, quality, start with Windows | P1 |
| Progress + result toast with Open / Show in folder / Undo | P1 |
| Batch: many files at once, with summary | P1 |
| Pin, hide and reorder slices | P2 |
| Recent history panel | P2 |
| Recipes (chain actions into one slice) | P2 |
| Custom slice (run your own script — sandboxed, opt-in) | P3 |
| Watch folder (auto-process files dropped in) | P3 |
| macOS / Linux support | P3 |

### 4.2 Images (JPG, PNG, WEBP, HEIC, AVIF, TIFF, BMP, GIF, ICO)
| Feature | Priority |
|---|---|
| Convert between all formats; image → PDF | P1 |
| HEIC/HEIF → JPG/PNG on Windows | P1 |
| Compress (quality) | P1 |
| **Compress to target size** ("under 200 KB") | P1 |
| Resize presets (50 %, 1080 px, 4K) + custom | P1 |
| Strip metadata (all, or GPS only) | P1 |
| Combine several images into one PDF | P1 |
| Editors: Crop, Edit (rotate/flip/brightness/contrast), Annotate, Redact, Add background | P1 |
| **Passport / ID photo** (35×45 mm, white background, size limit) | P2 |
| **Signature cleaner** (white background, crop, resize, size limit) | P2 |
| Watermark (text/logo) | P2 |
| AVIF and ICO output | P2 |
| Remove background (on-device model, downloaded on request) | P2 |
| Auto-redact phone numbers, emails, Aadhaar-like numbers | P3 |

### 4.3 PDF
| Feature | Priority |
|---|---|
| PDF → JPG/PNG (per page), PDF → TXT | P1 |
| Merge (drop several PDFs), split, extract pages, rotate | P1 |
| **Compress to target size** | P1 |
| Password protect (AES-256) / unlock (with the user's password) | P2 |
| Editors on any page, saved back as PDF | P2 |
| Make scanned PDF searchable (OCR) | P2 |
| Word → PDF (via installed Word / LibreOffice), PDF → Word | P2 |

### 4.4 Video & audio (needs FFmpeg)
| Feature | Priority |
|---|---|
| Video → MP3/M4A | P1 |
| **Compress for WhatsApp / email** (presets: 16 MB, 25 MB, 100 MB) | P1 |
| Trim, mute, video → GIF | P2 |
| Resize to 9:16 / 1:1 / 16:9 | P2 |
| Audio convert (MP3, M4A, WAV, FLAC), normalise loudness | P2 |
| Transcribe → subtitles (Whisper, on-device, downloaded on request) | P3 |

### 4.5 Smart (on-device)
| Feature | Priority |
|---|---|
| Copy text from image (Windows OCR) | P1 |
| Smart rename (e.g. `IMG_2231.jpg` → `electricity-bill-oct-2026.jpg`) | P2 |
| Summarise a PDF / ask a question (local model, opt-in) | P3 |
| Translate text in image (Tamil ↔ English) | P3 |

### 4.6 Share & organise
| Feature | Priority |
|---|---|
| Copy path, copy file to clipboard | P1 |
| Zip / unzip (with zip-slip and zip-bomb protection) | P1 |
| Make a QR code for a file path or link | P2 |
| Move to pinned folders | P2 |
| Send to phone | P3 |

## 5. What makes Spinfix different

| | Ryshift | DragShift | McGyver | Dropwheel (Store) | **Spinfix** |
|---|---|---|---|---|---|
| Open source | ✅ | ✅ | ✅ | ❌ | ✅ |
| Free | ✅ | ✅ | ✅ | Freemium | ✅ |
| Windows HEIC | ❌ | ✅ | needs DLL | ✅ | ✅ |
| Compress to exact size (image **and** PDF) | ❌ | image only | ❌ | ❌ | ✅ |
| Passport / signature photos | ❌ | ❌ | ❌ | ❌ | ✅ (P2) |
| WhatsApp-size video presets | ❌ | ❌ | partial | ❌ | ✅ |
| OCR | ❌ | ❌ | ❌ | ❌ | ✅ |
| PDF merge/split/compress | ❌ | ✅ | ✅ | ❌ | ✅ |

Focus: **the everyday "fix this file" jobs people in India hit every week**, done safely.

## 6. Architecture

### 6.1 Layers

```
┌───────────────────────────────────────────────────────────┐
│ UI (PySide6): wheel overlay · tray · toasts · settings ·   │
│               editors (crop/annotate/…)                    │
├───────────────────────────────────────────────────────────┤
│ App controller: single instance · IPC · job queue ·        │
│                 settings · logging                          │
├──────────────────────────┬────────────────────────────────┤
│ Platform (Windows)       │ Core (no UI)                    │
│ · drag watcher           │ · action registry               │
│ · Explorer selection     │ · file-type detection (magic)   │
│ · shell integration      │ · safe I/O (atomic, naming)     │
│                          │ · limits · jobs/cancel · errors │
├──────────────────────────┴────────────────────────────────┤
│ Actions: images · pdf · media(FFmpeg) · archive · ocr ·    │
│          clipboard · (later) ai                             │
└───────────────────────────────────────────────────────────┘
```

### 6.2 Drag detection on Windows (the hard part)
Windows doesn't tell other apps "a file drag started", so Spinfix watches cheaply:

1. A timer ticks every **15 ms** and reads three things with `GetAsyncKeyState`:
   left mouse button, the trigger key (Shift by default), Esc. This only *reads* state —
   it can't see what you type and needs no admin rights.
2. When the button goes down, Spinfix remembers the position and **which window** is under
   the cursor. Only File Explorer (`CabinetWClass`) and the Desktop (`Progman`/`WorkerW`)
   count as file sources.
3. If the mouse moves past the system drag distance (`SM_CXDRAG`) with the button held, and
   then the trigger key is pressed → show the wheel at the cursor.
4. The wheel is a topmost, transparent, **non-activating** window so Explorer keeps the
   drag. Qt's drop handler receives the real file paths from Windows drag-and-drop.
5. If no file drag arrives within ~0.75 s (it was a window move or text selection), the
   wheel hides itself.
6. Tapping the key again while the wheel is open cycles wheels; releasing the button drops.

**Hotkey path:** a registered global hotkey opens the wheel; the selected files are read
from the active Explorer window via the Shell COM API (`IShellWindows` → `IFolderView`).

### 6.3 Action flow
1. Wheel asks the registry: "which actions accept these files?" (by detected type).
2. User picks a slice → controller creates a **Job** (id, inputs, options).
3. Job runs on a worker thread with a progress callback and a cancel flag.
4. Action writes to temp files → `safe_io.commit()` atomically moves them to final unique names.
5. Toast shows result; Undo sends outputs to the Recycle Bin.

### 6.4 Data the app stores
| What | Where |
|---|---|
| Settings | `%APPDATA%\Spinfix\settings.json` |
| Log (rotating, 1 MB × 3) | `%LOCALAPPDATA%\Spinfix\logs\spinfix.log` |
| Temp work | `%LOCALAPPDATA%\Spinfix\tmp\` (cleaned after each job) |
| Optional tools (FFmpeg, models) | `%LOCALAPPDATA%\Spinfix\tools\` |
| History (P2) | `%LOCALAPPDATA%\Spinfix\history.json` (paths + action, no contents) |

## 7. Tech stack

| Area | Choice | License | Why |
|---|---|---|---|
| Language | Python 3.12 | PSF | Vigesh's main language; fast to build |
| UI | PySide6 (Qt 6) | LGPL-3.0 | Transparent overlay windows, tray, drag-drop, painting |
| Windows APIs | ctypes, pywin32 | PSF | Mouse/key state, Explorer COM, shell |
| Images | Pillow, pillow-heif | HPND, BSD | Formats, resize, compress, HEIC/AVIF |
| PDF render/text | pypdfium2 | Apache/BSD | Google's PDFium engine |
| PDF edit | pikepdf | MPL-2.0 | Merge, split, rotate, compress, AES-256 |
| Video/audio | FFmpeg (external) | LGPL/GPL program | Industry standard; not bundled |
| OCR | Windows.Media.Ocr (winrt) | built-in | No download; supports installed languages |
| Archives | zipfile, py7zr | PSF, LGPL | With Spinfix safety layer |
| Recycle Bin | send2trash | BSD | Safe undo |
| Secrets (later) | keyring | MIT | Windows Credential Manager |
| Packaging | PyInstaller + Inno Setup | GPL w/ exception, free | Per-user installer, no admin |
| Tests | pytest, pytest-qt | MIT | |
| Quality | ruff, mypy, bandit, pip-audit, gitleaks, CodeQL | various | Lint, types, security |

**License check needed in M3:** pillow-heif's prebuilt Windows wheels may bundle the GPL
`x265` encoder alongside LGPL `libheif`/`libde265`. Spinfix only needs to *read* HEIC, so
before shipping, confirm what the wheel contains and, if needed, use a decode-only build or
Windows' own HEIF decoder (WIC) instead.

**Not used on purpose:** PyMuPDF (AGPL — would force the whole app to AGPL), HandBrake
(GPL; FFmpeg gives the same encoders with more control), Electron (too heavy).

## 8. Security model

Spinfix opens files from untrusted sources, so it is built defensively:

| Threat | Protection |
|---|---|
| Malicious file triggers code | No eval/pickle; PDFs' JS never runs; Office opened read-only with macros off |
| Command injection via file names | `subprocess` with argument lists, `shell=False`, absolute exe paths, `--` before paths |
| Binary/DLL hijacking | External tools resolved to absolute, verified paths; never from current folder |
| Zip-slip (`..\..\evil.exe`) | Entry names normalised; anything leaving the target folder is skipped |
| Zip/decompression bombs | Caps on total size, ratio, entry count; free-space check |
| Huge images / PDFs (DoS) | Pixel cap, page cap, DPI cap, job timeouts, cancel |
| Overwriting user data | Never touch originals; unique names; atomic writes; Recycle Bin undo |
| Fake extensions | Magic-byte detection; mismatch → friendly refusal |
| Other users/apps talking to Spinfix | Named pipe restricted to current user SID; strict JSON schema; size cap |
| Keylogging fears | Only reads mouse/trigger-key state; no hooks; nothing recorded |
| Privacy leaks | No network by default; no telemetry; logs contain no file contents |
| Tampered downloads | HTTPS + pinned SHA-256 for FFmpeg/models, only on user request |
| Supply-chain attacks | Pinned, hashed dependencies; pip-audit; Dependabot; CodeQL |
| Fake/modified installers | CI-only builds, code-signed, SHA-256 checksums on releases |
| Privilege abuse | No admin rights; per-user install; HKCU only; clean uninstall |

A `SECURITY.md` explains how to report vulnerabilities privately (GitHub Security Advisories).

## 9. Settings (P1)

| Setting | Default |
|---|---|
| Trigger key | Shift (or Ctrl / Alt) |
| Hotkey | Ctrl + Alt + Space |
| Output location | Next to the original / `Spinfix` subfolder |
| JPG/WEBP quality | 85 |
| PDF → image DPI | 150 |
| Keep metadata | Off for compress, on for convert |
| Start with Windows | Off (asked on first run) |
| Show toasts | On |
| Paused | Off |

## 10. Error messages (tone)

Short, human, actionable:
- "This PDF is password-protected. Use **Unlock** first."
- "Couldn't get under 200 KB without making it unreadable. Best result: 230 KB."
- "Video tools need FFmpeg. **Download it** (≈ 80 MB) or install with winget."
- "This file says .jpg but isn't an image, so Spinfix left it alone."

## 11. Credits

Inspired by the open-source projects **Ryshift** (alexriderspy), **DragShift** (llamaboi55)
and **McGyver** (ferdiunal), all MIT-licensed. Spinfix is an independent implementation.
