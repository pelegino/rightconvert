"""Finds the conversion tools on this machine and picks one for each conversion."""

from __future__ import annotations

import functools
import glob
import os
import shutil
import subprocess
import sys

from .formats import CATEGORY, SMALLER_TARGETS, TARGETS, base_format, ext_of, is_small

WINDOWS = sys.platform == "win32"
MACOS = sys.platform == "darwin"

# Hide the console window that each tool would otherwise flash when run from pythonw.
NO_WINDOW = subprocess.CREATE_NO_WINDOW if WINDOWS else 0

INSTALL_HINT = (
    {
        "magick": "winget install ImageMagick.ImageMagick",
        "ffmpeg": "winget install Gyan.FFmpeg",
        "pdftoppm": "winget install oschwartz10612.Poppler",
        "pandoc": "winget install JohnMacFarlane.Pandoc",
        "soffice": "winget install TheDocumentFoundation.LibreOffice",
    }
    if WINDOWS
    else {
        "magick": "brew install imagemagick",
        "ffmpeg": "brew install ffmpeg",
        "pdftoppm": "brew install poppler",
        "pandoc": "brew install pandoc",
        "soffice": "brew install --cask libreoffice",
    }
)


@functools.lru_cache(maxsize=None)
def _extra_dirs() -> list[str]:
    """Install locations that aren't always on PATH (Finder and Explorer launch with a minimal one)."""
    if MACOS:
        return ["/opt/homebrew/bin", "/usr/local/bin", "/Applications/LibreOffice.app/Contents/MacOS"]
    if WINDOWS:
        local = os.environ.get("LOCALAPPDATA", "")
        programs = [os.environ.get(v, "") for v in ("ProgramFiles", "ProgramFiles(x86)")]
        patterns = _registry_path() + [os.path.join(local, "Microsoft", "WinGet", "Links"), os.path.join(local, "Pandoc")]
        patterns += [os.path.join(local, "Microsoft", "WinGet", "Packages", "oschwartz10612.Poppler*", "poppler-*", "Library", "bin")]
        patterns += [os.path.join(local, "Microsoft", "WinGet", "Packages", "Gyan.FFmpeg*", "ffmpeg-*", "bin")]
        for root in filter(None, programs):
            patterns += [os.path.join(root, "ImageMagick-*"), os.path.join(root, "LibreOffice", "program"),
                         os.path.join(root, "Pandoc")]
        dirs: list[str] = []
        for pattern in patterns:
            dirs += sorted(glob.glob(pattern), reverse=True)
        return dirs
    return []


