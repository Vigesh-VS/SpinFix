# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""PDF actions: to images, to text, merge, split, extract, rotate, compress.

Safety: pypdfium2 is used without a form environment, so embedded JavaScript never runs.
pikepdf never runs scripts or opens attachments. Page counts and render sizes are capped.
"""

from __future__ import annotations

import io
from collections.abc import Callable, Iterator, Sequence
from contextlib import ExitStack, contextmanager
from pathlib import Path
from typing import ClassVar

import pikepdf
import pypdfium2 as pdfium
from PIL import Image

from spinfix.actions.common import (
    for_each,
    opt_int,
    output_folder,
    parse_page_ranges,
    parse_size,
    save_into,
)
from spinfix.core import safe_io
from spinfix.core.errors import UserError
from spinfix.core.filetype import FileInfo, Kind
from spinfix.core.limits import Limits
from spinfix.core.registry import Action, JobContext, Options, Registry, Wheel

LOCKED = "This PDF is password-protected. Use Unlock first."
DAMAGED = "{name} looks damaged and couldn't be opened."


@contextmanager
def open_pike(path: Path, limits: Limits) -> Iterator[pikepdf.Pdf]:
    try:
        pdf = pikepdf.open(path)
    except pikepdf.PasswordError:
        raise UserError(LOCKED) from None
    except (pikepdf.PdfError, OSError, ValueError) as exc:
        raise UserError(DAMAGED.format(name=path.name)) from exc
    try:
        if len(pdf.pages) > limits.max_pdf_pages:
            raise UserError(f"This PDF has more than {limits.max_pdf_pages} pages.")
        yield pdf
    finally:
        pdf.close()


@contextmanager
def open_pdfium(path: Path, limits: Limits) -> Iterator[pdfium.PdfDocument]:
    try:
        doc = pdfium.PdfDocument(path)
    except pdfium.PdfiumError as exc:
        if "password" in str(exc).lower():
            raise UserError(LOCKED) from None
        raise UserError(DAMAGED.format(name=path.name)) from exc
    try:
        if len(doc) > limits.max_pdf_pages:
            raise UserError(f"This PDF has more than {limits.max_pdf_pages} pages.")
        yield doc
    finally:
        doc.close()


def _save_pike(pdf: pikepdf.Pdf, target: Path, *, compress: bool = False) -> None:
    pdf.remove_unreferenced_resources()
    if compress:
        pdf.save(
            target,
            compress_streams=True,
            object_stream_mode=pikepdf.ObjectStreamMode.generate,
            recompress_flate=True,
            linearize=False,
        )
    else:
        pdf.save(target)


class PdfAction(Action):
    kinds: ClassVar[frozenset[Kind]] = frozenset({Kind.PDF})

    def run(self, inputs: Sequence[FileInfo], options: Options, ctx: JobContext) -> list[Path]:
        return for_each(inputs, ctx, lambda info, sub: self.one(info, options, ctx, sub))

    def one(
        self, info: FileInfo, options: Options, ctx: JobContext, sub: Callable[[float], None]
    ) -> list[Path]:
        raise NotImplementedError


class PdfToImages(PdfAction):
    wheel = Wheel.CONVERT

    def __init__(self, fmt: str, order: int) -> None:
        self.fmt = fmt
        self.id = f"pdf.to_{fmt}"  # type: ignore[misc]
        self.title = fmt.upper()  # type: ignore[misc]
        self.icon = f"to-{fmt}"  # type: ignore[misc]
        self.order = order  # type: ignore[misc]

    def one(
        self, info: FileInfo, options: Options, ctx: JobContext, sub: Callable[[float], None]
    ) -> list[Path]:
        dpi = opt_int(options, "dpi", 150, 36, ctx.limits.max_render_dpi)
        ext = ".jpg" if self.fmt == "jpg" else ".png"
        with open_pdfium(info.path, ctx.limits) as doc:
            count = len(doc)
            folder: Path | None = None
            if count > 1:
                folder = output_folder(ctx, info.path, f"{info.path.stem} images")
            outputs: list[Path] = []
            for i in range(count):
                sub(i / count)
                page = doc[i]
                w, h = page.get_size()
                scale = dpi / 72
                if w * h * scale * scale > ctx.limits.max_render_pixels:
                    scale = (ctx.limits.max_render_pixels / (w * h)) ** 0.5
                img = page.render(scale=scale).to_pil()
                page.close()
                tmp = ctx.temp_file(f"p{i + 1}{ext}")
                if ext == ".jpg":
                    img.convert("RGB").save(tmp, "JPEG", quality=90, optimize=True)
                else:
                    img.save(tmp, "PNG", optimize=True)
                width = len(str(count))
                name = f"{info.path.stem} p{i + 1:0{width}d}{ext}"
                if folder is None:
                    outputs.append(ctx.save(tmp, info.path, name))
                else:
                    save_into(ctx, tmp, folder, name)
            return outputs if folder is None else [folder]


class PdfToText(PdfAction):
    id = "pdf.to_txt"
    title = "Text"
    icon = "text"
    wheel = Wheel.CONVERT
    order = 30

    def one(
        self, info: FileInfo, options: Options, ctx: JobContext, sub: Callable[[float], None]
    ) -> list[Path]:
        parts: list[str] = []
        with open_pdfium(info.path, ctx.limits) as doc:
            count = len(doc)
            for i in range(count):
                sub(i / count)
                page = doc[i]
                textpage = page.get_textpage()
                parts.append(textpage.get_text_bounded())
                textpage.close()
                page.close()
        text = "\n\f\n".join(p.replace("\r\n", "\n") for p in parts).strip()
        if not text:
            raise UserError("This PDF has no text layer (it's probably a scan).")
        tmp = ctx.temp_file("text.txt")
        tmp.write_text(text + "\n", encoding="utf-8")
        return [ctx.save(tmp, info.path, safe_io.output_name(info.path, ".txt"))]


class MergePdfs(Action):
    id = "pdf.merge"
    title = "Merge"
    icon = "merge"
    wheel = Wheel.TOOLS
    order = 10
    kinds = frozenset({Kind.PDF})
    min_files = 2

    def run(self, inputs: Sequence[FileInfo], options: Options, ctx: JobContext) -> list[Path]:
        total_pages = 0
        tmp = ctx.temp_file("merged.pdf")
        # Sources must stay open until the merged file is saved.
        with ExitStack() as stack, pikepdf.new() as merged:
            for i, info in enumerate(inputs):
                ctx.progress(i / (len(inputs) + 1), f"Adding {info.path.name}")
                src = stack.enter_context(open_pike(info.path, ctx.limits))
                total_pages += len(src.pages)
                if total_pages > ctx.limits.max_pdf_pages:
                    raise UserError(
                        f"Together these PDFs have over {ctx.limits.max_pdf_pages} pages."
                    )
                merged.pages.extend(src.pages)
            ctx.progress(len(inputs) / (len(inputs) + 1), "Saving")
            _save_pike(merged, tmp)
        first = inputs[0].path
        return [ctx.save(tmp, first, safe_io.output_name(first, ".pdf", "merged"))]


class SplitPdf(PdfAction):
    id = "pdf.split"
    title = "Split pages"
    icon = "split"
    wheel = Wheel.TOOLS
    order = 20

    def one(
        self, info: FileInfo, options: Options, ctx: JobContext, sub: Callable[[float], None]
    ) -> list[Path]:
        with open_pike(info.path, ctx.limits) as src:
            count = len(src.pages)
            if count < 2:
                raise UserError("This PDF has only one page.")
            folder = output_folder(ctx, info.path, f"{info.path.stem} pages")
            width = len(str(count))
            for i, page in enumerate(src.pages):
                sub(i / count)
                single = pikepdf.new()
                single.pages.append(page)
                tmp = ctx.temp_file(f"p{i + 1}.pdf")
                _save_pike(single, tmp)
                single.close()
                save_into(ctx, tmp, folder, f"{info.path.stem} p{i + 1:0{width}d}.pdf")
        return [folder]


class ExtractPages(PdfAction):
    id = "pdf.extract"
    title = "Pick pages…"
    icon = "pages"
    wheel = Wheel.TOOLS
    order = 21
    asks = "pages"

    def one(
        self, info: FileInfo, options: Options, ctx: JobContext, sub: Callable[[float], None]
    ) -> list[Path]:
        text = str(options.get("pages", "")).strip()
        if not text:
            raise UserError("Tell Spinfix which pages, for example 1-3, 5.")
        with open_pike(info.path, ctx.limits) as src:
            indexes = parse_page_ranges(text, len(src.pages))
            out = pikepdf.new()
            for n, i in enumerate(indexes):
                sub(n / len(indexes))
                out.pages.append(src.pages[i])
            tmp = ctx.temp_file("pages.pdf")
            _save_pike(out, tmp)
            out.close()
        label = "pages " + text.replace(" ", "")
        return [ctx.save(tmp, info.path, safe_io.output_name(info.path, ".pdf", label))]


class RotatePdf(PdfAction):
    wheel = Wheel.TOOLS

    def __init__(self, degrees: int, title: str, order: int) -> None:
        self.degrees = degrees
        self.id = f"pdf.rotate_{degrees}"  # type: ignore[misc]
        self.title = title  # type: ignore[misc]
        self.icon = "rotate-right" if degrees == 90 else "rotate-left"  # type: ignore[misc]
        if degrees == 180:
            self.icon = "rotate-180"  # type: ignore[misc]
        self.order = order  # type: ignore[misc]

    def one(
        self, info: FileInfo, options: Options, ctx: JobContext, sub: Callable[[float], None]
    ) -> list[Path]:
        with open_pike(info.path, ctx.limits) as src:
            for page in src.pages:
                page.rotate(self.degrees, relative=True)
            tmp = ctx.temp_file("rotated.pdf")
            _save_pike(src, tmp)
        return [ctx.save(tmp, info.path, safe_io.output_name(info.path, ".pdf", "rotated"))]


def _recompress_images(pdf: pikepdf.Pdf, max_dpi: int, quality: int, ctx: JobContext) -> None:
    """Downsample and re-encode big raster images as JPEG."""
    seen: set[tuple[int, int]] = set()
    pages = list(pdf.pages)
    for n, page in enumerate(pages):
        ctx.check_cancel()
        width_pt = float(page.mediabox[2]) - float(page.mediabox[0])
        for _name, raw in page.get_images().items():
            key = raw.objgen
            if key in seen:
                continue
            seen.add(key)
            try:
                pdfimg = pikepdf.PdfImage(raw)
                if pdfimg.width * pdfimg.height > ctx.limits.max_image_pixels:
                    continue
                if pdfimg.image_mask or pdfimg.bits_per_component != 8:
                    continue
                pil = pdfimg.as_pil_image()
            except (pikepdf.PdfError, NotImplementedError, ValueError, OSError):
                continue
            if pil.mode not in ("RGB", "L"):
                if pil.mode == "CMYK" or "/SMask" in raw:
                    continue
                pil = pil.convert("RGB")
            # Assume an image spans at most the page width to estimate its dpi.
            dpi = pil.width / max(width_pt / 72, 0.1)
            if dpi > max_dpi:
                f = max_dpi / dpi
                pil = pil.resize(
                    (max(1, int(pil.width * f)), max(1, int(pil.height * f))),
                    Image.Resampling.LANCZOS,
                )
            buf = io.BytesIO()
            pil.save(buf, "JPEG", quality=quality, optimize=True)
            data = buf.getvalue()
            if len(data) >= len(raw.read_raw_bytes()):
                continue
            raw.write(data, filter=pikepdf.Name.DCTDecode)
            raw.Width, raw.Height = pil.width, pil.height
            raw.ColorSpace = pikepdf.Name.DeviceGray if pil.mode == "L" else pikepdf.Name.DeviceRGB
            raw.BitsPerComponent = 8
            for key_name in ("/DecodeParms", "/Decode"):
                if key_name in raw:
                    del raw[key_name]
        ctx.progress_fn(n / max(len(pages), 1) * 0.9, "")


def compress_pdf(path: Path, target: Path, ctx: JobContext, max_dpi: int, quality: int) -> int:
    with open_pike(path, ctx.limits) as pdf:
        if max_dpi > 0:
            _recompress_images(pdf, max_dpi, quality, ctx)
        _save_pike(pdf, target, compress=True)
    return target.stat().st_size


LEVELS = ((150, 75), (120, 65), (100, 55), (85, 45), (72, 35), (60, 30))


class CompressPdf(PdfAction):
    id = "pdf.compress"
    title = "Compress"
    icon = "compress"
    wheel = Wheel.TOOLS
    order = 30

    def one(
        self, info: FileInfo, options: Options, ctx: JobContext, sub: Callable[[float], None]
    ) -> list[Path]:
        tmp = ctx.temp_file("compressed.pdf")
        size = compress_pdf(info.path, tmp, ctx, 150, 70)
        if size >= info.size:
            raise UserError(f"{info.path.name} is already as small as Spinfix can make it.")
        return [ctx.save(tmp, info.path, safe_io.output_name(info.path, ".pdf", "small"))]


class CompressPdfToSize(PdfAction):
    wheel = Wheel.TOOLS

    def __init__(self, label: str, target: str | None, order: int) -> None:
        self.default_target = target
        self.id = (  # type: ignore[misc]
            f"pdf.under_{label.lower().replace(' ', '')}" if target else "pdf.under_custom"
        )
        self.title = f"Under {label}" if target else "Under size…"  # type: ignore[misc]
        self.icon = "target"  # type: ignore[misc]
        self.order = order  # type: ignore[misc]
        self.asks = None if target else "target_size"  # type: ignore[misc]

    def one(
        self, info: FileInfo, options: Options, ctx: JobContext, sub: Callable[[float], None]
    ) -> list[Path]:
        raw = str(options.get("target_size") or self.default_target or "")
        if not raw:
            raise UserError("Tell Spinfix the size you need, for example 1MB.")
        target = parse_size(raw)
        if info.size <= target:
            raise UserError(f"{info.path.name} is already under {safe_io.human_size(target)}.")
        best: tuple[int, Path] | None = None
        for n, (dpi, quality) in enumerate(((0, 0), *LEVELS)):
            sub(n / (len(LEVELS) + 1))
            tmp = ctx.temp_file(f"try{n}.pdf")
            size = compress_pdf(info.path, tmp, ctx, dpi, quality)
            if best is None or size < best[0]:
                best = (size, tmp)
            if size <= target:
                break
        if best is None:  # the loop always runs at least once
            raise RuntimeError("no compression attempt")
        size, tmp = best
        if size >= info.size:
            raise UserError(
                f"Couldn't make {info.path.name} smaller. It probably has no big images."
            )
        label = f"under {safe_io.human_size(target)}"
        out = ctx.save(tmp, info.path, safe_io.output_name(info.path, ".pdf", label))
        if size > target:
            ctx.notes.append(
                f"Couldn't get under {safe_io.human_size(target)} without making it unreadable. "
                f"Best result: {safe_io.human_size(size)}."
            )
        return [out]


def register(registry: Registry) -> None:
    registry.register(PdfToImages("jpg", 10))
    registry.register(PdfToImages("png", 11))
    registry.register(PdfToText())
    registry.register(MergePdfs())
    registry.register(SplitPdf())
    registry.register(ExtractPages())
    registry.register(RotatePdf(90, "Rotate right", 22))
    registry.register(RotatePdf(270, "Rotate left", 23))
    registry.register(RotatePdf(180, "Upside down", 24))
    registry.register(CompressPdf())
    for order, (label, size) in enumerate((("1 MB", "1MB"), ("2 MB", "2MB")), start=31):
        registry.register(CompressPdfToSize(label, size, order))
    registry.register(CompressPdfToSize("custom", None, 35))
