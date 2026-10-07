# Contributing

Thanks for helping out. Bug reports, new formats, and fixes are all welcome.

## Setup

You need macOS 13 or later, Homebrew, and Xcode or the Xcode Command Line Tools.

```sh
./install.sh            # installs engines, builds and installs the app
tests/run.sh            # every conversion path your installed engines support, plus edge cases
tests/quality.sh        # fidelity guarantees: bit-exact lossless output, stream copies, SSIM/PSNR floors
```

An Apple developer certificate isn't required. Without one, `app/build.sh` signs ad-hoc, which Finder accepts for local builds.

After changing `bin/rightconvert`, run `./install.sh --skip-deps` so the installed app bundles the new copy.

## Where things live

- `bin/rightconvert` does all conversions. The format table is at the top: `CATEGORY` maps extensions to a kind of file, and `TARGETS` lists what each kind can become. `engine_for` picks the tool for a conversion.
- `app/FinderSync/FinderSync.swift` builds the right-click menu from the table that `rightconvert --matrix` writes.
- `app/Host/main.swift` is the helper app that runs conversions for the sandboxed extension.

Menu labels are generated in two places, `label_for` in `bin/rightconvert` and `label(category:format:)` in `FinderSync.swift`. Keep them in sync.

## Guidelines

- Everything must run locally. Don't add network calls or cloud services.
- Don't lower quality. Lossless targets must stay bit-exact, and a container change must copy streams rather than re-encode. `tests/quality.sh` enforces this, so add a check there when you add a format.
- Add a fixture and an expected MIME type to `tests/run.sh` for any new format.
- Keep pull requests focused, and describe how you tested them.
