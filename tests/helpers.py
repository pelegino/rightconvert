"""Shared test helpers: running the CLI, generating fixtures and identifying file types."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from rightconvert.engines import tool, tool_env  # noqa: E402

CLI = os.path.join(ROOT, "bin", "rightconvert")
WINDOWS = sys.platform == "win32"


def cli(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, CLI, *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8")


def convert(target: str, *files: str, cwd: str | None = None) -> str:
    """Last output path printed by `rightconvert --to target`, or "" on failure."""
    result = cli("--to", target, "--", *files, cwd=cwd)
    lines = result.stdout.strip().splitlines()
    return lines[-1] if result.returncode == 0 and lines else ""


def targets(path: str) -> list[str]:
    return cli("--list", path).stdout.split()


def run_tool(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    exe = tool(args[0])
    if not exe:
        raise unittest.SkipTest(args[0] + " is not installed")
    return subprocess.run([exe, *args[1:]], cwd=cwd, capture_output=True, text=True, env=tool_env(),
                          encoding="utf-8", errors="replace")


class WorkDir(unittest.TestCase):
    """A fresh folder per test class, kept on failure for inspection."""

    work = ""

    @classmethod
    def setUpClass(cls):
        cls.work = os.path.realpath(tempfile.mkdtemp(prefix="rightconvert-test-"))
        cls._failed = False

    @classmethod
    def tearDownClass(cls):
        if cls._failed:
            print(f"\nOutputs kept in {cls.work}", file=sys.stderr)
        else:
            shutil.rmtree(cls.work, ignore_errors=True)

    def run(self, result=None):
        before = len(result.failures) + len(result.errors) if result else 0
        result = super().run(result)
        if result and len(result.failures) + len(result.errors) > before:
            type(self)._failed = True
        return result

    def path(self, name: str) -> str:
        return os.path.join(self.work, name)


# ---------------------------------------------------------------- fixtures


def write(path: str, text: str) -> str:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def make_pdf(path: str, text: str) -> str:
    """A one-page US Letter PDF with real text, so pdftotext has something to extract."""
    stream = f"BT /F1 24 Tf 72 700 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> "
        b"/Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    with open(path, "wb") as f:
        f.write(out)
    return path


RTF = r"{\rtf1\ansi\deff0{\fonttbl{\f0 Helvetica;}}\f0\fs24 Plain text line one.\par Line two.\par}"
HTML = "<html><body><h1>Page</h1><p>Hello <b>world</b>.</p></body></html>\n"


def make_docx(path: str, html_path: str) -> bool:
    if tool("pandoc"):
        return run_tool("pandoc", html_path, "-o", path).returncode == 0
    if tool("textutil"):
        return run_tool("textutil", "-convert", "docx", "-output", path, html_path).returncode == 0
    return False


# ---------------------------------------------------------------- file type identification


def _ftyp_brand(head: bytes) -> bytes:
    return head[8:12] if head[4:8] == b"ftyp" else b""


def _zip_kind(path: str) -> str:
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if "mimetype" in names:
                mime = z.read("mimetype").decode()
                return {"application/vnd.oasis.opendocument.text": "odt",
                        "application/vnd.oasis.opendocument.spreadsheet": "ods",
                        "application/vnd.oasis.opendocument.presentation": "odp"}.get(mime, "zip")
            for prefix, kind in (("word/", "docx"), ("xl/", "xlsx"), ("ppt/", "pptx")):
                if any(n.startswith(prefix) for n in names):
                    return kind
    except zipfile.BadZipFile:
        pass
    return "zip"


def is_type(path: str, fmt: str) -> bool:
    """Whether a file's contents (not its name) are of format `fmt`."""
    with open(path, "rb") as f:
        head = f.read(4096)
    if not head:
        return False
    brand = _ftyp_brand(head)
    checks = {
        "jpg": lambda: head[:3] == b"\xff\xd8\xff",
        "png": lambda: head[:8] == b"\x89PNG\r\n\x1a\n",
        "webp": lambda: head[:4] == b"RIFF" and head[8:12] == b"WEBP",
        "heic": lambda: brand in (b"heic", b"heix", b"mif1", b"heim", b"heis"),
        "avif": lambda: brand in (b"avif", b"avis"),
        "tiff": lambda: head[:4] in (b"II*\x00", b"MM\x00*"),
        "gif": lambda: head[:4] == b"GIF8",
        "bmp": lambda: head[:2] == b"BM",
        "ico": lambda: head[:4] == b"\x00\x00\x01\x00",
        "pdf": lambda: head[:5] == b"%PDF-",
        "mp4": lambda: bool(brand) and brand != b"qt  ",
        "m4a": lambda: bool(brand),
        "mov": lambda: brand == b"qt  ",
        "mkv": lambda: head[:4] == b"\x1aE\xdf\xa3" and b"matroska" in head[:64],
        "webm": lambda: head[:4] == b"\x1aE\xdf\xa3" and b"webm" in head[:64],
        "mp3": lambda: head[:3] == b"ID3" or (head[0] == 0xFF and head[1] & 0xE0 == 0xE0),
        "wav": lambda: head[:4] == b"RIFF" and head[8:12] == b"WAVE",
        "flac": lambda: head[:4] == b"fLaC",
        "ogg": lambda: head[:4] == b"OggS",
        "opus": lambda: head[:4] == b"OggS" and b"OpusHead" in head,
        "aiff": lambda: head[:4] == b"FORM" and head[8:12] in (b"AIFF", b"AIFC"),
        "doc": lambda: head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",
        "rtf": lambda: head[:5] == b"{\\rtf",
        "html": lambda: b"<html" in head.lower() or b"<!doctype html" in head.lower(),
    }
    checks["xls"] = checks["ppt"] = checks["doc"]
    if fmt in checks:
        return checks[fmt]()
    if fmt in ("docx", "xlsx", "pptx", "odt", "ods", "odp"):
        return head[:2] == b"PK" and _zip_kind(path) == fmt
    if fmt in ("txt", "md", "csv"):
        try:
            head.decode("utf-8")
        except UnicodeDecodeError:
            return False
        return b"\x00" not in head and bool(head.strip())
    raise ValueError("unknown format " + fmt)


def output_ok(target: str, out: str) -> bool:
    """A non-empty output of the right type (for PDF pages: a folder of page images)."""
    fmt = target[:-6] if target.endswith("-small") else target
    if not out:
        return False
    if os.path.isdir(out):
        pages = sorted(n for n in os.listdir(out) if n.startswith("page") and n.endswith("." + fmt))
        return bool(pages) and is_type(os.path.join(out, pages[0]), fmt)
    return os.path.isfile(out) and os.path.getsize(out) > 0 and is_type(out, fmt)
