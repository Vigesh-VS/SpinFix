# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Image, PDF, archive, share, media and OCR actions."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pikepdf
import pypdfium2 as pdfium
import pytest
from PIL import Image

from spinfix.actions import media, ocr
from spinfix.core.jobs import JobState
from tests.conftest import RunFn, make_image, make_pdf

# ------------------------------------------------------------------ images


@pytest.mark.parametrize(
    ("action", "ext", "fmt"),
    [
        ("image.to_jpg", ".jpg", "JPEG"),
        ("image.to_webp", ".webp", "WEBP"),
        ("image.to_tiff", ".tiff", "TIFF"),
        ("image.to_bmp", ".bmp", "BMP"),
        ("image.to_gif", ".gif", "GIF"),
    ],
)
def test_convert_png(run: RunFn, work: Path, action: str, ext: str, fmt: str) -> None:
    src = make_image(work / "photo.png", (120, 80), "RGBA", fmt="PNG")
    result = run(action, src)
    assert result.ok, result.message
    out = result.outputs[0]
    assert out.name == f"photo{ext}"
    with Image.open(out) as img:
        assert img.format == fmt and img.size == (120, 80)


def test_convert_to_png_and_pdf(run: RunFn, work: Path) -> None:
    src = make_image(work / "scan.jpg", (200, 300), fmt="JPEG")
    png = run("image.to_png", src).outputs[0]
    assert png.name == "scan.png"
    pdf = run("image.to_pdf", src).outputs[0]
    with pikepdf.open(pdf) as doc:
        assert len(doc.pages) == 1


def test_exif_orientation_applied(run: RunFn, work: Path) -> None:
    img = Image.new("RGB", (200, 100), "red")
    exif = img.getexif()
    exif[0x0112] = 6  # rotate 90° on display
    path = work / "phone.jpg"
    img.save(path, "JPEG", exif=exif.tobytes())
    out = run("image.to_png", path).outputs[0]
    with Image.open(out) as res:
        assert res.size == (100, 200)
        assert res.getexif().get(0x0112) in (None, 1)


def test_heic_input(run: RunFn, work: Path) -> None:
    pi_heif = pytest.importorskip("pi_heif")
    src = work / "iphone.heic"
    try:
        pi_heif.from_pillow(Image.new("RGB", (64, 48), "blue")).save(src)
    except Exception:
        pytest.skip("no HEIC sample can be created with the decode-only build")
    out = run("image.to_jpg", src).outputs[0]
    assert out.suffix == ".jpg"


def test_compress_photo_png_to_jpg(run: RunFn, work: Path) -> None:
    src = make_image(work / "photo.png", (800, 600), fmt="PNG", noise=True)
    result = run("image.compress", src)
    assert result.ok, result.message
    assert result.outputs[0].name == "photo small.jpg"
    assert result.output_bytes < src.stat().st_size


@pytest.mark.parametrize("target", [200 * 1024, 50 * 1024])
def test_compress_to_target(run: RunFn, work: Path, target: int) -> None:
    src = make_image(work / "big.jpg", (2400, 1800), fmt="JPEG", noise=True, quality=95)
    assert src.stat().st_size > target
    result = run("image.under_custom", src, options={"target_size": f"{target // 1024}KB"})
    assert result.ok, result.message
    assert result.outputs[0].stat().st_size <= target
    with Image.open(result.outputs[0]) as img:
        assert img.width > 100


def test_compress_to_impossible_target_reports_best(run: RunFn, work: Path) -> None:
    src = make_image(work / "noise.png", (1200, 1200), fmt="PNG", noise=True)
    result = run("image.under_custom", src, options={"target_size": "1KB"})
    assert result.ok
    assert any("Best result" in n for n in result.notes)


def test_resize_presets(run: RunFn, work: Path) -> None:
    src = make_image(work / "wide.jpg", (4000, 2000), fmt="JPEG")
    out = run("image.resize_1080", src).outputs[0]
    with Image.open(out) as img:
        assert img.size == (1080, 540)
    half = run("image.resize_half", src).outputs[0]
    with Image.open(half) as img:
        assert img.size == (2000, 1000)
    custom = run("image.resize_custom", src, options={"width": "500"}).outputs[0]
    with Image.open(custom) as img:
        assert img.size == (500, 250)


