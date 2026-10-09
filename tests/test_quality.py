"""Measures conversion fidelity. Lossless targets must be bit-exact; lossy targets must clear a
visually/audibly transparent bar; container changes must copy streams untouched."""

from __future__ import annotations

import os
import re
import shutil
import unittest

from helpers import WorkDir, convert, make_pdf, run_tool, targets


def pixels_differ(a: str, b: str) -> float:
    return float(run_tool("magick", "compare", "-metric", "AE", a, b, "null:").stderr.split()[0])


def psnr(a: str, b: str) -> float:
    value = run_tool("magick", "compare", "-metric", "PSNR", a, b, "null:").stderr.split()[0]
    return float("inf") if value == "inf" else float(value)


def pcm_md5(path: str) -> str:
    return run_tool("ffmpeg", "-v", "error", "-i", path, "-map", "0:a:0", "-c:a", "pcm_s32le", "-f", "md5", "-").stdout.strip()


def stream_md5(path: str, stream: str) -> str:
    return run_tool("ffmpeg", "-v", "error", "-i", path, "-map", f"0:{stream}:0", "-c", "copy", "-f", "md5", "-").stdout.strip()


def probe(path: str, stream: str, entry: str) -> str:
    out = run_tool("ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", f"stream={entry}",
                   "-of", "default=nw=1:nk=1", path).stdout
    return (out.splitlines() or [""])[0].strip()


def ssim(output: str, reference: str) -> float:
    """Mean SSIM over all frames, with the reference cropped to the output's size."""
    w, h = probe(output, "v:0", "width"), probe(output, "v:0", "height")
    # Pair frames by index: containers round timestamps differently (WebM uses milliseconds).
    graph = f"[0:v]settb=1/30,setpts=N[out];[1:v]crop={w}:{h}:0:0,settb=1/30,setpts=N[ref];[out][ref]ssim"
    log = run_tool("ffmpeg", "-nostdin", "-i", output, "-i", reference, "-lavfi", graph, "-f", "null", "-").stderr
    match = re.search(r"All:([0-9.]+)", log)
    return float(match.group(1)) if match else 0.0


