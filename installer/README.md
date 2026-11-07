# Installer

Spinfix ships as a per-user installer (no admin rights) built with Inno Setup 6, plus a
portable zip.

```
pip install --require-hashes -r requirements-dev.lock
pyinstaller --noconfirm --clean packaging/spinfix.spec      # -> dist\Spinfix\
iscc /DAppVersion=0.1.0 installer\spinfix.iss               # -> installer\Output\
```

What the installer does:
- copies the app to `%LOCALAPPDATA%\Programs\Spinfix`
- adds a Start menu shortcut, and optionally a desktop shortcut, "Spinfix…" on the
  right-click menu (HKCU) and Spinfix in **Send to**
- removes all of that on uninstall, plus `%LOCALAPPDATA%\Spinfix` and `%APPDATA%\Spinfix`

Release builds are made only by CI from a tagged commit (`.github/workflows/release.yml`).
