# Security

## Reporting a vulnerability

Please report security problems privately through [GitHub's private vulnerability reporting](https://github.com/pelegino/rightconvert/security/advisories/new), not in a public issue. Include the platform, the steps to reproduce, and what an attacker could achieve. You'll get a reply within a week.

Only the latest release is supported with fixes.

## Security model

RightConvert never sends files or data over the network. Everything below concerns what other software on the same computer could make it do.

- **macOS:** the sandboxed Finder extension asks the helper app to convert files by opening a `rightconvert://` link. Any app or web page can open such a link, so the helper ignores requests that don't carry a random token. The token is stored in `~/Library/Application Support/rightconvert/token`, readable only by your user account.
- **Windows:** the Explorer menu is registered under `HKEY_CURRENT_USER` and runs with your own permissions. Nothing is installed system-wide by RightConvert itself.
- **Conversion tools:** files are opened by ffmpeg, ImageMagick, poppler, pandoc, and LibreOffice. A malicious file could exploit a bug in one of those tools, so keep them up to date with `brew upgrade` or `winget upgrade --all`. Converted files are written next to the source, never over an existing file.