def test_resize_already_small(run: RunFn, work: Path) -> None:
    src = make_image(work / "small.png", (300, 200), fmt="PNG")
    result = run("image.resize_1080", src)
    assert result.state is JobState.FAILED and "already" in result.message


def _with_gps(path: Path) -> Path:
    img = Image.new("RGB", (64, 64), "green")
    exif = img.getexif()
    exif[0x010F] = "PhoneMaker"
    gps = exif.get_ifd(0x8825)
    gps[2] = (13.0, 5.0, 0.0)
    img.save(path, "JPEG", exif=exif.tobytes(), quality=90)
    return path


def test_strip_all_metadata(run: RunFn, work: Path) -> None:
    out = run("image.strip_metadata", _with_gps(work / "gps.jpg")).outputs[0]
    with Image.open(out) as img:
        assert not img.getexif()


def test_strip_gps_only(run: RunFn, work: Path) -> None:
    out = run("image.strip_gps", _with_gps(work / "gps.jpg")).outputs[0]
    with Image.open(out) as img:
        exif = img.getexif()
        assert exif.get(0x010F) == "PhoneMaker"
        assert 0x8825 not in exif


def test_combine_images_into_pdf(run: RunFn, work: Path) -> None:
    a = make_image(work / "a.jpg", (300, 400), fmt="JPEG")
    b = make_image(work / "b.png", (400, 300), "RGBA", fmt="PNG")
    out = run("image.combine_pdf", a, b).outputs[0]
    assert out.name == "a combined.pdf"
    with pikepdf.open(out) as pdf:
        assert len(pdf.pages) == 2


def test_batch_skips_bad_file(run: RunFn, work: Path) -> None:
    good = make_image(work / "good.png", fmt="PNG")
    bad = work / "bad.png"
    bad.write_bytes(b"\x89PNG\r\n\x1a\nbroken")
    result = run("image.to_jpg", good, bad)
    assert result.ok
    assert [p.name for p in result.outputs] == ["good.jpg"]
    assert any("1 of 2" in n for n in result.notes)


# ------------------------------------------------------------------ PDF


def test_pdf_to_images_folder(run: RunFn, work: Path) -> None:
    src = make_pdf(work / "doc.pdf", 3)
    result = run("pdf.to_png", src, options={"dpi": "72"})
    folder = result.outputs[0]
    assert folder.is_dir() and folder.name == "doc images"
    assert sorted(p.name for p in folder.iterdir()) == ["doc p1.png", "doc p2.png", "doc p3.png"]


def test_single_page_pdf_to_jpg(run: RunFn, work: Path) -> None:
    out = run("pdf.to_jpg", make_pdf(work / "one.pdf", 1)).outputs[0]
    assert out.name == "one p1.jpg"


def test_pdf_to_text(run: RunFn, work: Path) -> None:
    out = run("pdf.to_txt", make_pdf(work / "t.pdf", 2, text="Hello Spinfix")).outputs[0]
    text = out.read_text(encoding="utf-8")
    assert "Hello Spinfix 1" in text and "Hello Spinfix 2" in text


def test_merge_split_extract_rotate(run: RunFn, work: Path) -> None:
    a = make_pdf(work / "a.pdf", 2)
    b = make_pdf(work / "b.pdf", 3)
    merged = run("pdf.merge", a, b).outputs[0]
    with pikepdf.open(merged) as pdf:
        assert len(pdf.pages) == 5
    folder = run("pdf.split", merged).outputs[0]
    assert len(list(folder.iterdir())) == 5
    picked = run("pdf.extract", merged, options={"pages": "1-2, 5"}).outputs[0]
    with pikepdf.open(picked) as pdf:
        assert len(pdf.pages) == 3
    rotated = run("pdf.rotate_90", a).outputs[0]
    with pikepdf.open(rotated) as pdf:
        assert int(pdf.pages[0].obj.get("/Rotate", 0)) == 90


def test_extract_bad_ranges(run: RunFn, work: Path) -> None:
    src = make_pdf(work / "a.pdf", 2)
    for bad in ("0", "3", "2-1", "abc"):
        result = run("pdf.extract", src, options={"pages": bad})
        assert result.state is JobState.FAILED


def _image_pdf(path: Path, pages: int = 2) -> Path:
    imgs = [Image.effect_noise((1600, 2200), 60).convert("RGB") for _ in range(pages)]
    imgs[0].save(path, "PDF", save_all=True, append_images=imgs[1:], resolution=300.0)
    return path


