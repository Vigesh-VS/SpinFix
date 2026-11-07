# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Vigesh
"""File-type detection by magic bytes (never by extension alone).

`detect(path)` reads only the first bytes of a file. `check(path)` also compares the
result with the extension and refuses files that pretend to be something they are not.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from spinfix.core.errors import UserError

HEADER_BYTES = 64


class Category(StrEnum):
    IMAGE = "image"
    PDF = "pdf"
    VIDEO = "video"
    AUDIO = "audio"
    ARCHIVE = "archive"
    DOCUMENT = "document"
    TEXT = "text"
    FOLDER = "folder"
    UNKNOWN = "unknown"


class Kind(StrEnum):
    JPEG = "jpeg"
    PNG = "png"
    GIF = "gif"
    WEBP = "webp"
    BMP = "bmp"
    TIFF = "tiff"
    HEIC = "heic"
    AVIF = "avif"
    ICO = "ico"
    PDF = "pdf"
    ZIP = "zip"
    SEVEN_Z = "7z"
    RAR = "rar"
    GZIP = "gzip"
    MP4 = "mp4"
    MOV = "mov"
    MKV = "mkv"
    WEBM = "webm"
    AVI = "avi"
    MP3 = "mp3"
    M4A = "m4a"
    WAV = "wav"
    FLAC = "flac"
    OGG = "ogg"
    DOCX = "docx"
    XLSX = "xlsx"
    PPTX = "pptx"
    TEXT = "text"
    FOLDER = "folder"
    UNKNOWN = "unknown"


CATEGORY: dict[Kind, Category] = {
    **dict.fromkeys(
        (
            Kind.JPEG,
            Kind.PNG,
            Kind.GIF,
            Kind.WEBP,
            Kind.BMP,
            Kind.TIFF,
            Kind.HEIC,
            Kind.AVIF,
            Kind.ICO,
        ),
        Category.IMAGE,
    ),
    Kind.PDF: Category.PDF,
    **dict.fromkeys((Kind.ZIP, Kind.SEVEN_Z, Kind.RAR, Kind.GZIP), Category.ARCHIVE),
    **dict.fromkeys((Kind.MP4, Kind.MOV, Kind.MKV, Kind.WEBM, Kind.AVI), Category.VIDEO),
    **dict.fromkeys((Kind.MP3, Kind.M4A, Kind.WAV, Kind.FLAC, Kind.OGG), Category.AUDIO),
    **dict.fromkeys((Kind.DOCX, Kind.XLSX, Kind.PPTX), Category.DOCUMENT),
    Kind.TEXT: Category.TEXT,
    Kind.FOLDER: Category.FOLDER,
    Kind.UNKNOWN: Category.UNKNOWN,
}

# Extension -> kinds whose content is acceptable for that extension.
EXTENSIONS: dict[str, tuple[Kind, ...]] = {
    ".jpg": (Kind.JPEG,),
    ".jpeg": (Kind.JPEG,),
    ".jfif": (Kind.JPEG,),
    ".png": (Kind.PNG,),
    ".gif": (Kind.GIF,),
    ".webp": (Kind.WEBP,),
    ".bmp": (Kind.BMP,),
    ".dib": (Kind.BMP,),
    ".tif": (Kind.TIFF,),
    ".tiff": (Kind.TIFF,),
    ".heic": (Kind.HEIC,),
    ".heif": (Kind.HEIC,),
    ".avif": (Kind.AVIF,),
    ".ico": (Kind.ICO,),
    ".pdf": (Kind.PDF,),
    ".zip": (Kind.ZIP,),
    ".7z": (Kind.SEVEN_Z,),
    ".rar": (Kind.RAR,),
    ".gz": (Kind.GZIP,),
    ".mp4": (Kind.MP4, Kind.MOV, Kind.M4A),
    ".m4v": (Kind.MP4, Kind.MOV),
    ".mov": (Kind.MOV, Kind.MP4),
    ".3gp": (Kind.MP4,),
    ".mkv": (Kind.MKV, Kind.WEBM),
    ".webm": (Kind.WEBM, Kind.MKV),
    ".avi": (Kind.AVI,),
    ".mp3": (Kind.MP3,),
    ".m4a": (Kind.M4A, Kind.MP4),
    ".aac": (Kind.M4A,),
    ".wav": (Kind.WAV,),
    ".flac": (Kind.FLAC,),
    ".ogg": (Kind.OGG,),
    ".opus": (Kind.OGG,),
    ".docx": (Kind.DOCX, Kind.ZIP),
    ".xlsx": (Kind.XLSX, Kind.ZIP),
    ".pptx": (Kind.PPTX, Kind.ZIP),
    ".txt": (Kind.TEXT,),
    ".csv": (Kind.TEXT,),
    ".md": (Kind.TEXT,),
}

_FTYP_BRANDS: dict[bytes, Kind] = {
    b"heic": Kind.HEIC,
    b"heix": Kind.HEIC,
    b"hevc": Kind.HEIC,
    b"heim": Kind.HEIC,
    b"heis": Kind.HEIC,
    b"mif1": Kind.HEIC,
    b"msf1": Kind.HEIC,
    b"avif": Kind.AVIF,
    b"avis": Kind.AVIF,
    b"qt  ": Kind.MOV,
    b"M4A ": Kind.M4A,
    b"M4B ": Kind.M4A,
}


@dataclass(frozen=True, slots=True)
class FileInfo:
    path: Path
    kind: Kind
    size: int

    @property
    def category(self) -> Category:
        return CATEGORY[self.kind]

    @property
    def extension(self) -> str:
        return self.path.suffix.lower()


def _sniff(head: bytes) -> Kind:
    if head.startswith(b"\xff\xd8\xff"):
        return Kind.JPEG
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return Kind.PNG
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return Kind.GIF
    if head.startswith(b"RIFF") and len(head) >= 12:
        sub = head[8:12]
        if sub == b"WEBP":
            return Kind.WEBP
        if sub == b"WAVE":
            return Kind.WAV
        if sub == b"AVI ":
            return Kind.AVI
    if head.startswith(b"BM") and len(head) >= 14:
        return Kind.BMP
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return Kind.TIFF
    if head.startswith(b"\x00\x00\x01\x00") and len(head) >= 6 and head[4:6] != b"\x00\x00":
        return Kind.ICO
    if head.startswith(b"%PDF-"):
        return Kind.PDF
    if head[:4] in (b"PK\x03\x04", b"PK\x05\x06"):
        return Kind.ZIP
    if head.startswith(b"7z\xbc\xaf\x27\x1c"):
        return Kind.SEVEN_Z
    if head.startswith(b"Rar!\x1a\x07"):
        return Kind.RAR
    if head.startswith(b"\x1f\x8b"):
        return Kind.GZIP
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return _FTYP_BRANDS.get(head[8:12], Kind.MP4)
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return Kind.WEBM if b"webm" in head else Kind.MKV
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and head[1] & 0xE0 == 0xE0):
        return Kind.MP3
    if head.startswith(b"fLaC"):
        return Kind.FLAC
    if head.startswith(b"OggS"):
        return Kind.OGG
    return Kind.UNKNOWN


def _looks_like_text(head: bytes) -> bool:
    if not head or b"\x00" in head:
        return False
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        # A multi-byte character may be cut at the end of the sample.
        try:
            head[:-3].decode("utf-8")
        except UnicodeDecodeError:
            return False
    return True


def _office_kind(path: Path) -> Kind:
    """Refine a ZIP into docx/xlsx/pptx by extension; content stays a ZIP container."""
    return {".docx": Kind.DOCX, ".xlsx": Kind.XLSX, ".pptx": Kind.PPTX}.get(
        path.suffix.lower(), Kind.ZIP
    )


def detect(path: str | os.PathLike[str]) -> FileInfo:
    """Detect what a file really is from its first bytes."""
    p = Path(path)
    if p.is_dir():
        return FileInfo(p, Kind.FOLDER, 0)
    try:
        with p.open("rb") as fh:
            head = fh.read(HEADER_BYTES)
        size = p.stat().st_size
    except OSError as exc:
        raise UserError(f"Couldn't read {p.name}.") from exc
    kind = _sniff(head)
    if kind is Kind.ZIP:
        kind = _office_kind(p)
    elif kind is Kind.UNKNOWN and _looks_like_text(head):
        kind = Kind.TEXT
    return FileInfo(p, kind, size)


def extension_matches(info: FileInfo) -> bool:
    expected = EXTENSIONS.get(info.extension)
    if expected is None:
        return True  # unknown extension: trust the content
    return info.kind in expected


def check(path: str | os.PathLike[str]) -> FileInfo:
    """Detect and refuse files whose content doesn't match their extension."""
    info = detect(path)
    if not extension_matches(info):
        what = _friendly(info.extension)
        raise UserError(
            f"This file says {info.extension} but isn't {what}, so Spinfix left it alone."
        )
    return info


def _friendly(ext: str) -> str:
    kinds = EXTENSIONS.get(ext, ())
    if not kinds:
        return "what it claims"
    cat = CATEGORY[kinds[0]]
    return {
        Category.IMAGE: "an image",
        Category.PDF: "a PDF",
        Category.VIDEO: "a video",
        Category.AUDIO: "an audio file",
        Category.ARCHIVE: "an archive",
        Category.DOCUMENT: "a document",
        Category.TEXT: "a text file",
    }.get(cat, "what it claims")
