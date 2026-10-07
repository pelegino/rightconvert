#!/bin/zsh
# Removes the Convert app, its Finder extension, and the rightconvert link. Homebrew packages are left installed.

app="$HOME/Applications/RightConvert.app"
pluginkit -e ignore -i com.rightconvert.Convert.FinderSync 2>/dev/null
pluginkit -r "$app/Contents/PlugIns/ConvertFinderSync.appex" 2>/dev/null
rm -rf "$app" "$HOME/Library/Application Support/rightconvert" "$HOME/Library/Services/Convert.workflow"
link="$HOME/.local/bin/rightconvert"
[[ -L $link ]] && rm "$link"
/System/Library/CoreServices/pbs -flush >/dev/null 2>&1 || true
print "Removed RightConvert.app, its Finder extension, and $link."
print "Engines installed with Homebrew were kept. Remove them with: brew uninstall ffmpeg imagemagick poppler pandoc"
