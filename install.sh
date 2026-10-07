#!/bin/zsh
# Installs the conversion engines, the Convert app with its Finder extension, and the rightconvert CLI.
#
#   ./install.sh                     install everything, ask about LibreOffice
#   ./install.sh --with-libreoffice  install LibreOffice without asking
#   ./install.sh --no-libreoffice    skip LibreOffice
#   ./install.sh --skip-deps         only rebuild and reinstall the app and CLI

setopt err_exit

REPO=${0:A:h}
APP_DST="$HOME/Applications/RightConvert.app"
EXT_ID="com.rightconvert.Convert.FinderSync"
LINK_DIR="$HOME/.local/bin"
MATRIX="$HOME/Library/Application Support/rightconvert/matrix.txt"
LSREGISTER=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister

libreoffice=ask
skip_deps=0
for arg; do
  case $arg in
    --with-libreoffice) libreoffice=yes ;;
    --no-libreoffice) libreoffice=no ;;
    --skip-deps) skip_deps=1 ;;
    *) print -u2 "Unknown option: $arg"; exit 2 ;;
  esac
done

export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

if (( ! skip_deps )); then
  if ! command -v brew >/dev/null; then
    print -u2 "Homebrew is required. Install it from https://brew.sh and run this script again."
    exit 1
  fi

  print "Installing ffmpeg, ImageMagick, libheif, poppler and pandoc..."
  brew install ffmpeg imagemagick libheif poppler pandoc

  if [[ -d /Applications/LibreOffice.app ]]; then
    print "LibreOffice is already installed."
  else
    if [[ $libreoffice == ask ]]; then
      print "LibreOffice (about 1 GB) enables Word/Excel/PowerPoint conversions and anything-to-PDF for documents."
      read -q "reply?Install LibreOffice? [y/N] " && libreoffice=yes || libreoffice=no
      print
    fi
    if [[ $libreoffice == yes ]]; then
      brew install --cask libreoffice
    else
      print "Skipping LibreOffice. Office formats will be hidden from the Convert menu."
    fi
  fi
fi

if ! xcrun --find swiftc >/dev/null 2>&1; then
  print -u2 "Xcode or the Command Line Tools are required to build the Finder extension (xcode-select --install)."
  exit 1
fi
"$REPO/app/build.sh"

# Replaced by the Finder extension.
if [[ -d $HOME/Library/Services/Convert.workflow ]]; then
  rm -rf "$HOME/Library/Services/Convert.workflow"
  /System/Library/CoreServices/pbs -flush >/dev/null 2>&1 || true
  print "Removed the old Convert... Quick Action."
fi

pluginkit -r "$APP_DST/Contents/PlugIns/ConvertFinderSync.appex" 2>/dev/null || true
mkdir -p "${APP_DST:h}"
rm -rf "$APP_DST"
cp -R "$REPO/build/RightConvert.app" "$APP_DST"
"$LSREGISTER" -f "$APP_DST"
pluginkit -a "$APP_DST/Contents/PlugIns/ConvertFinderSync.appex"
pluginkit -e use -i "$EXT_ID"
print "Installed $APP_DST and enabled its Finder extension."

mkdir -p "${MATRIX:h}"
"$APP_DST/Contents/Resources/rightconvert" --matrix >"$MATRIX"
# Shared secret the Finder extension attaches to its requests; see app/Host/main.swift.
TOKEN="${MATRIX:h}/token"
if [[ ! -s $TOKEN ]]; then
  (umask 077 && openssl rand -hex 32 >"$TOKEN")
fi

mkdir -p "$LINK_DIR"
ln -sf "$APP_DST/Contents/Resources/rightconvert" "$LINK_DIR/rightconvert"
print "Linked $LINK_DIR/rightconvert"
if [[ :$PATH: != *:$LINK_DIR:* ]]; then
  print "Note: add $LINK_DIR to your PATH to use 'rightconvert' from the terminal."
fi

print
print "Done. Right-click any file in Finder and hover Convert to pick a format."
print "If Convert doesn't appear, open System Settings > General > Login Items & Extensions,"
print "click the info button next to Finder, and turn on RightConvert. Then run: killall Finder"
print "After installing new engines (like LibreOffice), run ./install.sh --skip-deps to refresh the menu."
