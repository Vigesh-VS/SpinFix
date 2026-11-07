<p align="center">
  <img src="assets/logo/spinfix-logo.png" width="140" alt="Spinfix logo">
</p>

<h1 align="center">Spinfix</h1>
<p align="center"><b>Spin. Drop. Fixed.</b><br>
Drag any file, press Shift, drop it on a wheel. Spinfix converts, compresses or fixes it
right next to the original — offline, free and open source.</p>

---

## What it does

Start dragging a file in File Explorer (or on the Desktop), press **Shift**, and a wheel
opens under your cursor. Drop the file on a slice:

| Wheel | For images | For PDFs | For video / audio | For anything |
|---|---|---|---|---|
| **Convert** | JPG, PNG, WEBP, PDF, TIFF, BMP, GIF · HEIC/AVIF input · several images → one PDF | JPG / PNG per page · Text | MP3, M4A, WAV | — |
| **Edit** | Crop · Edit (turn, flip, brightness, contrast, colour, size) · Annotate · Redact · Add background | — | — | — |
| **Tools** | Compress · **Under 200 KB / 500 KB / 1 MB / any size** · Resize (half, 1080 px, 4K, custom) · Remove info · Remove location | Merge · Split · Pick pages · Rotate · Compress · **Under 1 MB / 2 MB / any size** | **WhatsApp 16 MB** · Email 25 MB · 100 MB | Unzip (safe) |
| **Smart** | Copy text from image (Windows OCR) | — | — | — |
| **Share** | — | — | — | Copy path · Copy file · Zip |

Tap **Shift** again while dragging to switch wheels. Drop on the centre, or press **Esc**, to cancel.

No drag? Select files and press **Ctrl + Alt + Space**, right-click → **Spinfix…**, use
**Send to → Spinfix**, or double-click the tray icon.

## Rules you can trust

- The original file is **never changed**. Results are saved next to it (`photo (1).jpg` if
  the name is taken), or in a `Spinfix` subfolder if you prefer.
- **Undo** moves results to the Recycle Bin.
- **Nothing is uploaded.** No account, no ads, no tracking, no network access at all.
- Every file is treated as untrusted: type checked by its content, size limits, zip-bomb
  and zip-slip protection, no scripts or macros ever run.

## Install

Download `Spinfix-x.y.z-setup.exe` from [Releases](https://github.com/Vigesh-VS/SpinFix/releases)
(no admin rights needed), or the portable zip. Check the SHA-256 against `SHA256SUMS.txt`.

Video tools need FFmpeg: `winget install Gyan.FFmpeg`.

See [HOWTO.md](HOWTO.md) for install, use, uninstall and FAQ.

## Build from source

```
python -m venv .venv
.venv\Scripts\activate
pip install --require-hashes -r requirements-dev.lock
python -m spinfix              # run the app
python -m spinfix.cli list photo.heic
python -m spinfix.cli run image.under_custom photo.jpg -o target_size=200KB
pytest -q
```

Design: [docs/DOCUMENTATION.md](docs/DOCUMENTATION.md) · Plan: [docs/PLAN.md](docs/PLAN.md) ·
Security: [SECURITY.md](SECURITY.md)

## Licence

MIT — Copyright (c) 2026 Vigesh. Third-party licences: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Inspired by the open-source projects Ryshift, DragShift and McGyver. Spinfix is an
independent implementation.