def _registry_path() -> list[str]:
    """The current user and system PATH. Explorer's own copy is stale until the next sign-in, so
    tools installed after login would otherwise be missed."""
    import winreg

    dirs = []
    for root, key in ((winreg.HKEY_CURRENT_USER, "Environment"),
                      (winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment")):
        try:
            with winreg.OpenKey(root, key) as k:
                value = winreg.QueryValueEx(k, "Path")[0]
        except OSError:
            continue
        dirs += [os.path.expandvars(d) for d in value.split(";") if d]
    return [glob.escape(d) for d in dirs]


@functools.lru_cache(maxsize=None)
def tool(name: str) -> str | None:
    """Absolute path of a command-line tool, or None if it isn't installed."""
    candidates = [name]
    # soffice.exe returns before conversion finishes; soffice.com waits.
    if WINDOWS and name == "soffice":
        candidates = ["soffice.com", "soffice"]
    path = os.pathsep.join([os.environ.get("PATH", "")] + _extra_dirs())
    for candidate in candidates:
        found = shutil.which(candidate, path=path)
        if found:
            return found
    return None


def has(name: str) -> bool:
    return tool(name) is not None


def tool_env() -> dict[str, str]:
    """Environment for child processes, with every discovered tool directory on PATH."""
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(_extra_dirs() + [env.get("PATH", "")])
    return env


def capture(args: list[str]) -> str:
    """Run a quick query command and return its stdout ("" on failure)."""
    exe = tool(args[0])
    if not exe:
        return ""
    try:
        result = subprocess.run([exe] + args[1:], capture_output=True, env=tool_env(),
                                creationflags=NO_WINDOW, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.decode("utf-8", "replace")


@functools.lru_cache(maxsize=None)
def magick_writable() -> frozenset[str]:
    """Formats ImageMagick can write here (Windows builds can't write HEIC, for example)."""
    formats = set()
    for line in capture(["magick", "-list", "format"]).splitlines():
        parts = line.split()
        if len(parts) >= 3 and len(parts[2]) == 3 and parts[2][1] == "w":
            formats.add(parts[0].rstrip("*").lower())
    return frozenset(formats)


@functools.lru_cache(maxsize=None)
def ffmpeg_encoders() -> frozenset[str]:
    names = set()
    for line in capture(["ffmpeg", "-hide_banner", "-encoders"]).splitlines():
        parts = line.split()
        if len(parts) >= 2 and len(parts[0]) == 6:
            names.add(parts[1])
    return frozenset(names)


PANDOC_IN = {"docx", "odt", "rtf", "md", "html", "txt"}
PANDOC_OUT = {"docx", "odt", "rtf", "md", "html", "txt"}
TEXTUTIL_FMT = {"txt", "html", "rtf", "doc", "docx", "odt"}
SOFFICE_IN = {"docx", "doc", "odt", "rtf", "txt", "html"}
SOFFICE_OUT = {"pdf", "docx", "doc", "odt", "rtf", "txt", "html"}


def _doc_engine(s: str, t: str) -> str | None:
    if s == "md":
        if t == "pdf":
            return "pandoc+soffice" if has("pandoc") and has("soffice") else None
        return "pandoc" if t in PANDOC_OUT and has("pandoc") else None
    if t == "md":
        return "pandoc" if s in PANDOC_IN and has("pandoc") else None
    if t == "pdf":
        return "soffice" if s in SOFFICE_IN and has("soffice") else None
    if s == "doc" or t == "doc":
        if has("textutil"):
            return "textutil"
        return "soffice" if has("soffice") else None
    if s != "txt" and has("pandoc") and s in PANDOC_IN and t in PANDOC_OUT:
        return "pandoc"
    if has("textutil") and s in TEXTUTIL_FMT and t in TEXTUTIL_FMT:
        return "textutil"
    if has("soffice") and s in SOFFICE_IN and t in SOFFICE_OUT:
        return "soffice"
    return None


def engine_for(s: str, target: str) -> str | None:
    """Tool that converts extension `s` to `target`, or None if this machine can't."""
    t = base_format(target)
    if s == t:
        return None
    category = CATEGORY.get(s)
    if category == "image":
        if not has("magick"):
            return None
        if t in ("heic", "avif"):
            # Lossless HEIF needs heif-enc; never offer "lossless" and silently encode lossy.
            if is_small(target):
                return "magick" if t in magick_writable() else None
            return "heif-enc" if has("heif-enc") else None
        return "magick"
    if category in ("video", "audio"):
        return "ffmpeg" if has("ffmpeg") else None
    if category == "pdf":
        if t in ("png", "jpg"):
            return "pdftoppm" if has("pdftoppm") else None
        if t == "txt":
            return "pdftotext" if has("pdftotext") else None
        if t == "docx":
            return "soffice-pdf" if has("soffice") else None
        return None
    if category == "doc":
        return _doc_engine(s, t)
    if category in ("sheet", "slides"):
        return "soffice" if has("soffice") else None
    return None


def targets_for(path: str) -> list[str]:
    """Formats `path` can be converted to with the tools installed here."""
    s = ext_of(path)
    category = CATEGORY.get(s)
    if not category:
        return []
    found = []
    for t in TARGETS[category]:
        if engine_for(s, t):
            found.append(t)
        if category == "image" and t in SMALLER_TARGETS and engine_for(s, t + "-small"):
            found.append(t + "-small")
    return found


def missing_engines_for(category: str) -> list[str]:
    """Tools whose absence limits what a category can produce."""
    needs = {
        "image": ["magick"],
        "video": ["ffmpeg"],
        "audio": ["ffmpeg"],
        "pdf": ["pdftoppm", "soffice"],
        "doc": ["pandoc", "soffice"],
        "sheet": ["soffice"],
        "slides": ["soffice"],
    }.get(category, [])
    return [name for name in needs if not has(name)]
