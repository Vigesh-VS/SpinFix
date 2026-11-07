# Spinfix — How to

## Install

1. Download `Spinfix-x.y.z-setup.exe` from the
   [Releases page](https://github.com/Vigesh-VS/SpinFix/releases).
2. (Optional, recommended) check it hasn't been tampered with: in PowerShell run
   `Get-FileHash .\Spinfix-x.y.z-setup.exe` and compare with `SHA256SUMS.txt`.
3. Run it. No admin rights are needed; Spinfix installs into
   `%LOCALAPPDATA%\Programs\Spinfix`.
4. Choose whether you want "Spinfix…" on the right-click menu and in **Send to**.

**Portable:** unzip `Spinfix-x.y.z-portable.zip` anywhere and run `Spinfix.exe`.

### "Windows protected your PC" (SmartScreen)

New apps without a long download history can trigger this blue box. Click
**More info → Run anyway**. Release builds are made only by GitHub Actions from tagged
source code and published with SHA-256 checksums.

## Use

| You want to… | Do this |
|---|---|
| Convert / compress / fix a file | Start dragging it, press **Shift**, drop it on a slice |
| See other wheels | While the wheel is open, tap **Shift** again (or **Tab** in click mode) |
| Cancel | Drop on the centre, press **Esc**, or drop away from the wheel |
| Use selected files | Select them in Explorer and press **Ctrl + Alt + Space** |
| Use the menu | Right-click → **Spinfix…**, or **Send to → Spinfix** |
| Pick files | Double-click the tray icon |
| Undo | Click **Undo** on the message — results go to the Recycle Bin |
| Pause Spinfix | Tray icon → **Pause** |

Click mode (hotkey / menu): click a slice or press its number **1–8**.

### Video tools

They need FFmpeg (free). Install it once with `winget install Gyan.FFmpeg`, or point
Spinfix at `ffmpeg.exe` in **Settings**. Spinfix never downloads anything by itself.

### Check that everything works

Run `Spinfix.exe --self-test` (from the install folder). It converts a test image and PDF
in a temporary folder and shows PASS/FAIL for each part.

## Settings

Tray icon → **Settings**: trigger key (Shift / Ctrl / Alt), hotkey, where results go,
JPG quality, PDF → image sharpness, keeping photo info, messages, start with Windows,
FFmpeg location. Changes save instantly.

## Uninstall

**Settings → Apps → Installed apps → Spinfix → Uninstall.** This removes the app, the
right-click entry, Send to, the startup entry, settings (`%APPDATA%\Spinfix`), logs and
temp files (`%LOCALAPPDATA%\Spinfix`). Files you made with Spinfix stay where they are.

## FAQ

**Does Spinfix upload my files?** No. Spinfix has no network code; everything happens on
your PC.

**Will it change my original?** Never. It always writes a new file next to it.

**Is it a keylogger?** No. It checks only whether the mouse button, your trigger key and
Esc are pressed (the same way games read the keyboard) and stores nothing. There are no
keyboard hooks.

**The hotkey doesn't work.** Another app may already use Ctrl + Alt + Space. Spinfix shows
a message when that happens — choose a different one in Settings.

**"This file says .jpg but isn't an image."** Spinfix checks what a file really is. A file
with a fake extension is left alone for your safety.

**HEIC from iPhone?** Supported for reading (convert to JPG/PNG, compress, etc.).

**Where is the log?** `%LOCALAPPDATA%\Spinfix\logs\spinfix.log`. It records actions, file
types, sizes and timings — never file contents or full paths.