class Quality(WorkDir):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        w = cls.work
        ff = ["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i"]
        run_tool(*ff, "testsrc2=size=1280x720", "-frames:v", "1", "photo.png", cwd=w)
        run_tool(*ff, "anoisesrc=d=3:c=pink:r=96000:a=0.5", "-c:a", "pcm_s24le", "studio.wav", cwd=w)
        run_tool(*ff, "sine=f=440:d=3:r=44100", "-c:a", "pcm_s16le", "cd.wav", cwd=w)
        run_tool(*ff, "testsrc2=d=3:size=1280x720:rate=30", "-f", "lavfi", "-i", "sine=d=3", "-shortest",
                 "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "clip.mp4", cwd=w)
        run_tool(*ff, "testsrc2=d=2:size=1280x720:rate=30", "-c:v", "libx265", "-pix_fmt", "yuv420p10le",
                 "-x265-params", "log-level=error", "-tag:v", "hvc1", "hdr.mov", cwd=w)
        run_tool(*ff, "testsrc2=d=2:size=641x361:rate=30", "-c:v", "mjpeg", "-q:v", "2", "odd.avi", cwd=w)
        make_pdf(os.path.join(w, "page.pdf"), "Quality test page")

    def offered(self, path: str, target: str) -> str:
        """Convert, or skip if this machine's tools don't offer the target."""
        if target not in targets(self.path(path)):
            self.skipTest(f"{target} isn't available for {path} with the tools installed here")
        out = convert(target, self.path(path))
        self.assertTrue(out, f"{path} -> {target} produced no output")
        return out

    # ------------------------------------------------------------ images

    def test_lossless_images_are_pixel_identical(self):
        shutil.copy(self.path("photo.png"), self.path("src.tiff"))
        for t in ("png", "tiff", "bmp", "webp", "heic", "avif"):
            with self.subTest(target=t):
                out = self.offered("src.tiff" if t == "png" else "photo.png", t)
                self.assertEqual(pixels_differ(self.path("photo.png"), out), 0)

    def test_jpg_is_transparent(self):
        out = self.offered("photo.png", "jpg")
        self.assertGreaterEqual(psnr(self.path("photo.png"), out), 45)

    def test_smaller_variants_shrink_and_stay_above_40db(self):
        run_tool("magick", "-seed", "7", "-size", "1920x1080", "plasma:fractal", "-blur", "0x1.2", "-quality", "92",
                 "scenery.jpg", cwd=self.work)
        source = os.path.getsize(self.path("scenery.jpg"))
        for t in ("webp", "heic", "avif"):
            with self.subTest(target=t + "-small"):
                out = self.offered("scenery.jpg", t + "-small")
                value = psnr(self.path("scenery.jpg"), out)
                print(f"\n  {t}-small: {os.path.getsize(out) // 1024} KB vs {source // 1024} KB, PSNR {value:.1f} dB", end="")
                self.assertLess(os.path.getsize(out), source)
                self.assertGreaterEqual(value, 40)

    # ------------------------------------------------------------ audio

    def test_lossless_audio_is_sample_identical(self):
        reference = pcm_md5(self.path("studio.wav"))
        for t in ("flac", "aiff", "m4a"):
            with self.subTest(target=t):
                out = self.offered("studio.wav", t)
                self.assertEqual(pcm_md5(out), reference)
                self.assertEqual(probe(out, "a:0", "sample_rate"), "96000")

    def test_flac_round_trip(self):
        flac = self.offered("cd.wav", "flac")
        back = convert("wav", flac)
        self.assertEqual(probe(back, "a:0", "codec_name"), "pcm_s16le")
        self.assertEqual(pcm_md5(back), pcm_md5(self.path("cd.wav")))

    def test_mp3_is_320k(self):
        out = self.offered("studio.wav", "mp3")
        self.assertEqual(probe(out, "a:0", "bit_rate"), "320000")

    def test_audio_extraction_copies_aac(self):
        out = self.offered("clip.mp4", "m4a")
        self.assertEqual(stream_md5(out, "a"), stream_md5(self.path("clip.mp4"), "a"))

    # ------------------------------------------------------------ video

    def test_container_changes_copy_streams(self):
        for t in ("mov", "mkv"):
            with self.subTest(target=t):
                out = self.offered("clip.mp4", t)
                for stream in ("v", "a"):
                    self.assertEqual(stream_md5(out, stream), stream_md5(self.path("clip.mp4"), stream))

    def test_hevc_copied_with_apple_tag(self):
        out = self.offered("hdr.mov", "mp4")
        self.assertEqual(stream_md5(out, "v"), stream_md5(self.path("hdr.mov"), "v"))
        self.assertEqual(probe(out, "v:0", "codec_tag_string"), "hvc1")

    def test_10bit_stays_10bit(self):
        out = self.offered("hdr.mov", "webm")
        self.assertEqual(probe(out, "v:0", "pix_fmt"), "yuv420p10le")

    def test_reencode_is_visually_lossless_and_cropped(self):
        out = self.offered("odd.avi", "mp4")
        self.assertEqual((probe(out, "v:0", "width"), probe(out, "v:0", "height")), ("640", "360"))
        self.assertGreaterEqual(ssim(out, self.path("odd.avi")), 0.99)

    def test_vp9_is_visually_lossless(self):
        out = self.offered("clip.mp4", "webm")
        self.assertGreaterEqual(ssim(out, self.path("clip.mp4")), 0.99)

    # ------------------------------------------------------------ PDF

    def test_pdf_renders_at_300_dpi(self):
        out = self.offered("page.pdf", "png")
        page = os.path.join(out, sorted(os.listdir(out))[0])
        self.assertEqual(run_tool("magick", "identify", "-format", "%w", page).stdout, "2550")


if __name__ == "__main__":
    unittest.main()
