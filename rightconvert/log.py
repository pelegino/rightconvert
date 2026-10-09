"""Conversion log and the subprocess runner that writes to it."""

from __future__ import annotations

import os
import shlex
import subprocess
import time

from .engines import MACOS, NO_WINDOW, WINDOWS, tool, tool_env


def log_path() -> str:
    if MACOS:
        return os.path.expanduser("~/Library/Logs/rightconvert.log")
    if WINDOWS:
        return os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "RightConvert", "rightconvert.log")
    return os.path.join(os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")), "rightconvert.log")


def rotate() -> None:
    path = log_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        if os.path.getsize(path) > 5 * 1024 * 1024:
            os.replace(path, path + ".old")
    except OSError:
        pass


def log(message: str) -> None:
    try:
        with open(log_path(), "a", encoding="utf-8") as f:
            f.write(message + "\n")
    except OSError:
        pass


def log_header(message: str) -> None:
    log("=== " + time.strftime("%Y-%m-%d %H:%M:%S") + " " + message)


def run(args: list[str], cwd: str | None = None) -> bool:
    """Run a conversion tool, appending its command line and output to the log."""
    exe = tool(args[0])
    if not exe:
        log("missing tool: " + args[0])
        return False
    args = [exe] + args[1:]
    log("+ " + " ".join(shlex.quote(a) for a in args))
    try:
        result = subprocess.run(args, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, env=tool_env(), creationflags=NO_WINDOW)
    except OSError as error:
        log(str(error))
        return False
    output = result.stdout.decode("utf-8", "replace").strip()
    if output:
        log(output)
    return result.returncode == 0
