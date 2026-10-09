# Contributing

Thanks for helping out. Bug reports, new formats, and fixes are all welcome.

## Setup

**macOS:** you need macOS 13 or later, Homebrew, and Xcode or the Xcode Command Line Tools.

```sh
./install.sh                        # installs tools, builds and installs the app
cd tests && /usr/bin/python3 -m unittest -v
```

An Apple developer certificate isn't required. Without one, `app/build.sh` signs ad-hoc, which Finder accepts for local builds. After changing the Python code, run `./install.sh --skip-deps` so the installed app bundles the new copy.

**Windows:** run `windows\install.cmd`, then:

```powershell
cd tests
python -m unittest -v
```

After changing the Python code, run `windows\install.ps1 -SkipDeps` to copy it to the installed folder and refresh the Explorer menu.

The tests cover every conversion your installed tools support, the fidelity guarantees (bit-exact lossless output, stream copies, SSIM and PSNR floors), CLI edge cases, multi-file batching, and the Explorer menu. Tests for formats your machine can't produce are skipped, so install every tool to run them all. CI runs the full suite on macOS and Windows.

## Where things live

- `rightconvert/formats.py` holds the format table: `CATEGORY` maps extensions to a kind of file, and `TARGETS` lists what each kind can become.
- `rightconvert/engines.py` finds the installed tools and picks one for each conversion (`engine_for`).
- `rightconvert/media.py` and `rightconvert/documents.py` run the conversions. `rightconvert/cli.py` is the command-line interface both menus call.
- `rightconvert/ui.py` shows the picker, notifications, and alerts on each platform.
- `rightconvert/windows.py` and `rightconvert/batch.py` are the Explorer menu and the multi-file batching.
- `app/FinderSync/FinderSync.swift` builds the Finder menu from the table that `rightconvert --matrix` writes, and `app/Host/main.swift` is the helper app that runs conversions for the sandboxed extension.

Menu labels are generated in two places, `label_for` in `rightconvert/formats.py` and `label(category:format:)` in `FinderSync.swift`. Keep them in sync.

The converter must stay compatible with Python 3.9, which is what macOS ships, and use only the standard library.

## Guidelines

- Everything must run locally. Don't add network calls or cloud services.
- Don't lower quality. Lossless targets must stay bit-exact, and a container change must copy streams rather than re-encode. `tests/test_quality.py` enforces this, so add a check there when you add a format.
- Add a file-type check to `is_type` in `tests/helpers.py` for any new output format.
- Keep pull requests focused, and describe how you tested them.
