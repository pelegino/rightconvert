"""What can be converted into what. Engine availability is decided in engines.py."""

from __future__ import annotations

import os

CATEGORY: dict[str, str] = {}
for _ext in "jpg png heic webp gif tiff bmp avif svg".split():
    CATEGORY[_ext] = "image"
for _ext in "mp4 mov mkv avi webm m4v".split():
    CATEGORY[_ext] = "video"
for _ext in "mp3 wav m4a aac flac ogg opus aiff".split():
    CATEGORY[_ext] = "audio"
CATEGORY["pdf"] = "pdf"
for _ext in "docx doc odt rtf txt md html".split():
    CATEGORY[_ext] = "doc"
for _ext in "xlsx xls ods csv".split():
    CATEGORY[_ext] = "sheet"
for _ext in "pptx ppt odp".split():
    CATEGORY[_ext] = "slides"

TARGETS: dict[str, list[str]] = {
    "image": "jpg png webp heic avif tiff gif bmp ico pdf".split(),
    "video": "mp4 mov mkv webm gif mp3 m4a wav".split(),
    "audio": "mp3 wav m4a flac ogg opus aiff".split(),
    "pdf": "png jpg txt docx".split(),
    "doc": "pdf docx doc odt rtf txt md html".split(),
    "sheet": "xlsx xls ods csv pdf".split(),
    "slides": "pptx ppt odp pdf".split(),
}

EXT_ALIASES = {"jpeg": "jpg", "tif": "tiff", "heif": "heic", "htm": "html", "markdown": "md", "aif": "aiff"}

# Image targets that also come as a FORMAT-small lossy variant next to the lossless one.
SMALLER_TARGETS = ("webp", "heic", "avif")
SMALL = "-small"


def normalize_ext(ext: str) -> str:
    ext = ext.lower().lstrip(".")
    return EXT_ALIASES.get(ext, ext)


def ext_of(path: str) -> str:
    return normalize_ext(os.path.splitext(os.path.basename(path))[1])


def category_of(path: str) -> str:
    return CATEGORY.get(ext_of(path), "")


def base_format(target: str) -> str:
    return target[: -len(SMALL)] if target.endswith(SMALL) else target


def is_small(target: str) -> bool:
    return target.endswith(SMALL)


def all_extensions() -> list[str]:
    """Every extension the tool recognizes, canonical ones first."""
    return sorted(CATEGORY) + list(EXT_ALIASES)


def label_for(category: str, target: str) -> str:
    """Menu label. Keep in sync with label(category:format:) in app/FinderSync/FinderSync.swift."""
    name = base_format(target).upper()
    if is_small(target):
        return name + " (smaller file)"
    if category == "video" and target in ("mp3", "m4a", "wav"):
        return name + " (audio only)"
    if category == "video" and target == "gif":
        return name + " (animated)"
    if category == "pdf" and target in ("png", "jpg"):
        return name + " (one image per page)"
    return name
