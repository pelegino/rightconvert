"""Fast tests of engine selection, labels, multi-file batching and the Explorer menu definition."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

from helpers import CLI, ROOT, WINDOWS, run_tool

from rightconvert import batch, engines, formats


class EngineSelection(unittest.TestCase):
    def tools(self, installed: set[str], writable: set[str] = frozenset()):
        return [mock.patch.object(engines, "has", lambda name: name in installed),
                mock.patch.object(engines, "magick_writable", lambda: frozenset(writable))]

    def offered(self, installed, writable=frozenset(), path="x.png"):
        patches = self.tools(installed, writable)
        for p in patches:
            p.start()
        try:
            return engines.targets_for(path)
        finally:
            for p in patches:
                p.stop()

    def test_lossless_heif_needs_heif_enc(self):
        offered = self.offered({"magick"}, {"avif"})
        self.assertNotIn("heic", offered)
        self.assertNotIn("avif", offered)
        self.assertIn("avif-small", offered)
        self.assertNotIn("heic-small", offered)

    def test_heif_enc_enables_lossless(self):
        offered = self.offered({"magick", "heif-enc"}, {"heic", "avif"})
        for t in ("heic", "heic-small", "avif", "avif-small"):
            self.assertIn(t, offered)
        self.assertEqual(offered.index("heic") + 1, offered.index("heic-small"))

    def test_documents_without_textutil_use_libreoffice(self):
        with mock.patch.object(engines, "has", lambda name: name in {"soffice"}):
            self.assertEqual(engines.engine_for("docx", "doc"), "soffice")
            self.assertEqual(engines.engine_for("txt", "rtf"), "soffice")
            self.assertIsNone(engines.engine_for("md", "pdf"))

    def test_nothing_installed_offers_nothing(self):
        for name in ("x.jpg", "x.mp4", "x.pdf", "x.docx", "x.xlsx"):
            self.assertEqual(self.offered(set(), path=name), [])


class Labels(unittest.TestCase):
    def test_labels_match_finder_extension(self):
        with open(os.path.join(ROOT, "app", "FinderSync", "FinderSync.swift"), encoding="utf-8") as f:
            swift = f.read()
        for suffix in ("(smaller file)", "(audio only)", "(animated)", "(one image per page)"):
            self.assertIn(suffix, swift)
        self.assertEqual(formats.label_for("image", "webp-small"), "WEBP (smaller file)")
        self.assertEqual(formats.label_for("video", "mp3"), "MP3 (audio only)")
        self.assertEqual(formats.label_for("pdf", "jpg"), "JPG (one image per page)")
        self.assertEqual(formats.label_for("mixed", "mp3"), "MP3")

    def test_aliases_normalize(self):
        self.assertEqual(formats.ext_of("A.JPEG"), "jpg")
        self.assertEqual(formats.ext_of("song.aif"), "aiff")
        self.assertEqual(formats.category_of("noext"), "")


class Batching(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="rightconvert-spool-")
        self.addCleanup(shutil.rmtree, self.root, True)

    def test_concurrent_requests_become_one_batch(self):
        batches, statuses = [], []

        def worker(name):
            statuses.append(batch.run_batched([name], "mp3", lambda paths: batches.append(paths) or 0, root=self.root))

        threads = [threading.Thread(target=worker, args=(f"file{i}.wav",)) for i in range(6)]
        for t in threads:
            t.start()
            time.sleep(0.05)
        for t in threads:
            t.join()
        self.assertEqual(len(batches), 1, batches)
        self.assertEqual(sorted(os.path.basename(p) for p in batches[0]), [f"file{i}.wav" for i in range(6)])
        self.assertEqual(statuses, [0] * 6)

    def test_request_during_conversion_is_not_lost(self):
        batches = []

        def slow(paths):
            batches.append(paths)
            if len(batches) == 1:
                # A new right-click arrives while the first batch is converting; that process
                # finds the lock taken and leaves its request for the leader.
                batch.run_batched(["late.wav"], "mp3", lambda p: self.fail("follower converted"), root=self.root)
            return 0

        batch.run_batched(["first.wav"], "mp3", slow, root=self.root)
        self.assertEqual([[os.path.basename(p) for p in b] for b in batches], [["first.wav"], ["late.wav"]])

    def test_failures_propagate(self):
        self.assertEqual(batch.run_batched(["a"], "x", lambda p: 1, root=self.root), 1)

    def test_separate_processes_share_one_batch(self):
        run_tool("ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=0.2", os.path.join(self.root, "a.wav"))
        for name in ("b.wav", "c.wav", "d.wav"):
            shutil.copy(os.path.join(self.root, "a.wav"), os.path.join(self.root, name))
        procs = [subprocess.Popen([sys.executable, CLI, "--batch", "--to", "flac", "--", os.path.join(self.root, n)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                 for n in ("a.wav", "b.wav", "c.wav", "d.wav")]
        outputs = [p.communicate(timeout=120)[0].split() for p in procs]
        self.assertEqual([p.returncode for p in procs], [0] * 4)
        self.assertEqual(sum(1 for o in outputs if o), 1, "exactly one process should do the converting")
        self.assertEqual(sorted(os.path.basename(f) for o in outputs for f in o), ["a.flac", "b.flac", "c.flac", "d.flac"])


class ExplorerMenu(unittest.TestCase):
    def setUp(self):
        from rightconvert import windows

        self.windows = windows

    def test_same_target_same_verb_across_extensions(self):
        with mock.patch.object(engines, "has", lambda name: name in {"magick"}), \
                mock.patch.object(engines, "magick_writable", lambda: frozenset({"avif"})):
            jpg = {t: key for key, _, t in self.windows.menu_entries("jpg")}
            png = {t: key for key, _, t in self.windows.menu_entries("png")}
            jpeg = self.windows.menu_entries("jpeg")
        self.assertNotIn("jpg", jpg)
        for t in set(jpg) & set(png):
            self.assertEqual(jpg[t], png[t])
        keys = [key for key, _, _ in jpeg]
        self.assertEqual(keys, sorted(keys), "Explorer orders verbs by key name")
        self.assertIn(("07_avif-small", "AVIF (smaller file)", "avif-small"), jpeg)

    def test_command_quoting(self):
        command = self.windows.command("webp-small")
        self.assertRegex(command, r'^".+" ".+rightconvert" --gui --batch --to webp-small -- "%1"$')
        self.assertNotIn("--to", self.windows.command())

    @unittest.skipUnless(WINDOWS, "Windows registry")
    def test_register_and_unregister(self):
        import winreg

        def read(path, name=None):
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, path) as key:
                return winreg.QueryValueEx(key, name)[0]

        base = r"Software\Classes\SystemFileAssociations\.wav\shell\RightConvert"
        self.windows.register()
        try:
            self.assertEqual(read(base, "MUIVerb"), "Convert")
            self.assertEqual(read(base, "SubCommands"), "")
            entries = self.windows.menu_entries("wav")
            key, label, target = entries[0]
            self.assertEqual(read(rf"{base}\shell\{key}", "MUIVerb"), label)
            self.assertIn(f"--to {target} ", read(rf"{base}\shell\{key}\command"))
            self.assertTrue(re.search(r"pythonw?\.exe", read(r"Software\Classes\Directory\shell\RightConvert\command")))
        finally:
            self.windows.unregister()
        with self.assertRaises(FileNotFoundError):
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, base)


if __name__ == "__main__":
    unittest.main()
