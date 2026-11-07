# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Core engine: file types, safe names, atomic output, jobs, settings, registry."""

from __future__ import annotations

import json
import threading
from collections.abc import Sequence
from pathlib import Path

import pytest

from spinfix.core import filetype, safe_io, settings
from spinfix.core.errors import UserError, short_path
from spinfix.core.filetype import Category, FileInfo, Kind
from spinfix.core.jobs import Job, JobState
from spinfix.core.limits import Limits
from spinfix.core.registry import Action, JobContext, Options, Registry, Wheel
from tests.conftest import make_image, make_pdf, make_zip

# ------------------------------------------------------------------ filetype


@pytest.mark.parametrize(
    ("name", "fmt", "kind"),
    [
        ("a.png", "PNG", Kind.PNG),
        ("a.jpg", "JPEG", Kind.JPEG),
        ("a.gif", "GIF", Kind.GIF),
        ("a.webp", "WEBP", Kind.WEBP),
        ("a.bmp", "BMP", Kind.BMP),
        ("a.tiff", "TIFF", Kind.TIFF),
        ("a.ico", "ICO", Kind.ICO),
    ],
)
def test_detect_images(work: Path, name: str, fmt: str, kind: Kind) -> None:
    path = make_image(work / name, (32, 32), fmt=fmt)
    info = filetype.check(path)
    assert info.kind is kind
    assert info.category is Category.IMAGE


@pytest.mark.parametrize(
    ("head", "kind"),
    [
        (b"%PDF-1.7\n", Kind.PDF),
        (b"7z\xbc\xaf\x27\x1c\x00\x04", Kind.SEVEN_Z),
        (b"\x00\x00\x00\x20ftypisom\x00\x00", Kind.MP4),
        (b"\x00\x00\x00\x14ftypqt  ", Kind.MOV),
        (b"\x00\x00\x00\x18ftypheic", Kind.HEIC),
        (b"\x00\x00\x00\x1cftypavif", Kind.AVIF),
        (b"\x1a\x45\xdf\xa3\x01\x00webm", Kind.WEBM),
        (b"ID3\x04\x00", Kind.MP3),
        (b"RIFF\x00\x00\x00\x00WAVEfmt ", Kind.WAV),
        (b"fLaC\x00", Kind.FLAC),
        (b"OggS\x00", Kind.OGG),
        (b"hello world\n", Kind.TEXT),
        (b"\x00\x01\x02\x03", Kind.UNKNOWN),
    ],
)
def test_detect_magic(work: Path, head: bytes, kind: Kind) -> None:
    path = work / "sample.bin"
    path.write_bytes(head + b"\x00" * 32 if kind is not Kind.TEXT else head)
    assert filetype.detect(path).kind is kind


def test_fake_extension_refused(work: Path) -> None:
    fake = work / "invoice.jpg"
    fake.write_bytes(b"MZ\x90\x00 this is an exe")
    with pytest.raises(UserError, match="isn't an image"):
        filetype.check(fake)


def test_pdf_named_png_refused(work: Path) -> None:
    path = make_pdf(work / "x.png", 1)
    with pytest.raises(UserError, match=r"says \.png"):
        filetype.check(path)


def test_docx_is_zip_container(work: Path) -> None:
    path = make_zip(work / "report.docx", {"[Content_Types].xml": b"<x/>"})
    assert filetype.check(path).kind is Kind.DOCX


def test_folder(work: Path) -> None:
    assert filetype.detect(work).category is Category.FOLDER


def test_empty_file_is_unknown(work: Path) -> None:
    (work / "empty.dat").write_bytes(b"")
    assert filetype.detect(work / "empty.dat").kind is Kind.UNKNOWN


# ------------------------------------------------------------------ names


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("photo.jpg", "photo.jpg"),
        ('a<b>c:"d|e?f*.png', "a_b_c__d_e_f_.png"),
        ("CON.txt", "_CON.txt"),
        ("nul", "_nul"),
        ("com1.tar.gz", "_com1.tar.gz"),
        ("LPT9.pdf", "_LPT9.pdf"),
        ("trailing. . ", "trailing"),
        ("..", "file"),
        ("-rf.mp4", "-rf.mp4"),
        ("tab\there.txt", "tab_here.txt"),
        ("a&b.jpg", "a&b.jpg"),
        ("தமிழ் படம்.jpg", "தமிழ் படம்.jpg"),
        ("dir/../x.png", "dir_.._x.png"),
    ],
)
def test_sanitize_name(raw: str, clean: str) -> None:
    assert safe_io.sanitize_name(raw) == clean


def test_unique_path_counts_up(work: Path) -> None:
    (work / "photo.jpg").write_bytes(b"1")
    (work / "photo (1).jpg").write_bytes(b"2")
    assert safe_io.unique_path(work, "photo.jpg").name == "photo (2).jpg"


def test_unique_path_respects_length(work: Path) -> None:
    long = "x" * 400 + ".png"
    path = safe_io.unique_path(work, long, Limits())
    assert len(str(path)) <= Limits().max_path_length


def test_unique_path_needs_absolute() -> None:
    with pytest.raises(UserError):
        safe_io.unique_path(Path("relative"), "a.txt")


# ------------------------------------------------------------------ atomic output


def test_atomic_commit_never_overwrites(work: Path) -> None:
    original = work / "report.txt"
    original.write_text("original")
    with safe_io.atomic_output(work, "report.txt") as out, out.open() as fh:
        fh.write(b"new")
    assert original.read_text() == "original"
    assert out.final_path == work / "report (1).txt"
    assert out.final_path.read_bytes() == b"new"
    assert not list(work.glob(".~*"))


