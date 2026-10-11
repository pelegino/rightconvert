"""Command-line entry point. The right-click menus on both platforms call this."""

from __future__ import annotations

import os
import shutil
import sys

from . import __version__, ui
from .documents import convert_document
from .engines import INSTALL_HINT, WINDOWS, engine_for, missing_engines_for, targets_for
from .formats import CATEGORY, all_extensions, base_format, category_of, ext_of, label_for, normalize_ext
from .log import log, log_header, log_path, rotate
from .media import convert_av, convert_image

USAGE = """\
Usage:
  rightconvert FILE...              pick a target format from a dialog
  rightconvert --to FORMAT FILE...  convert without a dialog
  rightconvert --list FILE          print the formats FILE can be converted to
  rightconvert --matrix             print the conversion table for all known extensions
  rightconvert --gui ...            show notifications and dialogs even with --to
  rightconvert --version            print the version
""" + ("""\
  rightconvert --register           add the Convert menu to Explorer (run again after installing tools)
  rightconvert --unregister         remove the Convert menu from Explorer
""" if WINDOWS else "") + """
FORMAT is a file extension such as jpg, mp4 or pdf. webp-small, heic-small and avif-small
make smaller lossy images instead of lossless ones.
Folders are expanded one level deep. Output is written next to each source file."""


class UsageError(Exception):
    pass


def unique_path(stem: str, suffix: str) -> str:
    candidate, n = stem + suffix, 1
    while os.path.lexists(candidate):
        candidate = f"{stem}-{n}{suffix}"
        n += 1
    return candidate


def convert_one(path: str, target: str) -> str | None:
    """Convert one file; returns the output path, or None on failure (leaving no partial output)."""
    src = os.path.abspath(path)
    s = ext_of(src)
    engine = engine_for(s, target)
    if not engine:
        log(f"no engine for {s} -> {target}: {src}")
        return None
    t = base_format(target)
    stem = os.path.splitext(src)[0]
    if engine == "pdftoppm":
        out = unique_path(stem + "-pages", "")
        os.makedirs(out)
    else:
        out = unique_path(stem, "." + t)

    try:
        if engine in ("magick", "heif-enc"):
            ok = convert_image(src, s, target, out)
        elif engine == "ffmpeg":
            ok = convert_av(src, t, out)
        else:
            ok = convert_document(engine, src, s, t, out)
    except Exception as error:  # a crash must still clean up partial output
        log(f"error: {error!r}")
        ok = False

    if engine == "pdftoppm" and ok:
        ok = bool(os.listdir(out))
    if not ok or not os.path.exists(out):
        if os.path.isdir(out) and not os.path.islink(out):
            shutil.rmtree(out, ignore_errors=True)
        elif os.path.lexists(out):
            os.remove(out)
        return None
    return out


def print_matrix() -> None:
    for raw in all_extensions():
        norm = normalize_ext(raw)
        print(" ".join([raw, norm, CATEGORY[norm]] + targets_for("x." + raw)))


def expand(args: list[str]) -> tuple[list[str], list[str]]:
    """Supported files among args, with folders expanded one level; and the skipped args."""
    files, skipped = [], []
    for arg in args:
        if os.path.isdir(arg):
            for name in sorted(os.listdir(arg)):
                path = os.path.join(arg, name)
                if not name.startswith(".") and os.path.isfile(path) and category_of(path):
                    files.append(path)
        elif os.path.isfile(arg) and category_of(arg):
            files.append(arg)
        else:
            skipped.append(arg)
    return files, skipped


