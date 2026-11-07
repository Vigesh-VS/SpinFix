# Third-Party Notices

Spinfix is licensed under the MIT License (see `LICENSE`). Copyright (c) 2026 Vigesh.

Spinfix bundles the libraries below in its Windows build. Each keeps its own licence.
LGPL libraries are used as unmodified, dynamically loaded libraries (separate DLLs/.pyd
files in the install folder) and can be replaced by the user.

## Bundled with the app

| Library | Licence | Used for | Source |
|---|---|---|---|
| Python 3.12 runtime | PSF-2.0 | Runs the app | https://www.python.org |
| PySide6-Essentials, shiboken6 (Qt 6) | LGPL-3.0 (Qt open-source licence) | User interface | https://code.qt.io/cgit/pyside/pyside-setup.git |
| Pillow | MIT-CMU (HPND) | Images | https://github.com/python-pillow/Pillow |
| pi-heif | BSD-3-Clause | Reading HEIC/HEIF | https://github.com/bigcat88/pillow_heif |
| ↳ libheif | LGPL-3.0 | HEIF decoding (bundled DLL) | https://github.com/strukturag/libheif |
| ↳ libde265 | LGPL-3.0 | HEVC decoding (bundled DLL) | https://github.com/strukturag/libde265 |
| ↳ libstdc++, libgcc (MinGW runtime) | GPL-3.0 with GCC Runtime Library Exception | C++ runtime for the above | https://gcc.gnu.org |
| ↳ libwinpthread | MIT / BSD | Threads for the above | https://www.mingw-w64.org |
| pypdfium2 | Apache-2.0 / BSD-3-Clause | PDF rendering and text | https://github.com/pypdfium2-team/pypdfium2 |
| ↳ PDFium | BSD-3-Clause / Apache-2.0 | PDF engine | https://pdfium.googlesource.com/pdfium |
| pikepdf | MPL-2.0 | PDF merge, split, rotate, compress | https://github.com/pikepdf/pikepdf |
| ↳ qpdf | Apache-2.0 | PDF engine for pikepdf | https://github.com/qpdf/qpdf |
| ↳ lxml | BSD-3-Clause | XML for pikepdf | https://github.com/lxml/lxml |
| packaging, typing-extensions | Apache-2.0 / BSD-2-Clause, PSF-2.0 | Helpers used by the libraries above | |
| pywin32 | PSF-2.0 | Windows APIs | https://github.com/mhammond/pywin32 |
| winrt-runtime, winrt-Windows.* | MIT | Windows OCR | https://github.com/pywinrt/pywinrt |
| Send2Trash | BSD-3-Clause | Undo to the Recycle Bin | https://github.com/arsenetar/send2trash |

Why **pi-heif** and not pillow-heif: the pillow-heif Windows wheel also bundles the
GPL-licensed x265 encoder. Spinfix only needs to *read* HEIC, so it uses the decode-only
pi-heif build, which contains no GPL encoder.

## Not bundled

- **FFmpeg** — used for video/audio only if the user installs it themselves
  (e.g. `winget install Gyan.FFmpeg`). It runs as a separate program and is never
  shipped with Spinfix.

## Build and development tools (not shipped as libraries)

| Tool | Licence |
|---|---|
| PyInstaller (bootloader included in Spinfix.exe) | GPL-2.0-or-later with the bootloader exception, which allows any licence for the built app |
| Inno Setup | Inno Setup licence (free, modified BSD-style) |
| ruff, mypy, pytest, pytest-qt, pre-commit, setuptools, gitleaks | MIT |
| bandit, pip-audit | Apache-2.0 |
| pip-tools | BSD-3-Clause |

## Inspiration

Spinfix's ideas were inspired by **Ryshift** (alexriderspy), **DragShift** (llamaboi55)
and **McGyver** (ferdiunal), all MIT-licensed. No code has been copied from them. If any
code is ever adapted, its copyright notice will be added here.
