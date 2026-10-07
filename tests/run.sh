#!/bin/zsh
# Generates sample files, converts each one to every format its installed engines support,
# and checks that each output exists and has the expected file type.

setopt null_glob
export PATH="/opt/homebrew/bin:/usr/local/bin:/Applications/LibreOffice.app/Contents/MacOS:$PATH"

CLI=${0:A:h:h}/bin/rightconvert
WORK=${$(mktemp -d -t rightconvert-test):A}
pass=0 fail=0

ok() { print -r -- "  ok    $1"; (( pass++ )) }
bad() { print -r -- "  FAIL  $1"; (( fail++ )) }

typeset -A MIME
MIME=(
  jpg jpeg  png png  webp webp  heic 'hei[cf]'  avif avif  tiff tiff  gif gif  bmp bmp  ico icon
  pdf pdf  mp4 mp4  mov quicktime  mkv matroska  webm webm
  mp3 mpeg  m4a '(mp4|m4a)'  wav wav  flac flac  ogg ogg  opus ogg  aiff aiff
  docx '(wordprocessingml|zip)'  odt '(opendocument.text|zip)'  doc '(msword|CDFV2)'
  rtf rtf  txt text  md text  html html
  xlsx '(spreadsheetml|zip)'  ods '(opendocument.spreadsheet|zip)'  xls '(excel|CDFV2)'  csv text
  pptx '(presentationml|zip)'  odp '(opendocument.presentation|zip)'  ppt '(powerpoint|CDFV2)'
)

check_output() {  # check_output TARGET PATH
  local t=${1%-small} out=$2
  if [[ -d $out ]]; then
    local -a pages=("$out"/page*.$t)
    (( ${#pages} )) && [[ $(file -b --mime-type "$pages[1]") =~ ${MIME[$t]} ]]
  else
    [[ -s $out && $(file -b --mime-type "$out") =~ ${MIME[$t]} ]]
  fi
}

print "Generating fixtures in $WORK"
cd "$WORK"
ffmpeg -loglevel error -f lavfi -i sine=frequency=440:duration=1 audio.wav
ffmpeg -loglevel error -f lavfi -i testsrc=duration=1:size=321x241:rate=10 \
  -f lavfi -i sine=duration=1 -shortest -c:v mjpeg video.mov
ffmpeg -loglevel error -f lavfi -i testsrc=size=64x48 -frames:v 1 image.png
print -r -- $'Plain text line one.\nLine two.' > plain.txt
print -r -- $'# Notes\n\nSome *markdown* with a [link](https://example.com).\n\n- one\n- two' > notes.md
print -r -- '<html><body><h1>Page</h1><p>Hello <b>world</b>.</p></body></html>' > page.html
textutil -convert rtf -output letter.rtf plain.txt
textutil -convert docx -output report.docx page.html
print -r -- $'name,qty\napple,3\npear,5' > table.csv
cupsfilter plain.txt > document.pdf 2>/dev/null || rm -f document.pdf

for fixture in audio.wav video.mov image.png document.pdf plain.txt notes.md page.html letter.rtf report.docx table.csv; do
  [[ -s $fixture ]] || { print "Skipping $fixture (could not generate)"; continue }
  local -a targets=($("$CLI" --list "$fixture"))
  print "$fixture -> ${targets:-(no engines installed)}"
  for t in $targets; do
    out=$("$CLI" --to $t "$fixture" 2>/dev/null | tail -1)
    if [[ -n $out ]] && check_output $t "$out"; then ok "$fixture -> $t"
    else bad "$fixture -> $t (${out:-no output})"
    fi
  done
done

print "Behavior"
first=$("$CLI" --to mp3 audio.wav)
second=$("$CLI" --to mp3 audio.wav)
[[ $first != $second && -s $second ]] && ok "never overwrites (${second:t})" || bad "never overwrites"

mkdir folder && cp audio.wav folder/a.wav && cp audio.wav folder/.hidden.wav
"$CLI" --to flac folder >/dev/null
[[ -s folder/a.flac && ! -e folder/.hidden.flac ]] && ok "expands folders, ignores hidden files" || bad "folder expansion"

cp audio.wav mixed.wav
out=$("$CLI" --to mp3 mixed.wav video.mov)
[[ $(print -r -- $out | wc -l | tr -d ' ') == 2 ]] && ok "audio + video share audio targets" || bad "mixed audio/video"

"$CLI" --to mp3 audio.wav image.png 2>/dev/null && bad "rejects incompatible mix" || ok "rejects incompatible mix"
matrix=$("$CLI" --matrix)
[[ $(print -r -- $matrix | grep '^jpeg ') == "jpeg jpg image $("$CLI" --list x.jpeg | tr '\n' ' ' | sed 's/ $//')" ]] \
  && ok "--matrix matches --list (Finder menu table)" || bad "--matrix matches --list"

print "Edge cases"
for name in "with spaces.png" "quote's \"double\".png" "a&b=c+d#1%.png" "émoji 🎉 שלום.png" "-leading-dash.png" "UPPER.PNG" "photo.jpeg"; do
  cp image.png "$name"
  out=$("$CLI" --to webp -- "$WORK/$name" 2>/dev/null)
  [[ -s $out && $out == "$WORK/${name:r}.webp" ]] && ok "file name: $name" || bad "file name: $name (${out:-no output})"
done

out=$("$CLI" --to webp-small image.png)
[[ $out == */image-*.webp || $out == */image.webp ]] && check_output webp "$out" && ok "smaller-file variant writes a .webp" || bad "smaller-file variant"
[[ $("$CLI" --list image.png | grep -c -- -small) == 3 ]] && ok "--list offers webp/heic/avif smaller variants" || bad "--list smaller variants"
[[ -z $("$CLI" --list audio.wav | grep -- -small) ]] && ok "no smaller variants for audio" || bad "smaller variants leak into audio"

mkdir locked && cp audio.wav locked/ && chmod a-w locked
"$CLI" --to mp3 locked/audio.wav >/dev/null 2>&1 && bad "read-only folder reports failure" || ok "read-only folder reports failure"
[[ -z $(print locked/*.mp3) ]] && ok "no partial output left behind" || bad "partial output left behind"
chmod u+w locked

"$CLI" --to >/dev/null 2>&1; [[ $? == 2 ]] && ok "--to without a format exits 2" || bad "--to without a format"
"$CLI" --bogus x 2>/dev/null; [[ $? == 2 ]] && ok "unknown option exits 2" || bad "unknown option"
"$CLI" --to mp3 /nonexistent/file.wav 2>/dev/null && bad "missing file reports failure" || ok "missing file reports failure"

print x > thing.xyz
"$CLI" --to mp3 thing.xyz 2>/dev/null && bad "rejects unsupported type" || ok "rejects unsupported type"

print
print "$pass passed, $fail failed"
(( fail )) && print "Outputs kept in $WORK; details in ~/Library/Logs/rightconvert.log" || rm -rf "$WORK"
(( fail == 0 ))
