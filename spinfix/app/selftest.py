# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""`Spinfix.exe --self-test`: run a few real jobs in a temp folder and report the result.

Useful after installing: it proves images, PDFs, zip, OCR and FFmpeg detection work
in this build on this PC. Nothing outside a temporary folder is touched.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from pathlib import Path

from spinfix import __version__


def run_checks() -> list[tuple[str, bool, str]]:
    import pikepdf  # noqa: PLC0415
    from PIL import Image, ImageDraw, ImageFont  # noqa: PLC0415

    from spinfix.actions import build_registry, media, ocr  # noqa: PLC0415
    from spinfix.core import filetype  # noqa: PLC0415
    from spinfix.core.jobs import Job  # noqa: PLC0415

    registry = build_registry()
    results: list[tuple[str, bool, str]] = []

    with tempfile.TemporaryDirectory(prefix="spinfix-selftest-") as tmp:
        folder = Path(tmp)
        photo = folder / "photo.png"
        img = Image.new("RGB", (900, 220), "white")
        font: ImageFont.FreeTypeFont | ImageFont.ImageFont
        try:
            font = ImageFont.truetype("arial.ttf", 72)
        except OSError:
            font = ImageFont.load_default()
        ImageDraw.Draw(img).text((30, 60), "Spinfix 123", fill="black", font=font)
        img.save(photo)
        pdf_path = folder / "doc.pdf"
        pdf = pikepdf.new()
        for _ in range(2):
            pdf.add_blank_page()
        pdf.save(pdf_path)

        def job(name: str, action: str, path: Path, check: Callable[[Job], str]) -> None:
            try:
                j = Job(registry.get(action), [filetype.check(path)])
                res = j.run()
                ok = res.ok
                detail = check(j) if ok else res.message
            except Exception as exc:
                ok, detail = False, f"{type(exc).__name__}: {exc}"
            results.append((name, ok, detail))

        def outputs(j: Job) -> str:
            if j.result is None:
                return ""
            return ", ".join(p.name for p in j.result.outputs)

        job("Image convert (PNG → JPG)", "image.to_jpg", photo, outputs)
        job("Image compress to size", "image.under_200kb", photo, outputs)
        job("PDF → images", "pdf.to_png", pdf_path, outputs)
        job("PDF rotate", "pdf.rotate_90", pdf_path, outputs)
        job("Zip", "archive.zip", photo, outputs)
        if ocr.ocr_available():
            job(
                "Copy text (Windows OCR)",
                "ocr.copy_text",
                photo,
                lambda j: (j.result.clipboard_text or "")[:40] if j.result else "",
            )
        else:
            results.append(("Copy text (Windows OCR)", False, ocr.NO_ENGINE))
        try:
            import pi_heif  # noqa: F401, PLC0415

            results.append(("HEIC support", True, "pi-heif loaded"))
        except ImportError as exc:
            results.append(("HEIC support", False, str(exc)))
        found = media.find_ffmpeg(refresh=True)
        results.append(
            (
                "FFmpeg (video tools)",
                found is not None,
                str(found) if found else "not installed — winget install Gyan.FFmpeg",
            )
        )
    return results


def report(results: list[tuple[str, bool, str]]) -> str:
    lines = [f"Spinfix {__version__} self-test", ""]
    for name, ok, detail in results:
        lines.append(f"{'PASS' if ok else 'FAIL'}  {name} — {detail}")
    return "\n".join(lines)


def show(results: list[tuple[str, bool, str]]) -> int:
    from PySide6.QtWidgets import QMessageBox  # noqa: PLC0415

    from spinfix.core.errors import get_logger  # noqa: PLC0415

    text = report(results)
    get_logger("selftest").info("\n%s", text)
    box = QMessageBox()
    box.setWindowTitle("Spinfix self-test")
    box.setText(text)
    box.exec()
    required_ok = all(ok for name, ok, _ in results if not name.startswith(("FFmpeg", "Copy")))
    return 0 if required_ok else 1