def test_atomic_failure_leaves_nothing(work: Path) -> None:
    with pytest.raises(RuntimeError), safe_io.atomic_output(work, "x.bin") as out:
        with out.open() as fh:
            fh.write(b"partial")
        raise RuntimeError("boom")
    assert list(work.iterdir()) == []


def test_commit_race_picks_next_name(work: Path) -> None:
    out = safe_io.AtomicOutput(work, "race.txt")
    with out.open() as fh:
        fh.write(b"mine")
    (work / "race.txt").write_text("someone else's")  # appears before commit
    final = out.commit()
    assert final.name == "race (1).txt"
    assert (work / "race.txt").read_text() == "someone else's"


def test_remove_stale_parts(work: Path) -> None:
    (work / ".~old.abc.part").write_bytes(b"x")
    (work / "keep.part").write_bytes(b"x")
    assert safe_io.remove_stale_parts(work) == 1
    assert (work / "keep.part").exists()


def test_job_temp_dir_is_private_and_removed() -> None:
    with safe_io.job_temp_dir() as tmp:
        (tmp / "x").write_text("x")
        assert tmp.parent == safe_io.temp_root()
    assert not tmp.exists()


def test_human_size() -> None:
    assert safe_io.human_size(500) == "500 bytes"
    assert safe_io.human_size(200 * 1024) == "200 KB"
    assert safe_io.human_size(1.5 * 1024 * 1024) == "1.5 MB"


def test_short_path_hides_folders() -> None:
    assert short_path(r"C:\Users\vigesh\Secret\photo.jpg") == "…\\photo.jpg"


def test_free_space_check(work: Path) -> None:
    with pytest.raises(UserError, match="Not enough free space"):
        safe_io.check_free_space(work, 10**18)


# ------------------------------------------------------------------ jobs


class _Slow(Action):
    id = "test.slow"
    title = "Slow"
    categories = frozenset(Category)

    def run(self, inputs: Sequence[FileInfo], options: Options, ctx: JobContext) -> list[Path]:
        for i in range(200):
            ctx.progress(i / 200)
            threading.Event().wait(0.01)
        return []


class _Writes(Action):
    id = "test.writes"
    title = "Writes then fails"
    categories = frozenset(Category)

    def run(self, inputs: Sequence[FileInfo], options: Options, ctx: JobContext) -> list[Path]:
        tmp = ctx.temp_file("a.txt")
        tmp.write_text("x")
        ctx.save(tmp, inputs[0].path, "out.txt")
        raise UserError("Nope.")


class _Crash(Action):
    id = "test.crash"
    title = "Crash"
    categories = frozenset(Category)

    def run(self, inputs: Sequence[FileInfo], options: Options, ctx: JobContext) -> list[Path]:
        raise KeyError("secret internal detail")


def _info(work: Path) -> FileInfo:
    p = work / "in.txt"
    p.write_text("hello")
    return filetype.check(p)


def test_job_cancel(work: Path) -> None:
    job = Job(_Slow(), [_info(work)])
    job.start()
    job.cancel()
    result = job.wait(10)
    assert result is not None
    assert result.state is JobState.CANCELLED


def test_job_timeout(work: Path) -> None:
    job = Job(_Slow(), [_info(work)], limits=Limits(job_timeout_seconds=0.2))
    result = job.run()
    assert result.state is JobState.CANCELLED
    assert "too long" in result.message


def test_failed_job_removes_partial_outputs(work: Path) -> None:
    result = Job(_Writes(), [_info(work)]).run()
    assert result.state is JobState.FAILED
    assert result.message == "Nope."
    assert not (work / "out.txt").exists()


def test_internal_error_is_generic(work: Path) -> None:
    result = Job(_Crash(), [_info(work)]).run()
    assert result.state is JobState.FAILED
    assert "secret" not in result.message
    assert "log" in result.message


def test_registry_rejects_duplicates() -> None:
    reg = Registry()
    reg.register(_Slow())
    with pytest.raises(ValueError, match="duplicate"):
        reg.register(_Slow())
    with pytest.raises(UserError):
        reg.get("nope")


def test_registry_filters_by_kind(registry: Registry, work: Path) -> None:
    png = filetype.check(make_image(work / "a.png", fmt="PNG"))
    pdf = filetype.check(make_pdf(work / "a.pdf", 1))
    ids = {a.id for a in registry.for_files([png])}
    assert "image.to_jpg" in ids and "image.to_png" not in ids and "pdf.merge" not in ids
    assert {a.id for a in registry.for_files([png, pdf])} == {
        "share.copy_path",
        "share.copy_file",
        "archive.zip",
    }
    assert registry.wheels_for([pdf])[0] is Wheel.CONVERT


def test_every_action_has_metadata(registry: Registry) -> None:
    assert len(registry) > 30
    for action in registry.all():
        assert action.id and action.title and action.icon
        assert action.kinds or action.categories


# ------------------------------------------------------------------ settings


def test_settings_roundtrip_and_validation(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    s = settings.Settings(jpeg_quality=70, trigger_key="ctrl")
    settings.save(s, path)
    assert settings.load(path) == s
    path.write_text(
        json.dumps(
            {
                "jpeg_quality": 9000,
                "trigger_key": "win",
                "paused": "yes",
                "evil": "__import__('os')",
            }
        )
    )
    loaded = settings.load(path)
    assert loaded.jpeg_quality == 85 and loaded.trigger_key == "shift" and loaded.paused is False


def test_settings_garbage_file(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_bytes(b"\xff\xfe not json")
    assert settings.load(path) == settings.Settings()


def test_store_update_persists() -> None:
    settings.store.update(output_mode="subfolder")
    settings.store.reset_cache()
    assert settings.store.get().output_subfolder() == "Spinfix"
