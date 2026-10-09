"""Image, audio and video conversion. Lossless wherever the target allows it."""

from __future__ import annotations

import os
import shutil
import tempfile

from .engines import capture, ffmpeg_encoders, magick_writable
from .formats import CATEGORY, base_format, ext_of, is_small
from .log import log, run

# ---------------------------------------------------------------- images


def convert_image(src: str, s: str, target: str, out: str) -> bool:
    t = base_format(target)
    small = is_small(target)
    pre = ["-background", "none", "-density", "288"] if s == "svg" else []
    # Single-frame formats take only the first frame of animated or multi-page input.
    frame = src + "[0]" if t in ("jpg", "png", "bmp", "ico", "heic", "avif") else src
    opts = ["-auto-orient"]

    if not small and t in ("heic", "avif"):
        # ImageMagick's HEIF writer always goes through lossy YUV; heif-enc -L encodes RGB losslessly.
        tmp = tempfile.mkdtemp(prefix="rightconvert")
        try:
            png = os.path.join(tmp, "frame.png")
            if run(["magick"] + pre + [frame] + opts + [png]) and \
                    run(["heif-enc", "-L"] + (["-A"] if t == "avif" else []) + [png, "-o", out]):
                return True
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        if t not in magick_writable():
            return False
        # Inputs heif-enc can't store losslessly (e.g. 16-bit) get the highest lossy quality instead.
        log(f"lossless {t} encode failed; using quality 95")

    if t == "jpg":
        opts += ["-background", "white", "-alpha", "remove", "-alpha", "off", "-quality", "95", "-sampling-factor", "4:4:4"]
    elif t == "webp":
        if small:
            opts += ["-quality", "85", "-define", "webp:use-sharp-yuv=true", "-define", "webp:method=6"]
        else:
            opts += ["-define", "webp:lossless=true", "-define", "webp:exact=true", "-quality", "100"]
    elif t in ("heic", "avif"):
        # Smaller-file qualities measured to stay above 40 dB PSNR (see tests/test_quality.py).
        if small:
            opts += ["-quality", "60" if t == "heic" else "70"]
        else:
            opts += ["-quality", "95", "-define", "heic:chroma=444"]
    elif t in ("tiff", "pdf"):
        # Without an explicit lossless codec, ImageMagick may reuse a JPEG source's compression.
        opts += ["-compress", "zip"]
    elif t == "png":
        opts += ["-define", "png:compression-level=9"]
    elif t == "ico":
        opts += ["-background", "none", "-resize", "256x256>", "-define", "icon:auto-resize=256,128,64,48,32,16"]
    return run(["magick"] + pre + [frame] + opts + [out])


# ---------------------------------------------------------------- audio and video

LOSSLESS_AUDIO = {"flac", "alac", "wavpack", "ape", "tta", "truehd", "mlp", "pcm_u8", "pcm_s16le", "pcm_s16be",
                  "pcm_s24le", "pcm_s24be", "pcm_s32le", "pcm_s32be", "pcm_f32le", "pcm_f32be", "pcm_f64le",
                  "pcm_f64be"}

# Codecs each container can hold as-is, so they're copied instead of re-encoded. MKV holds anything.
VIDEO_COPY = {"mp4": {"h264", "hevc", "av1", "mpeg4"}, "mov": {"h264", "hevc", "av1", "mpeg4", "prores", "mjpeg"},
              "webm": {"vp8", "vp9", "av1"}}
AUDIO_COPY = {"mp4": {"aac", "mp3", "alac", "ac3", "eac3", "opus", "flac"},
              "mov": {"aac", "mp3", "alac", "ac3", "eac3", "pcm_s16le", "pcm_s24le", "pcm_s16be", "pcm_s24be",
                      "pcm_f32le"},
              "webm": {"opus", "vorbis"}}


class Probe:
    """Stream properties of one input file, queried lazily with ffprobe."""

    def __init__(self, path: str):
        self.path = path
        self._cache: dict[tuple[str, str], str] = {}

    def get(self, stream: str, entry: str) -> str:
        key = (stream, entry)
        if key not in self._cache:
            out = capture(["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries", f"stream={entry}",
                           "-of", "default=nw=1:nk=1", self.path])
            self._cache[key] = (out.splitlines() or [""])[0].strip()
        return self._cache[key]

    def pcm_depth(self) -> str:
        """s16, s24, s32 or f32, matching the source's precision."""
        fmt = self.get("a:0", "sample_fmt")
        if fmt.startswith(("u8", "s16")):
            return "s16"
        if fmt.startswith("s32"):
            return "s24" if self.get("a:0", "bits_per_raw_sample") == "24" else "s32"
        # Float decoders: keep real float sources exact; 24-bit is beyond transparent for lossy ones.
        return "f32" if self.get("a:0", "codec_name") in LOSSLESS_AUDIO else "s24"