def test_pdf_compress(run: RunFn, work: Path) -> None:
    src = _image_pdf(work / "scan.pdf")
    result = run("pdf.compress", src)
    assert result.ok, result.message
    assert result.output_bytes < src.stat().st_size
    doc = pdfium.PdfDocument(result.outputs[0])
    assert len(doc) == 2
    doc.close()


def test_pdf_compress_to_size(run: RunFn, work: Path) -> None:
    src = _image_pdf(work / "scan.pdf", 1)
    target = src.stat().st_size // 4
    result = run("pdf.under_custom", src, options={"target_size": str(target)})
    assert result.ok, result.message
    assert result.outputs[0].stat().st_size <= target or result.notes


# ------------------------------------------------------------------ archive & share


def test_zip_and_unzip_roundtrip(run: RunFn, work: Path) -> None:
    folder = work / "holiday"
    (folder / "day1").mkdir(parents=True)
    (folder / "day1" / "a.txt").write_text("one")
    (folder / "b.txt").write_text("two")
    archive = run("archive.zip", folder).outputs[0]
    assert archive.name == "holiday.zip"
    with zipfile.ZipFile(archive) as zf:
        assert sorted(zf.namelist()) == ["holiday/b.txt", "holiday/day1/a.txt"]
    out = run("archive.unzip", archive).outputs[0]
    assert (out / "holiday" / "day1" / "a.txt").read_text() == "one"


def test_copy_path_sets_clipboard_text(run: RunFn, work: Path) -> None:
    p = make_image(work / "x.png", fmt="PNG")
    result = run("share.copy_path", p)
    assert result.clipboard_text == str(p.resolve())
    assert result.outputs == []


def test_copy_file_sets_clipboard_files(run: RunFn, work: Path) -> None:
    p = make_image(work / "x.png", fmt="PNG")
    assert run("share.copy_file", p).clipboard_files == [p.resolve()]


# ------------------------------------------------------------------ media


def test_ffmpeg_missing_message(monkeypatch: pytest.MonkeyPatch, run: RunFn, work: Path) -> None:
    monkeypatch.setattr(media, "find_ffmpeg", lambda refresh=False: None)
    clip = work / "clip.mp4"
    clip.write_bytes(b"\x00\x00\x00\x20ftypisom" + b"\x00" * 64)
    result = run("media.to_mp3", clip)
    assert result.state is JobState.FAILED
    assert "FFmpeg" in result.message


def test_ffmpeg_never_found_in_current_dir(monkeypatch: pytest.MonkeyPatch, work: Path) -> None:
    (work / "ffmpeg.exe").write_bytes(b"MZ fake")
    monkeypatch.chdir(work)
    found = media.find_ffmpeg(refresh=True)
    assert found is None or found.parent != work


def test_file_url_protects_dash_names(work: Path) -> None:
    assert media.file_url(work / "-rf.mp4").startswith("file:")


@pytest.mark.skipif(media.find_ffmpeg() is None, reason="FFmpeg not installed")
def test_extract_audio_and_compress(run: RunFn, work: Path) -> None:
    import subprocess

    exe = media.find_ffmpeg()
    assert exe is not None
    clip = work / "-tricky clip.mp4"
    subprocess.run(
        [
            str(exe),
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc=size=640x360:rate=25",
            "-f",
            "lavfi",
            "-i",
            "sine",
            "-t",
            "4",
            "-pix_fmt",
            "yuv420p",
            "-b:v",
            "8M",
            media.file_url(clip),
        ],
        check=True,
        timeout=120,
    )
    mp3 = run("media.to_mp3", clip).outputs[0]
    assert mp3.suffix == ".mp3" and mp3.stat().st_size > 1000


# ------------------------------------------------------------------ OCR


@pytest.mark.skipif(not ocr.ocr_available(), reason="Windows OCR not available")
def test_ocr_reads_text(run: RunFn, work: Path) -> None:
    from PIL import ImageDraw, ImageFont

    img = Image.new("RGB", (900, 200), "white")
    try:
        font = ImageFont.truetype("arial.ttf", 64)
    except OSError:
        pytest.skip("Arial not available")
    ImageDraw.Draw(img).text((30, 50), "Spinfix works", fill="black", font=font)
    path = work / "text.png"
    img.save(path)
    result = run("ocr.copy_text", path)
    assert result.ok, result.message
    assert result.clipboard_text is not None
    assert "spinfix" in result.clipboard_text.lower()
