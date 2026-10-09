"""Merges the separate processes Explorer starts for a multi-file selection into one batch.

Every process drops its paths into a spool folder and tries to take a lock. The process that gets
the lock waits until no new paths arrive for QUIET seconds, then converts everything as one job
(one picker, one notification). The lock is an OS file lock, so it's released even if the leader
crashes.
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from typing import Callable

QUIET = 0.6


def spool_root() -> str:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
        return os.path.join(base, "RightConvert", "spool")
    return os.path.join(tempfile.gettempdir(), f"rightconvert-spool-{os.getuid()}")


def _lock(path: str) -> int | None:
    fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        if sys.platform == "win32":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return None
    return fd


def _unlock(fd: int) -> None:
    try:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _pending(folder: str) -> list[str]:
    return sorted(name for name in os.listdir(folder) if name.endswith(".req"))


def _collect(folder: str) -> list[str]:
    """Wait for the selection to finish arriving, then take every queued path."""
    seen, quiet_since = None, time.monotonic()
    while True:
        names = _pending(folder)
        if names != seen:
            seen, quiet_since = names, time.monotonic()
        elif time.monotonic() - quiet_since >= QUIET:
            break
        time.sleep(0.1)
    paths = []
    for name in seen:
        request = os.path.join(folder, name)
        try:
            with open(request, encoding="utf-8") as f:
                paths += [line for line in f.read().split("\n") if line]
            os.remove(request)
        except OSError:
            pass
    return paths


def run_batched(paths: list[str], target: str, convert: Callable[[list[str]], int], root: str | None = None) -> int:
    folder = os.path.join(root or spool_root(), target or "_pick")
    os.makedirs(folder, exist_ok=True)
    request = os.path.join(folder, f"{time.time_ns():020d}-{os.getpid()}.req")
    with open(request + ".tmp", "w", encoding="utf-8") as f:
        f.write("\n".join(os.path.abspath(p) for p in paths))
    os.replace(request + ".tmp", request)

    status = 0
    lock_path = os.path.join(folder, "lock")
    # A process that finds the lock taken leaves: the holder re-checks the spool after unlocking,
    # so requests written while it was busy are never stranded.
    while _pending(folder):
        fd = _lock(lock_path)
        if fd is None:
            break
        try:
            while _pending(folder):
                status = convert(_collect(folder)) or status
        finally:
            _unlock(fd)
    return status
