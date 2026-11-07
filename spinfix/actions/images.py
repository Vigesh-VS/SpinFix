# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Image actions: convert, compress, compress to size, resize, strip metadata, to PDF."""

from __future__ import annotations

import io
import warnings
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, ClassVar

from PIL import Image, ImageOps, UnidentifiedImageError

from spinfix.actions.common import for_each, opt_int, parse_size
from spinfix.core import safe_io
from spinfix.core.errors import UserError
from spinfix.core.filetype import FileInfo, Kind
from spinfix.core.limits import Limits
from spinfix.core.registry import Action, JobContext, Options, Registry, Wheel

_heif_ready = False

GPS_IFD = 0x8825
ORIENTATION = 0x0112

# Output format -> (Pillow format, extension, supports alpha)
FORMATS: dict[str, tuple[str, str, bool]] = {
    "png": ("PNG", ".png", True),
    "jpg": ("JPEG", ".jpg", False),
    "webp": ("WEBP", ".webp", True),
    "tiff": ("TIFF", ".tiff", True),
    "bmp": ("BMP", ".bmp", False),
    "gif": ("GIF", ".gif", True),
    "pdf": ("PDF", ".pdf", False),
}
INPUT_KINDS = frozenset(
    {Kind.JPEG, Kind.PNG, Kind.GIF, Kind.WEBP, Kind.BMP, Kind.TIFF, Kind.HEIC, Kind.AVIF, Kind.ICO}
)
LOSSY = {"JPEG", "WEBP"}


def _enable_heif() -> None:
    global _heif_ready  # noqa: PLW0603 — one-time plugin registration
    if _heif_ready:
        return
    try:
        import pi_heif  # noqa: PLC0415 — optional decoder, loaded on first use

        pi_heif.register_heif_opener()
    except ImportError:  # pragma: no cover — package missing
        pass
    _heif_ready = True


def open_image(path: Path, limits: Limits) -> Image.Image:
    """Open an untrusted image safely: pixel cap, full decode, EXIF rotation applied."""
    _enable_heif()
    Image.MAX_IMAGE_PIXELS = limits.max_image_pixels
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(path)
            w, h = img.size
            if w * h > limits.max_image_pixels or w <= 0 or h <= 0:
                raise UserError(f"This image is too big to open safely ({w} x {h} pixels).")
            img.load()
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise UserError("This image is too big to open safely.") from None
    except UnidentifiedImageError:
        raise UserError(f"{path.name} isn't an image Spinfix can read.") from None
    except (OSError, SyntaxError, ValueError) as exc:
        raise UserError(f"{path.name} looks damaged and couldn't be opened.") from exc
    if getattr(img, "n_frames", 1) > 1 and img.format != "GIF":
        img.seek(0)
    rotated = ImageOps.exif_transpose(img)
    return rotated if rotated is not None else img


