"""PDF, document, spreadsheet and presentation conversion."""

from __future__ import annotations

import glob
import os
import shutil
import tempfile
from pathlib import Path

from .log import run

SOFFICE_FILTERS = {
    "txt": "txt:Text (encoded):UTF8",
    "csv": "csv:Text - txt - csv (StarCalc):44,34,76,1",
    "docx": "docx:MS Word 2007 XML",
}


def soffice_convert(src: str, t: str, out: str, infilter: str | None = None) -> bool:
    tmp = tempfile.mkdtemp(prefix="rightconvert")
    try:
        # A private profile, so conversions work even while LibreOffice is open.
        args = ["soffice", "--headless", "--norestore", "-env:UserInstallation=" + Path(tmp, "profile").as_uri()]
        if infilter:
            args.append("--infilter=" + infilter)
        args += ["--convert-to", SOFFICE_FILTERS.get(t, t), "--outdir", os.path.join(tmp, "out"), src]
        run(args)
        produced = glob.glob(os.path.join(glob.escape(tmp), "out", "*." + t))
        if not produced:
            return False
        shutil.move(produced[0], out)
        return True
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def pandoc_convert(src: str, s: str, t: str, out: str) -> bool:
    source = "markdown" if s in ("md", "txt") else s
    dest = {"md": "gfm", "txt": "plain"}.get(t, t)
    stem = os.path.splitext(os.path.basename(out))[0]
    extra = ["--standalone"]
    if t == "html":
        extra += ["--metadata", "pagetitle=" + os.path.splitext(os.path.basename(src))[0]]
        if s in ("docx", "odt"):
            extra.append("--embed-resources")
    if t == "md" and s in ("docx", "odt"):
        extra.append("--extract-media=" + stem + "_media")
    return run(["pandoc", "--from", source, "--to", dest] + extra + ["--output", out, src], cwd=os.path.dirname(src))


def pdf_to_images(src: str, t: str, out_dir: str) -> bool:
    kind = ["-png"] if t == "png" else ["-jpeg", "-jpegopt", "quality=95"]
    return run(["pdftoppm", "-r", "300"] + kind + [src, os.path.join(out_dir, "page")])


def convert_document(engine: str, src: str, s: str, t: str, out: str) -> bool:
    if engine == "pdftoppm":
        return pdf_to_images(src, t, out)
    if engine == "pdftotext":
        return run(["pdftotext", "-layout", src, out])
    if engine == "soffice-pdf":
        return soffice_convert(src, t, out, infilter="writer_pdf_import")
    if engine == "soffice":
        return soffice_convert(src, t, out)
    if engine == "textutil":
        return run(["textutil", "-convert", t, "-output", out, src])
    if engine == "pandoc":
        return pandoc_convert(src, s, t, out)
    if engine == "pandoc+soffice":
        tmp = tempfile.mkdtemp(prefix="rightconvert")
        try:
            docx = os.path.join(tmp, os.path.splitext(os.path.basename(src))[0] + ".docx")
            return pandoc_convert(src, s, "docx", docx) and soffice_convert(docx, t, out)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return False
