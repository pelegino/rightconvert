# Changelog

All notable changes are listed here. The project follows [semantic versioning](https://semver.org).

## 1.0.0

First public release.

- **Convert** submenu in Finder (macOS 13+) and Explorer (Windows 10 and 11) that lists the formats the selected files can become, with a format picker for folders.
- Images, video, audio, PDFs, documents, spreadsheets, and presentations, converted locally with ffmpeg, ImageMagick, libheif, poppler, pandoc, LibreOffice, and `textutil`.
- Lossless output where the format allows it: bit-exact images and audio, stream copies for container changes, and measured quality floors for unavoidable re-encodes.
- **(smaller file)** variants of WebP, HEIC, and AVIF.
- `rightconvert` command-line tool with `--to`, `--list`, `--matrix`, and `--version`.
- Installers for macOS (Homebrew) and Windows (winget).