def convert(args: list[str], target: str, interactive: bool) -> int:
    alert = ui.alert if interactive else lambda message: print("rightconvert: " + message, file=sys.stderr)
    notify = ui.notify if interactive else lambda message: None

    files, skipped = expand(args)
    if not files:
        if args:
            alert("None of the selected items are a supported file type.")
        else:
            print(USAGE, file=sys.stderr)
        return 1

    common: list[str] | None = None
    owns, cats = [], []
    for f in files:
        own = ext_of(f)
        if own not in owns:
            owns.append(own)
        if CATEGORY[own] not in cats:
            cats.append(CATEGORY[own])
        options = targets_for(f) + [own]
        common = options if common is None else [t for t in common if t in options]
    assert common is not None
    if len(owns) == 1:
        common = [t for t in common if t != owns[0]]

    if not common:
        missing = []
        for category in cats:
            missing += [m for m in missing_engines_for(category) if m not in missing]
        if missing:
            alert("No output formats are available for this selection. Install the missing converters:"
                  + "".join("\n  " + INSTALL_HINT[m] for m in missing))
        else:
            alert("The selected files don't share an output format. Select files of one kind and try again.")
        return 1

    if not target:
        prompt = f'Convert "{os.path.basename(files[0])}" to:' if len(files) == 1 else f"Convert {len(files)} files to:"
        category = cats[0] if len(cats) == 1 else "mixed"
        index = ui.pick(prompt, [label_for(category, t) for t in common])
        if index is None:
            return 0
        target = common[index]
    elif target not in common:
        alert(f"Can't convert the selected files to '{target}'. Available: {', '.join(common)}")
        return 1

    name = label_for("", target)
    log_header(f"converting {len(files)} file(s) to {target}")
    notify(f"Converting {len(files)} file(s) to {name}...")

    done = same = 0
    failed = []
    for f in files:
        if ext_of(f) == base_format(target):
            same += 1
            continue
        out = convert_one(f, target)
        if out:
            done += 1
            print(out, flush=True)
            log(f"ok: {f} -> {out}")
        else:
            failed.append(os.path.basename(f))
            log(f"FAILED: {f} -> {target}")
            print(f"rightconvert: failed to convert {f} (see {log_path()})", file=sys.stderr)

    summary = f"Converted {done} file(s) to {name}."
    if same:
        summary += f" Skipped {same} already in {base_format(target).upper()}."
    if skipped:
        summary += f" Skipped {len(skipped)} unsupported."
    if failed:
        summary += f" {len(failed)} failed: {', '.join(failed)}. Details in {log_path()}"
        alert(summary)
        return 1
    notify(summary)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    # Piped output on Windows defaults to the legacy code page, which can't encode every file name.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure") and not stream.isatty():
            stream.reconfigure(encoding="utf-8")
    target, list_only, gui, batch, interactive = "", False, False, False, True
    args: list[str] = []
    try:
        i = 0
        while i < len(argv):
            a = argv[i]
            if a == "--to":
                if i + 1 >= len(argv):
                    raise UsageError("--to needs a format")
                target, interactive = normalize_ext(argv[i + 1]), False
                i += 1
            elif a.startswith("--to="):
                target, interactive = normalize_ext(a[5:]), False
            elif a == "--list":
                list_only, interactive = True, False
            elif a == "--matrix":
                print_matrix()
                return 0
            elif a == "--gui":
                gui = True
            elif a == "--batch":
                batch = True
            elif a in ("--register", "--unregister") and WINDOWS:
                from . import windows

                return windows.register() if a == "--register" else windows.unregister()
            elif a in ("-h", "--help"):
                print(USAGE)
                return 0
            elif a in ("-V", "--version"):
                print("rightconvert " + __version__)
                return 0
            elif a == "--":
                args += argv[i + 1:]
                break
            elif a.startswith("-") and a != "-":
                raise UsageError("unknown option " + a + "\n" + USAGE)
            else:
                args.append(a)
            i += 1
    except UsageError as error:
        print("rightconvert: " + str(error), file=sys.stderr)
        return 2
    if gui:
        interactive = True

    rotate()

    if list_only:
        if len(args) != 1:
            print(USAGE, file=sys.stderr)
            return 2
        for t in targets_for(args[0]):
            print(t)
        return 0

    if batch:
        from .batch import run_batched

        return run_batched(args, target, lambda paths: convert(paths, target, interactive))
    return convert(args, target, interactive)