def _audio_args(p: Probe, t: str, allow_copy: bool) -> list[str]:
    codec = p.get("a:0", "codec_name") if allow_copy else ""
    lossless = p.get("a:0", "codec_name") in LOSSLESS_AUDIO
    depth = p.pcm_depth()
    planar, packed = ("s16p", "s16") if depth == "s16" else ("s32p", "s32")
    if t == "mp3":
        args = ["-c:a", "copy"] if codec == "mp3" else ["-c:a", "libmp3lame", "-b:a", "320k"]
    elif t == "m4a":
        if codec in ("aac", "alac"):
            args = ["-c:a", "copy"]
        elif lossless:
            args = ["-c:a", "alac", "-sample_fmt", planar]
        else:
            args = ["-c:a", "aac", "-b:a", "320k"]
    elif t == "ogg":
        if codec in ("opus", "vorbis"):
            args = ["-c:a", "copy"]
        elif "libvorbis" in ffmpeg_encoders():
            args = ["-c:a", "libvorbis", "-q:a", "10"]
        else:
            args = ["-c:a", "libopus", "-b:a", "256k"]
    elif t == "opus":
        args = ["-c:a", "copy"] if codec == "opus" else ["-c:a", "libopus", "-b:a", "256k"]
    elif t == "flac":
        args = ["-c:a", "copy"] if codec == "flac" else ["-c:a", "flac", "-compression_level", "8", "-sample_fmt", packed]
    elif t == "wav":
        args = ["-c:a", f"pcm_{depth}le"]
    else:  # aiff
        args = ["-c:a", "pcm_s32be" if depth == "f32" else f"pcm_{depth}be"]
    if depth == "s24" and args[1] in ("flac", "alac"):
        args += ["-bits_per_raw_sample", "24"]
    return args


def _video_args(p: Probe, t: str, allow_copy: bool) -> list[str]:
    vcodec, acodec, pix = p.get("v:0", "codec_name"), p.get("a:0", "codec_name"), p.get("v:0", "pix_fmt")
    maps = ["-map", "0:v:0", "-map", "0:a?"]

    if allow_copy and (t == "mkv" or vcodec in VIDEO_COPY[t]):
        v = ["-c:v", "copy"]
        if vcodec == "hevc" and t in ("mp4", "mov"):
            v += ["-tag:v", "hvc1"]
    elif pix.endswith(("10le", "10be", "12le", "12be")):
        # 10/12-bit (HDR) sources stay 10-bit.
        if t == "webm":
            v = ["-c:v", "libvpx-vp9", "-profile:v", "2", "-pix_fmt", "yuv420p10le", "-crf", "12", "-b:v", "0", "-row-mt", "1"]
        else:
            v = ["-c:v", "libx265", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p10le", "-tag:v", "hvc1"]
    else:
        # 4:2:0 needs even dimensions; crop one pixel rather than rescale.
        v = ["-vf", "crop=trunc(iw/2)*2:trunc(ih/2)*2"]
        if t == "webm":
            v += ["-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-crf", "12", "-b:v", "0", "-row-mt", "1",
                  "-deadline", "good", "-cpu-used", "2"]
        else:
            v += ["-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p"]

    if not acodec:
        a: list[str] = []
    elif allow_copy and (t == "mkv" or acodec in AUDIO_COPY[t]):
        a = ["-c:a", "copy"]
    elif t == "webm":
        a = ["-c:a", "libopus", "-b:a", "256k"]
    elif acodec in LOSSLESS_AUDIO:
        a = ["-c:a", "alac", "-sample_fmt", "s16p" if p.pcm_depth() == "s16" else "s32p"]
    else:
        a = ["-c:a", "aac", "-b:a", "320k"]

    if t == "mkv" and allow_copy:
        maps += ["-map", "0:s?"]
        a += ["-c:s", "copy"]
    args = maps + v + a
    if t in ("mp4", "mov"):
        args += ["-movflags", "+faststart"]
    return args


def _gif_args(p: Probe) -> list[str]:
    """Full resolution, frame rate capped at 30 fps, best 256-color palette."""
    filt = "split[a][b];[a]palettegen=max_colors=256:stats_mode=full[p];[b][p]paletteuse=dither=sierra2_4a"
    num, _, den = p.get("v:0", "r_frame_rate").partition("/")
    try:
        if int(num) / int(den or 1) > 30:
            filt = "fps=30," + filt
    except (ValueError, ZeroDivisionError):
        pass
    return ["-an", "-map", "0:v:0", "-vf", filt, "-loop", "0"]


def convert_av(src: str, t: str, out: str) -> bool:
    p = Probe(src)
    category = CATEGORY.get(ext_of(src))
    # First try copying streams the target can hold; if the muxer rejects that, re-encode everything.
    for allow_copy in (True, False):
        if t in ("mp4", "mov", "mkv", "webm"):
            args = _video_args(p, t, allow_copy)
        elif t == "gif":
            args = _gif_args(p)
        else:
            args = ["-map", "0:a:0"] + _audio_args(p, t, allow_copy)
            # Keep embedded cover art when the target supports it.
            if allow_copy and category == "audio" and t in ("mp3", "m4a", "flac") and p.get("v:0", "codec_name"):
                args += ["-map", "0:v:0", "-c:v", "copy", "-disposition:v:0", "attached_pic"]
            else:
                args += ["-vn"]
        if run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", src] + args + [out]):
            return True
        if t == "gif":
            return False
        log("retrying without stream copy")
    return False
