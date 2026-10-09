"""Converts sample files to every format the installed tools support and checks each output's type,
then exercises the CLI's behavior and edge cases."""

from __future__ import annotations

import os
import shutil
import stat
import unittest

from helpers import HTML, RTF, WINDOWS, WorkDir, cli, convert, make_docx, make_pdf, output_ok, run_tool, targets, write


class Conversions(WorkDir):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        w = cls.work
        fixtures = []
        try:
            run_tool("ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", "audio.wav", cwd=w)
            # MJPEG with odd dimensions exercises the even-size crop on re-encode.
            run_tool("ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=1:size=321x241:rate=10",
                     "-f", "lavfi", "-i", "sine=duration=1", "-shortest", "-c:v", "mjpeg", "video.mov", cwd=w)
            run_tool("ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=64x48", "-frames:v", "1",
                     "image.png", cwd=w)
            fixtures += ["audio.wav", "video.mov", "image.png"]
        except unittest.SkipTest:
            pass
        write(os.path.join(w, "plain.txt"), "Plain text line one.\nLine two.\n")
        write(os.path.join(w, "notes.md"), "# Notes\n\nSome *markdown* with a [link](https://example.com).\n\n- one\n- two\n")
        write(os.path.join(w, "page.html"), HTML)
        write(os.path.join(w, "letter.rtf"), RTF)
        write(os.path.join(w, "table.csv"), "name,qty\napple,3\npear,5\n")
        make_pdf(os.path.join(w, "document.pdf"), "Hello from a PDF")
        fixtures += ["document.pdf", "plain.txt", "notes.md", "page.html", "letter.rtf", "table.csv"]
        try:
            if make_docx(os.path.join(w, "report.docx"), os.path.join(w, "page.html")):
                fixtures.append("report.docx")
        except unittest.SkipTest:
            pass
        cls.fixtures = [f for f in fixtures if os.path.getsize(os.path.join(w, f))]

    def test_every_offered_target(self):
        for fixture in self.fixtures:
            offered = targets(self.path(fixture))
            print(f"\n  {fixture} -> {' '.join(offered) or '(no engines installed)'}", end="")
            for t in offered:
                with self.subTest(fixture=fixture, target=t):
                    out = convert(t, self.path(fixture))
                    self.assertTrue(output_ok(t, out), f"{fixture} -> {t}: {out or 'no output'}")


class Behavior(WorkDir):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        run_tool("ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=1", "audio.wav", cwd=cls.work)
        run_tool("ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=1:size=64x48:rate=10",
                 "-f", "lavfi", "-i", "sine=duration=1", "-shortest", "-c:v", "mjpeg", "video.mov", cwd=cls.work)
        run_tool("ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=64x48", "-frames:v", "1",
                 "image.png", cwd=cls.work)

    def needs(self, path: str, target: str):
        if target not in targets(path):
            self.skipTest(f"{target} isn't available for {os.path.basename(path)} here")

    def test_never_overwrites(self):
        first = convert("mp3", self.path("audio.wav"))
        second = convert("mp3", self.path("audio.wav"))
        self.assertTrue(first and second and first != second)
        self.assertEqual(os.path.basename(second), "audio-1.mp3")

    def test_folder_expansion_skips_hidden_files(self):
        folder = self.path("folder")
        os.mkdir(folder)
        shutil.copy(self.path("audio.wav"), os.path.join(folder, "a.wav"))
        shutil.copy(self.path("audio.wav"), os.path.join(folder, ".hidden.wav"))
        cli("--to", "flac", folder)
        self.assertTrue(os.path.getsize(os.path.join(folder, "a.flac")))
        self.assertFalse(os.path.exists(os.path.join(folder, ".hidden.flac")))

    def test_audio_and_video_share_audio_targets(self):
        shutil.copy(self.path("audio.wav"), self.path("mixed.wav"))
        result = cli("--to", "mp3", self.path("mixed.wav"), self.path("video.mov"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 2)

    def test_rejects_incompatible_mix(self):
        self.assertNotEqual(cli("--to", "mp3", self.path("audio.wav"), self.path("image.png")).returncode, 0)

    def test_matrix_matches_list(self):
        rows = {line.split()[0]: line.split() for line in cli("--matrix").stdout.splitlines()}
        self.assertEqual(rows["jpeg"], ["jpeg", "jpg", "image"] + targets("x.jpeg"))
        self.assertEqual(rows["mp4"][:3], ["mp4", "mp4", "video"])

    def test_tricky_file_names(self):
        names = ["with spaces.png", "quote's.png", "a&b=c+d#1%.png", "émoji 🎉 שלום.png", "-leading-dash.png",
                 "UPPER.PNG", "photo.jpeg"]
        if not WINDOWS:
            names.append('double "quotes".png')
        for name in names:
            with self.subTest(name=name):
                shutil.copy(self.path("image.png"), self.path(name))
                out = convert("webp", self.path(name))
                self.assertEqual(out, self.path(os.path.splitext(name)[0] + ".webp"))
                self.assertTrue(output_ok("webp", out))

    def test_smaller_variant_writes_real_format(self):
        self.needs(self.path("image.png"), "webp-small")
        out = convert("webp-small", self.path("image.png"))
        self.assertTrue(out.endswith(".webp") and output_ok("webp", out), out)

    def test_smaller_variants_listed_for_images_only(self):
        small = [t for t in targets(self.path("image.png")) if t.endswith("-small")]
        self.assertTrue(set(small) <= {"webp-small", "heic-small", "avif-small"})
        self.assertIn("webp-small", small)
        self.assertFalse([t for t in targets(self.path("audio.wav")) if t.endswith("-small")])

    @unittest.skipIf(WINDOWS or (hasattr(os, "geteuid") and os.geteuid() == 0),
                     "read-only folders behave differently on Windows and as root")
    def test_read_only_folder_fails_cleanly(self):
        folder = self.path("locked")
        os.mkdir(folder)
        shutil.copy(self.path("audio.wav"), folder)
        os.chmod(folder, stat.S_IRUSR | stat.S_IXUSR)
        try:
            self.assertNotEqual(cli("--to", "mp3", os.path.join(folder, "audio.wav")).returncode, 0)
            self.assertEqual(sorted(os.listdir(folder)), ["audio.wav"])
        finally:
            os.chmod(folder, stat.S_IRWXU)

    def test_usage_errors_exit_2(self):
        self.assertEqual(cli("--to").returncode, 2)
        self.assertEqual(cli("--bogus", "x").returncode, 2)
        self.assertEqual(cli("--list").returncode, 2)

    def test_missing_and_unsupported_files_fail(self):
        self.assertNotEqual(cli("--to", "mp3", self.path("nope/file.wav")).returncode, 0)
        write(self.path("thing.xyz"), "x")
        self.assertNotEqual(cli("--to", "mp3", self.path("thing.xyz")).returncode, 0)

    def test_unavailable_target_fails(self):
        result = cli("--to", "docx", self.path("audio.wav"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("Available:", result.stderr)


if __name__ == "__main__":
    unittest.main()
