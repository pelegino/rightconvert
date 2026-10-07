<p align="center"><img src="docs/icon.png" width="128" alt="RightConvert icon"></p>

<h1 align="center">RightConvert</h1>

<p align="center">Right-click any file on your Mac, hover <b>Convert</b>, pick a format. Done.</p>

<p align="center"><img src="docs/menu.png" width="420" alt="The Convert item in Finder's right-click menu"></p>

RightConvert adds a **Convert** submenu to Finder that turns images, video, audio, PDFs, and documents into other formats. The converted file is saved next to the original, and the original is never touched or overwritten.

- **100% local.** Your files never leave your Mac. Conversions run with ffmpeg, ImageMagick, libheif, poppler, pandoc, LibreOffice, and macOS's built-in `textutil`.
- **No quality loss where the format allows it.** Lossless targets come out bit-exact, and container changes copy streams instead of re-encoding. See [Quality](#quality).
- **Only valid choices.** The submenu lists only the formats your selected files can actually become with the tools you have installed.

## Install

Requirements: macOS 13 or later, [Homebrew](https://brew.sh), and Xcode or the Command Line Tools (`xcode-select --install`).

```sh
git clone https://github.com/peleg1711-boop/rightconvert.git
cd rightconvert
./install.sh
```

The installer:

1. Installs the conversion engines with Homebrew: `ffmpeg`, `imagemagick`, `libheif`, `poppler`, `pandoc`.
2. Asks whether to install LibreOffice (about 1 GB). It's needed for Word, Excel, and PowerPoint formats and for converting documents to PDF.
3. Builds `RightConvert.app` from source, installs it to `~/Applications`, and enables its Finder extension.
4. Links the `rightconvert` command into `~/.local/bin`.

Options: `--with-libreoffice`, `--no-libreoffice`, and `--skip-deps` (rebuild and reinstall only the app and CLI).

If **Convert** doesn't appear in the right-click menu, open System Settings > General > Login Items & Extensions, click the info button next to **Finder**, turn on **RightConvert**, and run `killall Finder`.

To remove it, run `./uninstall.sh`. The Homebrew packages stay installed.

## Usage

**In Finder:** select one or more files, right-click, hover **Convert**, and click a format.

- With several files selected, the submenu shows only formats they can all be converted to.
- If the selection includes a folder, **Convert...** opens a format picker instead and converts the files inside it. It goes one level deep and skips hidden files.
- A notification tells you when the conversion is done. If something fails, a dialog names the file and points to the log.

**In Terminal:**

```sh
rightconvert photo.heic                    # opens the format picker
rightconvert --to mp3 talk.mov more/       # no picker
rightconvert --to webp-small photo.jpg     # smaller lossy file instead of lossless
rightconvert --list report.docx            # formats this file can become
```

Output goes next to each source file. If `photo.jpg` already exists, the new file is saved as `photo-1.jpg`, then `photo-2.jpg`, and so on.

## Supported formats

| From | To | Engine |
| --- | --- | --- |
| Images: jpg, png, heic, webp, gif, tiff, bmp, avif, svg | jpg, png, webp, heic, avif, tiff, gif, bmp, ico, pdf | ImageMagick, libheif |
| Video: mp4, mov, mkv, avi, webm, m4v | mp4, mov, mkv, webm, animated gif, or audio only (mp3, m4a, wav) | ffmpeg |
| Audio: mp3, wav, m4a, aac, flac, ogg, opus, aiff | mp3, wav, m4a, flac, ogg, opus, aiff | ffmpeg |
| PDF | png or jpg (one image per page, in a `name-pages` folder), txt, docx | poppler, LibreOffice |
| Documents: docx, doc, odt, rtf, txt, md, html | pdf, docx, doc, odt, rtf, txt, md, html | pandoc, `textutil`, LibreOffice |
| Spreadsheets: xlsx, xls, ods, csv | xlsx, xls, ods, csv, pdf | LibreOffice |
| Presentations: pptx, ppt, odp | pptx, ppt, odp, pdf | LibreOffice |

If an engine isn't installed, the formats that need it are left out of the menu. After installing one later, run `./install.sh --skip-deps` to refresh the menu. Conversions among doc, docx, odt, rtf, txt, and html work with no installs at all, using `textutil`.

## Quality

Conversions never lose more than the target format forces them to. `tests/quality.sh` measures each of these guarantees.

**Bit-exact:**

- PNG, TIFF, BMP, WebP, HEIC, and AVIF are encoded losslessly, even from a JPEG source, so the output has exactly the input's pixels.
- FLAC, WAV, AIFF, and M4A (as Apple Lossless, when the source is lossless) keep every sample, plus the source's bit depth and sample rate. 24-bit/96 kHz stays 24-bit/96 kHz.
- When the target container can hold the original streams, they're copied byte for byte. That covers MP4 to MOV, anything to MKV, HEVC to MP4, AAC from a video to M4A, and MP3 audio to `.mp3`. Subtitles are kept when converting to MKV, and cover art is kept for MP3, M4A, and FLAC.

**Transparent when re-encoding is unavoidable:**

- Video uses H.264 at CRF 16, 10-bit HEVC for 10-bit/HDR sources, and VP9 at CRF 12 for WebM. These score at least 0.99 SSIM against the source. Odd-sized video is cropped by one pixel rather than rescaled.
- Audio uses MP3 at 320 kbps, AAC at 320 kbps, and Opus at 256 kbps.
- JPG uses quality 95 with full 4:4:4 color, and PDF pages render at 300 dpi.

**Smaller file.** Lossless images can be much larger than a JPEG original. WebP, HEIC, and AVIF each also appear as **(smaller file)**: a lossy encode that's typically 2 to 4 times smaller than the source JPEG and still above 40 dB PSNR.

**Unavoidable losses:**

- JPG, MP3, AAC, Opus/OGG, re-encoded video, and the smaller-file options are lossy by design.
- GIF holds at most 256 colors, and ICO at most 256x256 pixels.
- Converting a lossy file to a lossless format doesn't restore what was already lost.
- Document conversions keep only the formatting the target supports.
- Photo metadata such as EXIF isn't guaranteed to carry over to every format.

## How it works

```mermaid
flowchart LR
    Finder["Finder right-click"] --> Ext["Finder extension (sandboxed)"]
    Ext -->|"reads"| Matrix["matrix.txt: formats per extension"]
    Ext -->|"rightconvert:// link with secret token"| Host["RightConvert.app (background helper)"]
    Host --> CLI["bin/rightconvert"]
    CLI --> Engines["ffmpeg, ImageMagick, libheif, poppler, pandoc, LibreOffice, textutil"]
```

- `app/FinderSync/`: the Finder Sync extension that builds the **Convert** menu. Because it's sandboxed, it can't run converters itself. It reads the format table at `~/Library/Application Support/rightconvert/matrix.txt` and hands the selection to the helper app.
- `app/Host/`: `RightConvert.app`, a background helper with no Dock icon. It runs the bundled `rightconvert` script, refreshes the format table each time it launches, and quits when it's done. It only acts on requests carrying a random token stored in `~/Library/Application Support/rightconvert/token`, which other apps and web pages can't read.
- `app/icons/make-icons.swift`: draws the menu glyph and the app icon in code.
- `bin/rightconvert`: does every conversion. It's a standalone zsh script and works without the app.

## Troubleshooting

- **Convert doesn't appear in the menu.** Enable **RightConvert** under System Settings > General > Login Items & Extensions > Finder, then run `killall Finder`.
- **A format you expect is missing.** Its engine probably isn't installed. Install it, then run `./install.sh --skip-deps`.
- **A conversion failed.** Every command and its error output are logged to `~/Library/Logs/rightconvert.log`.
- **No notifications appear.** The first time, macOS may ask you to allow notifications from Script Editor, which is how notifications are shown. Allow them in System Settings > Notifications.
- **`brew install` fails with "You have not agreed to the Xcode license".** Run `sudo xcodebuild -license accept`, then run `./install.sh` again.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Run `tests/run.sh` and `tests/quality.sh` before opening a pull request.

## License

[MIT](LICENSE)
