# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Security tests with hostile inputs: zip-slip, zip bombs, fake files, pixel bombs,
nasty file names, broken files."""

from __future__ import annotations

import struct
import zipfile
import zlib
from pathlib import Path

import pytest

from spinfix.actions.archive import safe_member_path
from spinfix.core import filetype
from spinfix.core.errors import UserError
from spinfix.core.jobs import JobState
from spinfix.core.limits import Limits
from tests.conftest import RunFn, make_image, make_zip, png_bytes

# ------------------------------------------------------------------ zip-slip


@pytest.mark.parametrize(
    "name",
    [
        "../evil.exe",
        "..\\..\\evil.exe",
        "a/../../evil.exe",
        "/abs/evil.exe",
        "C:/evil.exe",
        "C:evil.exe",
        "\\\\server\\share\\x",
        "ok/CON",
        "ok/nul.txt",
        "x/file.txt:stream",
        "trailing./x",
        "a\x00b",
    ],
)
def test_unsafe_member_names_rejected(name: str) -> None:
    assert safe_member_path(name) is None


def test_safe_member_names_kept() -> None:
    assert str(safe_member_path("folder/sub/photo.jpg")) == "folder/sub/photo.jpg"
    assert str(safe_member_path("./a.txt")) == "a.txt"


def test_zip_slip_does_not_escape(run: RunFn, work: Path) -> None:
    archive = make_zip(
        work / "slip.zip",
        {
            "../../escaped.txt": b"bad",
            "..\\escaped2.txt": b"bad",
            "good/file.txt": b"good",
        },
        symlink="link-to-system",
    )
    result = run("archive.unzip", archive)
    assert result.ok
    folder = result.outputs[0]
    assert (folder / "good" / "file.txt").read_bytes() == b"good"
    assert not (work / "escaped.txt").exists() and not (work.parent / "escaped.txt").exists()
    assert not (work / "escaped2.txt").exists()
    assert not (folder / "link-to-system").exists()
    assert any("Skipped 3" in n for n in result.notes)


# ------------------------------------------------------------------ zip bombs


def test_zip_bomb_by_ratio(run: RunFn, work: Path) -> None:
    archive = make_zip(work / "bomb.zip", {"zeros.bin": b"\0" * (64 * 1024 * 1024)})
    assert archive.stat().st_size < 1024 * 1024
    result = run("archive.unzip", archive)
    assert result.state is JobState.FAILED
    assert "zip bomb" in result.message
    assert [p.name for p in work.iterdir()] == ["bomb.zip"]  # partial folder removed


def test_zip_with_lying_header_is_stopped(work: Path) -> None:
    """Header says 10 bytes, data inflates to 5 MB: the byte counter must stop it."""
    from spinfix.actions.archive import extract_zip
    from spinfix.core.registry import JobContext

    archive = make_zip(work / "liar.zip", {"a.bin": b"\0" * (5 * 1024 * 1024)})
    data = bytearray(archive.read_bytes())
    # Patch the uncompressed size in the local header and central directory to 10.
    for sig in (b"PK\x03\x04", b"PK\x01\x02"):
        pos = data.find(sig)
        offset = 22 if sig == b"PK\x03\x04" else 24
        data[pos + offset : pos + offset + 4] = struct.pack("<I", 10)
    archive.write_bytes(bytes(data))
    out = work / "out"
    out.mkdir()
    with pytest.raises((UserError, zipfile.BadZipFile)):
        extract_zip(archive, out, JobContext(temp_dir=work))
    assert sum(f.stat().st_size for f in out.rglob("*") if f.is_file()) < 3 * 1024 * 1024


def test_too_many_entries(work: Path) -> None:
    from spinfix.actions.archive import check_zip

    archive = make_zip(work / "many.zip", {f"f{i}.txt": b"x" for i in range(50)})
    with zipfile.ZipFile(archive) as zf, pytest.raises(UserError, match="too many files"):
        check_zip(zf, archive.stat().st_size, Limits(max_archive_entries=10))


def test_encrypted_zip_message(run: RunFn, work: Path) -> None:
    archive = make_zip(work / "locked.zip", {"a.txt": b"x"})
    data = bytearray(archive.read_bytes())
    for sig, off in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        pos = data.find(sig)
        data[pos + off] |= 0x1
    archive.write_bytes(bytes(data))
    result = run("archive.unzip", archive)
    assert result.state is JobState.FAILED
    assert "password" in result.message


def test_zip_never_follows_junction_or_symlink(run: RunFn, work: Path, tmp_path: Path) -> None:
    secret = tmp_path / "outside"
    secret.mkdir()
    (secret / "secret.txt").write_text("private")
    folder = work / "folder"
    folder.mkdir()
    (folder / "a.txt").write_text("a")
    try:
        (folder / "link").symlink_to(secret, target_is_directory=True)
    except OSError:
        pytest.skip("creating symlinks needs Developer Mode on Windows")
    result = run("archive.zip", folder)
    with zipfile.ZipFile(result.outputs[0]) as zf:
        assert zf.namelist() == ["folder/a.txt"]


# ------------------------------------------------------------------ images


def _png_with_size(path: Path, width: int, height: int) -> Path:
    """A tiny PNG whose header claims a huge size (pixel bomb)."""

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\0" * 64)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    )
    return path


def test_huge_pixel_png_refused(run: RunFn, work: Path) -> None:
    bomb = _png_with_size(work / "bomb.png", 50_000, 50_000)
    result = run("image.to_jpg", bomb)
    assert result.state is JobState.FAILED
    assert "too big" in result.message
    assert [p.name for p in work.iterdir()] == ["bomb.png"]


def test_truncated_image(run: RunFn, work: Path) -> None:
    good = make_image(work / "photo.jpg", (800, 600), fmt="JPEG", noise=True)
    data = good.read_bytes()
    good.write_bytes(data[: len(data) // 3])
    result = run("image.to_png", good)
    assert result.state is JobState.FAILED
    assert "damaged" in result.message


def test_garbage_after_magic(run: RunFn, work: Path) -> None:
    path = work / "weird.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"garbage" * 100)
    result = run("image.to_jpg", path)
    assert result.state is JobState.FAILED


# ------------------------------------------------------------------ PDFs


def test_broken_pdf(run: RunFn, work: Path) -> None:
    path = work / "broken.pdf"
    path.write_bytes(b"%PDF-1.7\n" + b"\x00garbage" * 50)
    result = run("pdf.to_png", path)
    assert result.state is JobState.FAILED
    assert "damaged" in result.message


def test_encrypted_pdf(run: RunFn, work: Path) -> None:
    import pikepdf

    pdf = pikepdf.new()
    pdf.add_blank_page()
    path = work / "locked.pdf"
    pdf.save(path, encryption=pikepdf.Encryption(owner="o", user="secret", R=6))
    for action in ("pdf.to_png", "pdf.rotate_90", "pdf.compress"):
        result = run(action, path)
        assert result.state is JobState.FAILED
        assert "password-protected" in result.message


def test_pdf_page_cap(work: Path) -> None:
    from spinfix.actions.pdf import open_pike
    from tests.conftest import make_pdf

    path = make_pdf(work / "big.pdf", 12)
    with (
        pytest.raises(UserError, match="more than 10 pages"),
        open_pike(path, Limits(max_pdf_pages=10)),
    ):
        pass


# ------------------------------------------------------------------ names


@pytest.mark.parametrize(
    "name",
    [
        "-rf.png",
        "a&b; del x.png",
        "தமிழ்.png",
        "CON.png",
        "space .png",
        "%PATH%.png",
        "quote'name.png",
        "$(calc).png",
    ],
)
def test_odd_file_names_work(run: RunFn, work: Path, name: str) -> None:
    path = work / name
    path.write_bytes(png_bytes())
    result = run("image.to_jpg", path)
    assert result.ok, result.message
    out = result.outputs[0]
    assert out.parent == work and out.suffix == ".jpg"
    assert out.name.upper() not in {"CON.JPG"}


def test_original_never_modified(run: RunFn, work: Path) -> None:
    path = make_image(work / "photo.png", (300, 200), fmt="PNG", noise=True)
    before = path.read_bytes()
    for action in ("image.to_png", "image.compress", "image.strip_metadata", "image.resize_half"):
        if action == "image.to_png":
            continue
        run(action, path)
    assert path.read_bytes() == before


def test_mismatch_never_reaches_action(work: Path) -> None:
    exe = work / "holiday.png"
    exe.write_bytes(b"MZ" + b"\0" * 100)
    with pytest.raises(UserError):
        filetype.check(exe)
