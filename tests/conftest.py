# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""Shared fixtures. Tests never touch the real %APPDATA% or %LOCALAPPDATA%."""

from __future__ import annotations

import io
import os
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")  # never pop up windows in tests

import pikepdf
import pytest
from PIL import Image

from spinfix.actions import build_registry
from spinfix.core import filetype
from spinfix.core.jobs import Job, JobResult
from spinfix.core.registry import Options, Registry
from spinfix.core.settings import store


@pytest.fixture(autouse=True)
def _private_appdata(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    root = tmp_path_factory.mktemp("appdata")
    monkeypatch.setenv("LOCALAPPDATA", str(root / "local"))
    monkeypatch.setenv("APPDATA", str(root / "roaming"))
    store.reset_cache()
    yield
    store.reset_cache()


@pytest.fixture(scope="session")
def registry() -> Registry:
    return build_registry()


@pytest.fixture
def work(tmp_path: Path) -> Path:
    d = tmp_path / "work folder"
    d.mkdir()
    return d


RunFn = Callable[..., JobResult]


@pytest.fixture
def run(registry: Registry) -> RunFn:
    def _run(action_id: str, *paths: Path, options: Options | None = None) -> JobResult:
        infos = [filetype.check(p) for p in paths]
        action = registry.get(action_id)
        assert action.accepts(infos), f"{action_id} should accept {[i.kind for i in infos]}"
        return Job(action, infos, options or {}).run()

    return _run


def make_image(
    path: Path,
    size: tuple[int, int] = (640, 480),
    mode: str = "RGB",
    fmt: str | None = None,
    noise: bool = False,
    **save: object,
) -> Path:
    if noise:
        img = Image.effect_noise(size, 80).convert(mode)
    else:
        img = Image.new(mode, size, (200, 40, 40, 255)[: len(mode)] if mode != "L" else 128)
    img.save(path, fmt, **save)
    return path


def make_pdf(path: Path, pages: int = 3, text: str | None = None) -> Path:
    if text is None:
        pdf = pikepdf.new()
        for _ in range(pages):
            pdf.add_blank_page(page_size=(595, 842))
        pdf.save(path)
        return path
    # A tiny PDF with real text on each page.
    pdf = pikepdf.new()
    font = pdf.make_indirect(
        pikepdf.Dictionary(
            Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1, BaseFont=pikepdf.Name.Helvetica
        )
    )
    for i in range(pages):
        content = f"BT /F1 24 Tf 72 720 Td ({text} {i + 1}) Tj ET".encode()
        page = pikepdf.Dictionary(
            Type=pikepdf.Name.Page,
            MediaBox=[0, 0, 595, 842],
            Resources=pikepdf.Dictionary(Font=pikepdf.Dictionary(F1=font)),
            Contents=pdf.make_stream(content),
        )
        pdf.pages.append(pikepdf.Page(page))
    pdf.save(path)
    return path


def make_zip(
    path: Path,
    entries: dict[str, bytes],
    *,
    compression: int = zipfile.ZIP_DEFLATED,
    symlink: str | None = None,
) -> Path:
    with zipfile.ZipFile(path, "w", compression) as zf:
        for name, data in entries.items():
            zf.writestr(zipfile.ZipInfo(name), data, compress_type=compression)
        if symlink:
            info = zipfile.ZipInfo(symlink)
            info.external_attr = 0o120777 << 16
            zf.writestr(info, b"C:/Windows/System32")
    return path


def png_bytes(size: tuple[int, int] = (10, 10)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size).save(buf, "PNG")
    return buf.getvalue()
