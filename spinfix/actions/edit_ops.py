# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Pure image operations behind the editors (no UI, so they can be unit-tested)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps

Box = tuple[int, int, int, int]  # left, top, right, bottom in image pixels

RATIOS: dict[str, float | None] = {
    "Free": None,
    "1:1": 1.0,
    "4:5": 4 / 5,
    "9:16": 9 / 16,
    "16:9": 16 / 9,
    "A4": 1 / 1.4142,
}


def clamp_box(box: Box, size: tuple[int, int]) -> Box:
    w, h = size
    left, top, right, bottom = box
    left, right = sorted((max(0, min(w, left)), max(0, min(w, right))))
    top, bottom = sorted((max(0, min(h, top)), max(0, min(h, bottom))))
    return left, top, right, bottom


def crop(img: Image.Image, box: Box) -> Image.Image:
    box = clamp_box(box, img.size)
    if box[2] - box[0] < 1 or box[3] - box[1] < 1:
        raise ValueError("empty crop")
    return img.crop(box)


def fit_ratio(box: Box, ratio: float | None, size: tuple[int, int]) -> Box:
    """Shrink a box (around its centre) to an aspect ratio, inside the image."""
    box = clamp_box(box, size)
    if ratio is None:
        return box
    left, top, right, bottom = box
    w, h = right - left, bottom - top
    if w <= 0 or h <= 0:
        return box
    if w / h > ratio:
        new_w, new_h = round(h * ratio), h
    else:
        new_w, new_h = w, round(w / ratio)
    cx, cy = (left + right) // 2, (top + bottom) // 2
    return clamp_box(
        (cx - new_w // 2, cy - new_h // 2, cx - new_w // 2 + new_w, cy - new_h // 2 + new_h), size
    )


@dataclass
class Adjustments:
    rotate: int = 0  # multiples of 90, clockwise
    flip_h: bool = False
    flip_v: bool = False
    brightness: int = 0  # -100..100
    contrast: int = 0
    saturation: int = 0
    width: int = 0  # 0 = keep


def adjust(img: Image.Image, a: Adjustments) -> Image.Image:
    out = img
    turns = (a.rotate // 90) % 4
    if turns:
        out = out.transpose(
            {
                1: Image.Transpose.ROTATE_270,
                2: Image.Transpose.ROTATE_180,
                3: Image.Transpose.ROTATE_90,
            }[turns]
        )
    if a.flip_h:
        out = ImageOps.mirror(out)
    if a.flip_v:
        out = ImageOps.flip(out)
    alpha = out.getchannel("A") if out.mode == "RGBA" else None
    rgb = out.convert("RGB")
    for value, enhancer in (
        (a.brightness, ImageEnhance.Brightness),
        (a.contrast, ImageEnhance.Contrast),
        (a.saturation, ImageEnhance.Color),
    ):
        if value:
            rgb = enhancer(rgb).enhance(1 + value / 100)
    if alpha is not None:
        rgb.putalpha(alpha)
    out = rgb
    if a.width and a.width != out.width:
        height = max(1, round(out.height * a.width / out.width))
        out = out.resize((a.width, height), Image.Resampling.LANCZOS)
    return out


def redact(img: Image.Image, boxes: Sequence[Box], mode: str = "box") -> Image.Image:
    """Destroy the pixels in each box (black fill or heavy pixelation). Returns a copy."""
    out = img.convert("RGBA" if img.mode in ("RGBA", "LA", "P") else "RGB").copy()
    draw = ImageDraw.Draw(out)
    for raw in boxes:
        box = clamp_box(raw, out.size)
        w, h = box[2] - box[0], box[3] - box[1]
        if w < 1 or h < 1:
            continue
        if mode == "pixelate":
            region = out.crop(box)
            block = max(8, max(w, h) // 12)
            small = region.resize(
                (max(1, w // block), max(1, h // block)), Image.Resampling.BILINEAR
            )
            out.paste(small.resize((w, h), Image.Resampling.NEAREST), box[:2])
        else:
            fill = (0, 0, 0, 255) if out.mode == "RGBA" else (0, 0, 0)
            draw.rectangle((box[0], box[1], box[2] - 1, box[3] - 1), fill=fill)
    return out


GRADIENTS: dict[str, tuple[tuple[int, int, int], tuple[int, int, int]]] = {
    "Sunset": ((255, 94, 58), (255, 42, 104)),
    "Ocean": ((33, 150, 243), (0, 201, 167)),
    "Grape": ((106, 17, 203), (37, 117, 252)),
    "Mint": ((67, 233, 123), (56, 249, 215)),
    "Night": ((20, 20, 26), (60, 60, 72)),
    "Paper": ((246, 244, 238), (226, 222, 212)),
    "White": ((255, 255, 255), (255, 255, 255)),
    "Spinfix": ((255, 85, 20), (16, 16, 20)),
}


@dataclass
class Background:
    style: str = "Sunset"
    padding: int = 8  # percent of the image's longer side
    radius: int = 3  # percent
    shadow: bool = True
    ratio: str = "Auto"  # Auto or a key of RATIOS


def _gradient(
    size: tuple[int, int], a: tuple[int, int, int], b: tuple[int, int, int]
) -> Image.Image:
    w, h = size
    base = Image.new("RGB", (2, 2))
    base.putdata(
        [
            a,
            (a[0] // 2 + b[0] // 2, a[1] // 2 + b[1] // 2, a[2] // 2 + b[2] // 2),
            (a[0] // 2 + b[0] // 2, a[1] // 2 + b[1] // 2, a[2] // 2 + b[2] // 2),
            b,
        ]
    )
    return base.resize((w, h), Image.Resampling.BILINEAR)


def add_background(img: Image.Image, bg: Background) -> Image.Image:
    src = img.convert("RGBA")
    long_side = max(src.size)
    pad = round(long_side * bg.padding / 100)
    w, h = src.width + 2 * pad, src.height + 2 * pad
    ratio = RATIOS.get(bg.ratio) if bg.ratio != "Auto" else None
    if ratio:
        if w / h < ratio:
            w = round(h * ratio)
        else:
            h = round(w / ratio)
    a, b = GRADIENTS.get(bg.style, GRADIENTS["Sunset"])
    canvas = _gradient((w, h), a, b).convert("RGBA")
    x, y = (w - src.width) // 2, (h - src.height) // 2
    radius = round(min(src.size) * bg.radius / 100)
    mask = Image.new("L", src.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, src.width - 1, src.height - 1), radius=radius, fill=255
    )
    if bg.shadow and pad > 0:
        shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        offset = max(2, pad // 6)
        shadow.paste((0, 0, 0, 110), (x + offset, y + offset), mask)
        canvas = Image.alpha_composite(
            canvas, shadow.filter(ImageFilter.GaussianBlur(max(2, pad // 3)))
        )
    if src.mode == "RGBA":
        mask = Image.composite(src.getchannel("A"), Image.new("L", src.size, 0), mask)
    canvas.paste(src, (x, y), mask)
    return canvas
