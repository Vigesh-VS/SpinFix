# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Copy text from an image using the OCR engine built into Windows (no download)."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from PIL import Image

from spinfix.actions.images import INPUT_KINDS, open_image
from spinfix.core.errors import UserError, get_logger
from spinfix.core.filetype import FileInfo
from spinfix.core.registry import Action, JobContext, Options, Registry, Wheel

log = get_logger("ocr")

NO_ENGINE = (
    "Windows OCR isn't available. Add a language with OCR in Settings → Time & language → Language."
)


def _engine() -> Any:  # winrt types are dynamic
    try:
        from winrt.windows.media.ocr import OcrEngine  # noqa: PLC0415 — Windows only
    except ImportError:
        return None
    return OcrEngine.try_create_from_user_profile_languages()


def ocr_available() -> bool:
    try:
        return _engine() is not None
    except OSError:
        return False


async def _recognize(img: Image.Image) -> str:
    from winrt.windows.graphics.imaging import (  # noqa: PLC0415
        BitmapAlphaMode,
        BitmapPixelFormat,
        SoftwareBitmap,
    )
    from winrt.windows.media.ocr import OcrEngine  # noqa: PLC0415
    from winrt.windows.storage.streams import DataWriter  # noqa: PLC0415

    engine = _engine()
    if engine is None:
        raise UserError(NO_ENGINE)
    limit = int(OcrEngine.max_image_dimension)
    if max(img.size) > limit:
        f = limit / max(img.size)
        img = img.resize((max(1, int(img.width * f)), max(1, int(img.height * f))))
    rgba = img.convert("RGBA")
    r, g, b, a = rgba.split()
    bgra = Image.merge("RGBA", (b, g, r, a)).tobytes()
    writer = DataWriter()
    writer.write_bytes(bgra)
    bitmap = SoftwareBitmap.create_copy_from_buffer(
        writer.detach_buffer(),
        BitmapPixelFormat.BGRA8,
        rgba.width,
        rgba.height,
        BitmapAlphaMode.PREMULTIPLIED,
    )
    result = await engine.recognize_async(bitmap)
    return "\n".join(line.text for line in result.lines)


def recognize(img: Image.Image) -> str:
    return asyncio.run(_recognize(img))


class CopyText(Action):
    id = "ocr.copy_text"
    title = "Copy text"
    icon = "ocr"
    wheel = Wheel.SMART
    order = 10
    kinds = INPUT_KINDS

    def available(self) -> str | None:
        return None if ocr_available() else NO_ENGINE

    def run(self, inputs: Sequence[FileInfo], options: Options, ctx: JobContext) -> list[Path]:
        texts: list[str] = []
        for i, info in enumerate(inputs):
            ctx.progress(i / len(inputs), f"Reading {info.path.name}")
            img = open_image(info.path, ctx.limits)
            text = recognize(img).strip()
            if text:
                texts.append(text)
        if not texts:
            raise UserError("Spinfix couldn't find any text in this image.")
        ctx.clipboard_text = "\n\n".join(texts)
        if options.get("save_txt"):
            tmp = ctx.temp_file("text.txt")
            tmp.write_text(ctx.clipboard_text + "\n", encoding="utf-8")
            src = inputs[0].path
            return [ctx.save(tmp, src, f"{src.stem}.txt")]
        return []


def register(registry: Registry) -> None:
    registry.register(CopyText())
