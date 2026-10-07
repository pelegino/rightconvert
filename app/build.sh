#!/bin/zsh
# Builds build/RightConvert.app: a background helper app that bundles rightconvert, plus the
# Finder extension that adds the "Convert" submenu. Signs with an Apple Development
# identity if one is available, otherwise ad-hoc. Override with SIGN_IDENTITY=<identity> or
# SIGN_IDENTITY=- (ad-hoc).

setopt err_exit

REPO=${0:A:h:h}
SRC="$REPO/app"
OUT="$REPO/build"
APP="$OUT/RightConvert.app"
EXT="$APP/Contents/PlugIns/ConvertFinderSync.appex"
SDK=$(xcrun --sdk macosx --show-sdk-path)
TARGET="$(uname -m)-apple-macos13.0"

rm -rf "$APP" "$OUT/icons"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" "$EXT/Contents/MacOS" "$EXT/Contents/Resources"

print "Rendering icons..."
swift "$SRC/icons/make-icons.swift" "$OUT/icons"
iconutil -c icns -o "$APP/Contents/Resources/AppIcon.icns" "$OUT/icons/AppIcon.iconset"
tiffutil -cathidpicheck "$OUT/icons/MenuIconTemplate.png" "$OUT/icons/MenuIconTemplate@2x.png" \
  -out "$EXT/Contents/Resources/MenuIconTemplate.tiff" >/dev/null

print "Compiling..."
xcrun swiftc -O -sdk "$SDK" -target "$TARGET" \
  -o "$APP/Contents/MacOS/RightConvert" "$SRC/Host/main.swift"
xcrun swiftc -O -sdk "$SDK" -target "$TARGET" -application-extension -parse-as-library \
  -module-name ConvertFinderSync -Xlinker -e -Xlinker _NSExtensionMain \
  -o "$EXT/Contents/MacOS/ConvertFinderSync" "$SRC/FinderSync/FinderSync.swift"

cp "$SRC/Host/Info.plist" "$APP/Contents/Info.plist"
cp "$SRC/FinderSync/Info.plist" "$EXT/Contents/Info.plist"
cp "$REPO/bin/rightconvert" "$APP/Contents/Resources/rightconvert"
chmod +x "$APP/Contents/Resources/rightconvert"

identity=${SIGN_IDENTITY-$(security find-identity -v -p codesigning 2>/dev/null | awk '/Apple Development/ { print $2; exit }')}
[[ $identity == - ]] && identity=""
print "Signing with ${identity:-ad-hoc identity}..."
codesign --force --timestamp=none --sign "${identity:--}" \
  --entitlements "$SRC/FinderSync/FinderSync.entitlements" "$EXT"
codesign --force --timestamp=none --sign "${identity:--}" "$APP"

print "Built $APP"