def _flatten(img: Image.Image, background: tuple[int, int, int] = (255, 255, 255)) -> Image.Image:
    """RGB with transparency composited on white (for JPEG, BMP, PDF)."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        base = Image.new("RGB", rgba.size, background)
        base.paste(rgba, mask=rgba.getchannel("A"))
        return base
    return img.convert("RGB") if img.mode != "RGB" else img


def _prepare(img: Image.Image, fmt: str) -> Image.Image:
    if fmt in ("JPEG", "BMP", "PDF"):
        return _flatten(img)
    if fmt == "GIF":
        return img if img.mode in ("P", "L") else img.convert("RGBA").quantize(256)
    if img.mode in ("I;16", "I", "F", "CMYK", "YCbCr", "LAB", "HSV"):
        return img.convert("RGB")
    return img


def _exif_bytes(img: Image.Image, keep: bool, strip_gps: bool = False) -> bytes | None:
    if not keep:
        return None
    exif = img.getexif()
    if not exif:
        return None
    exif.pop(ORIENTATION, None)  # pixels are already rotated
    if strip_gps:
        exif.pop(GPS_IFD, None)
    return exif.tobytes()


def encode(
    img: Image.Image,
    fmt: str,
    *,
    quality: int = 85,
    keep_metadata: bool = True,
    strip_gps: bool = False,
    source: Image.Image | None = None,
) -> bytes:
    """Encode an image to bytes in a Pillow format."""
    meta_src = source if source is not None else img
    out = _prepare(img, fmt)
    params: dict[str, Any] = {}
    exif = _exif_bytes(meta_src, keep_metadata, strip_gps)
    icc = meta_src.info.get("icc_profile") if keep_metadata else None
    if fmt == "JPEG":
        params.update(quality=quality, optimize=True, progressive=True)
        if quality < 90:
            params["subsampling"] = "4:2:0"
    elif fmt == "WEBP":
        params.update(quality=quality, method=6)
    elif fmt == "PNG":
        params.update(optimize=True)
    elif fmt == "TIFF":
        params.update(compression="tiff_lzw")
    elif fmt == "PDF":
        params.update(resolution=150.0)
    if exif and fmt in ("JPEG", "WEBP", "PNG", "TIFF"):
        params["exif"] = exif
    if icc and fmt in ("JPEG", "WEBP", "PNG", "TIFF"):
        params["icc_profile"] = icc
    buf = io.BytesIO()
    out.save(buf, fmt, **params)
    return buf.getvalue()


def _write_and_save(ctx: JobContext, data: bytes, source: Path, filename: str) -> Path:
    tmp = ctx.temp_file(filename)
    tmp.write_bytes(data)
    return ctx.save(tmp, source, filename)


def _keep_meta(options: Options, default: bool) -> bool:
    value = options.get("keep_metadata", default)
    return value if isinstance(value, bool) else str(value).lower() in ("1", "true", "yes")


class ImageAction(Action):
    kinds: ClassVar[frozenset[Kind]] = INPUT_KINDS

    def run(self, inputs: Sequence[FileInfo], options: Options, ctx: JobContext) -> list[Path]:
        return for_each(inputs, ctx, lambda info, sub: self.one(info, options, ctx, sub))

    def one(
        self, info: FileInfo, options: Options, ctx: JobContext, sub: Callable[[float], None]
    ) -> list[Path]:
        raise NotImplementedError


class ConvertImage(ImageAction):
    """Convert to another format. Same name, new extension."""

    wheel = Wheel.CONVERT

    def __init__(self, target: str, order: int) -> None:
        self.target = target
        self.id = f"image.to_{target}"  # type: ignore[misc]
        self.title = target.upper()  # type: ignore[misc]
        self.icon = f"to-{target}"  # type: ignore[misc]
        self.order = order  # type: ignore[misc]
        same = {
            "jpg": Kind.JPEG,
            "png": Kind.PNG,
            "webp": Kind.WEBP,
            "tiff": Kind.TIFF,
            "bmp": Kind.BMP,
            "gif": Kind.GIF,
        }.get(target)
        self.kinds = INPUT_KINDS - {same} if same else INPUT_KINDS  # type: ignore[misc]

    def one(
        self, info: FileInfo, options: Options, ctx: JobContext, sub: Callable[[float], None]
    ) -> list[Path]:
        fmt, ext, _alpha = FORMATS[self.target]
        img = open_image(info.path, ctx.limits)
        sub(0.4)
        quality = opt_int(options, "quality", 92 if fmt == "JPEG" else 90, 1, 100)
        data = encode(img, fmt, quality=quality, keep_metadata=_keep_meta(options, True))
        sub(0.9)
        return [_write_and_save(ctx, data, info.path, safe_io.output_name(info.path, ext))]


def same_format(info: FileInfo) -> tuple[str, str]:
    """Pick an output format for 'keep format' actions (HEIC/AVIF/ICO become JPG/PNG)."""
    mapping = {
        Kind.JPEG: ("JPEG", ".jpg"),
        Kind.PNG: ("PNG", ".png"),
        Kind.WEBP: ("WEBP", ".webp"),
        Kind.GIF: ("GIF", ".gif"),
        Kind.BMP: ("PNG", ".png"),
        Kind.TIFF: ("TIFF", ".tiff"),
        Kind.HEIC: ("JPEG", ".jpg"),
        Kind.AVIF: ("JPEG", ".jpg"),
        Kind.ICO: ("PNG", ".png"),
    }
    return mapping[info.kind]


class CompressImage(ImageAction):
    id = "image.compress"
    title = "Compress"
    icon = "compress"
    wheel = Wheel.TOOLS
    order = 10

    def one(
        self, info: FileInfo, options: Options, ctx: JobContext, sub: Callable[[float], None]
    ) -> list[Path]:
        img = open_image(info.path, ctx.limits)
        fmt, ext = same_format(info)
        if fmt in ("PNG", "TIFF", "GIF") and not _has_alpha(img):
            fmt, ext = "JPEG", ".jpg"  # photos saved as PNG shrink a lot as JPEG
        quality = opt_int(options, "quality", 75, 1, 100)
        keep = _keep_meta(options, False)
        if fmt == "PNG":
            data = encode(_quantize(img), "PNG", keep_metadata=keep, source=img)
        else:
            data = encode(img, fmt, quality=quality, keep_metadata=keep)
        sub(0.9)
        if len(data) >= info.size and ext == info.extension:
            raise UserError(f"{info.path.name} is already as small as Spinfix can make it.")
        name = safe_io.output_name(info.path, ext, "small")
        return [_write_and_save(ctx, data, info.path, name)]


def _has_alpha(img: Image.Image) -> bool:
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        low, _high = img.convert("RGBA").getchannel("A").getextrema()
        return isinstance(low, int | float) and low < 255
    return False


def _quantize(img: Image.Image) -> Image.Image:
    rgba = img.convert("RGBA")
    return rgba.quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.FLOYDSTEINBERG)


def compress_to_size(
    img: Image.Image,
    target: int,
    *,
    prefer: str,
    keep_metadata: bool,
    progress: Callable[[float], None] | None = None,
) -> tuple[bytes, str]:
    """Smallest good-looking encoding under `target` bytes.

    Binary-search the quality first; if even low quality is too big, shrink the
    resolution in steps. Returns (bytes, pillow format). If impossible, returns the
    best (smallest) attempt — the caller reports it.
    """
    fmt = prefer if prefer in LOSSY else "JPEG"
    if fmt == "WEBP" or _has_alpha(img):
        fmt = "WEBP" if _has_alpha(img) else fmt
    best: bytes | None = None
    scale = 1.0
    w0, h0 = img.size
    for step in range(12):
        current = (
            img
            if scale == 1.0
            else img.resize(
                (max(1, int(w0 * scale)), max(1, int(h0 * scale))), Image.Resampling.LANCZOS
            )
        )
        lo, hi = 35 if step == 0 else 50, 95
        found: bytes | None = None
        while lo <= hi:
            q = (lo + hi) // 2
            data = encode(current, fmt, quality=q, keep_metadata=keep_metadata, source=img)
            if len(data) <= target:
                found, lo = data, q + 1
            else:
                hi = q - 1
            if best is None or len(data) < len(best):
                best = data
        if found is not None:
            return found, fmt
        if progress:
            progress(min(0.9, 0.2 + step * 0.07))
        scale *= 0.85
        if min(w0, h0) * scale < 64:
            break
    if best is None:  # the loop always runs at least once
        raise RuntimeError("no encoding attempt")
    return best, fmt


class CompressToSize(ImageAction):
    """Compress to a target size such as 'under 200 KB'."""

    wheel = Wheel.TOOLS

    def __init__(self, label: str, target: str | None, order: int) -> None:
        self.default_target = target
        suffix = label.lower().replace(" ", "")
        self.id = f"image.under_{suffix}" if target else "image.under_custom"  # type: ignore[misc]
        self.title = f"Under {label}" if target else "Under size…"  # type: ignore[misc]
        self.icon = "target"  # type: ignore[misc]
        self.order = order  # type: ignore[misc]
        self.asks = None if target else "target_size"  # type: ignore[misc]

    def one(
        self, info: FileInfo, options: Options, ctx: JobContext, sub: Callable[[float], None]
    ) -> list[Path]:
        raw = str(options.get("target_size") or self.default_target or "")
        if not raw:
            raise UserError("Tell Spinfix the size you need, for example 200KB.")
        target = parse_size(raw)
        if info.size <= target and info.kind in (Kind.JPEG, Kind.WEBP):
            raise UserError(f"{info.path.name} is already under {safe_io.human_size(target)}.")
        img = open_image(info.path, ctx.limits)
        fmt0, _ = same_format(info)
        data, fmt = compress_to_size(
            img, target, prefer=fmt0, keep_metadata=_keep_meta(options, False), progress=sub
        )
        ext = ".webp" if fmt == "WEBP" else ".jpg"
        label = f"under {safe_io.human_size(target)}"
        out = _write_and_save(ctx, data, info.path, safe_io.output_name(info.path, ext, label))
        if len(data) > target:
            ctx.notes.append(
                f"Couldn't get under {safe_io.human_size(target)} without making it unreadable. "
                f"Best result: {safe_io.human_size(len(data))}."
            )
        return [out]


class ResizeImage(ImageAction):
    wheel = Wheel.TOOLS

    def __init__(self, preset: str, title: str, order: int) -> None:
        self.preset = preset
        self.id = f"image.resize_{preset}"  # type: ignore[misc]
        self.title = title  # type: ignore[misc]
        self.icon = "resize"  # type: ignore[misc]
        self.order = order  # type: ignore[misc]
        self.asks = "size" if preset == "custom" else None  # type: ignore[misc]

    def target_size(self, w: int, h: int, options: Options) -> tuple[int, int]:
        long_side = max(w, h)
        if self.preset == "half":
            return max(1, w // 2), max(1, h // 2)
        if self.preset in ("1080", "3840"):
            edge = int(self.preset)
            if long_side <= edge:
                raise UserError(f"This image is already {long_side} px or smaller.")
            f = edge / long_side
            return max(1, round(w * f)), max(1, round(h * f))
        width = opt_int(options, "width", 0, 0, 30000)
        height = opt_int(options, "height", 0, 0, 30000)
        if not width and not height:
            raise UserError("Give a width or a height.")
        if width and not height:
            height = max(1, round(h * width / w))
        elif height and not width:
            width = max(1, round(w * height / h))
        return width, height

    def one(
        self, info: FileInfo, options: Options, ctx: JobContext, sub: Callable[[float], None]
    ) -> list[Path]:
        img = open_image(info.path, ctx.limits)
        size = self.target_size(*img.size, options)
        if size[0] * size[1] > ctx.limits.max_image_pixels:
            raise UserError("That size is too large.")
        resized = img.resize(size, Image.Resampling.LANCZOS)
        sub(0.6)
        fmt, ext = same_format(info)
        data = encode(resized, fmt, quality=90, keep_metadata=True, source=img)
        label = f"{size[0]}x{size[1]}"
        return [_write_and_save(ctx, data, info.path, safe_io.output_name(info.path, ext, label))]


class StripMetadata(ImageAction):
    wheel = Wheel.TOOLS

    def __init__(self, gps_only: bool, order: int) -> None:
        self.gps_only = gps_only
        self.id = "image.strip_gps" if gps_only else "image.strip_metadata"  # type: ignore[misc]
        self.title = "Remove location" if gps_only else "Remove info"  # type: ignore[misc]
        self.icon = "location-off" if gps_only else "shield"  # type: ignore[misc]
        self.order = order  # type: ignore[misc]

    def one(
        self, info: FileInfo, options: Options, ctx: JobContext, sub: Callable[[float], None]
    ) -> list[Path]:
        img = open_image(info.path, ctx.limits)
        fmt, ext = same_format(info)
        params: dict[str, Any] = {}
        if fmt == "JPEG" and info.kind is Kind.JPEG and img.getexif().get(ORIENTATION, 1) == 1:
            # Re-use the original JPEG quantisation tables: no visible quality loss.
            with Image.open(info.path) as original:
                buf = io.BytesIO()
                exif = _exif_bytes(original, keep=self.gps_only, strip_gps=True)
                if exif:
                    params["exif"] = exif
                original.save(buf, "JPEG", quality="keep", **params)
                data = buf.getvalue()
        else:
            data = encode(img, fmt, quality=95, keep_metadata=self.gps_only, strip_gps=True)
        label = "no location" if self.gps_only else "clean"
        return [_write_and_save(ctx, data, info.path, safe_io.output_name(info.path, ext, label))]


class CombineToPdf(Action):
    id = "image.combine_pdf"
    title = "One PDF"
    icon = "pdf-stack"
    wheel = Wheel.CONVERT
    order = 80
    kinds = INPUT_KINDS
    min_files = 2

    def run(self, inputs: Sequence[FileInfo], options: Options, ctx: JobContext) -> list[Path]:
        pages: list[Image.Image] = []
        for i, info in enumerate(inputs):
            ctx.progress(i / (len(inputs) + 1), f"Adding {info.path.name}")
            pages.append(_flatten(open_image(info.path, ctx.limits)))
        tmp = ctx.temp_file("combined.pdf")
        pages[0].save(tmp, "PDF", save_all=True, append_images=pages[1:], resolution=150.0)
        first = inputs[0].path
        return [ctx.save(tmp, first, safe_io.output_name(first, ".pdf", "combined"))]


def register(registry: Registry) -> None:
    for order, target in enumerate(("jpg", "png", "webp", "pdf", "tiff", "bmp", "gif"), start=10):
        registry.register(ConvertImage(target, order))
    registry.register(CombineToPdf())
    registry.register(CompressImage())
    for order, (label, size) in enumerate(
        (("200 KB", "200KB"), ("500 KB", "500KB"), ("1 MB", "1MB")), start=20
    ):
        registry.register(CompressToSize(label, size, order))
    registry.register(CompressToSize("custom", None, 29))
    registry.register(ResizeImage("half", "Half size", 30))
    registry.register(ResizeImage("1080", "1080 px", 31))
    registry.register(ResizeImage("3840", "4K", 32))
    registry.register(ResizeImage("custom", "Resize…", 33))
    registry.register(StripMetadata(gps_only=False, order=40))
    registry.register(StripMetadata(gps_only=True, order=41))


__all__ = ["INPUT_KINDS", "compress_to_size", "encode", "open_image", "register"]
