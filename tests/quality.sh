#!/bin/zsh
# Measures conversion fidelity. Lossless targets must be bit-exact; lossy targets must clear
# a "visually/audibly transparent" bar; container changes must copy streams untouched.

setopt null_glob
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"

CLI=${0:A:h:h}/bin/rightconvert
WORK=$(mktemp -d -t rightconvert-quality)
pass=0 fail=0

check() {  # check DESCRIPTION DETAIL CONDITION...
  local desc=$1 detail=$2; shift 2
  if "$@"; then print -r -- "  ok    $desc ($detail)"; (( pass++ ))
  else print -r -- "  FAIL  $desc ($detail)"; (( fail++ ))
  fi
}

pixels_diff() { magick compare -metric AE "$1" "$2" null: 2>&1 | cut -d' ' -f1 }
psnr() { magick compare -metric PSNR "$1" "$2" null: 2>&1 | cut -d' ' -f1 }
pcm_md5() { ffmpeg -v error -i "$1" -map 0:a:0 -c:a pcm_s32le -f md5 - }
stream_md5() { ffmpeg -v error -i "$1" -map 0:$2:0 -c copy -f md5 - }
probe() { ffprobe -v error -select_streams $2 -show_entries stream=$3 -of default=nw=1:nk=1 "$1" | head -n1 }
ssim() {  # ssim OUTPUT REFERENCE: mean SSIM over all frames, reference cropped to the output size
  local size=$(ffprobe -v error -select_streams v:0 -show_entries stream=width,height -of csv=s=x:p=0 "$1")
  # Pair frames by index: containers round timestamps differently (WebM uses milliseconds).
  ffmpeg -nostdin -i "$1" -i "$2" -lavfi \
    "[0:v]settb=1/30,setpts=N[out];[1:v]crop=${size/x/:}:0:0,settb=1/30,setpts=N[ref];[out][ref]ssim" -f null - 2>&1 \
    | sed -n 's/.*All:\([0-9.]*\).*/\1/p'
}
gte() { (( $1 >= $2 )) }

cd "$WORK"
print "Generating fixtures in $WORK"
ffmpeg -loglevel error -f lavfi -i testsrc2=size=1280x720 -frames:v 1 photo.png
ffmpeg -loglevel error -f lavfi -i "anoisesrc=d=3:c=pink:r=96000:a=0.5" -c:a pcm_s24le studio.wav
ffmpeg -loglevel error -f lavfi -i "sine=f=440:d=3:r=44100" -c:a pcm_s16le cd.wav
ffmpeg -loglevel error -f lavfi -i testsrc2=d=3:size=1280x720:rate=30 -f lavfi -i sine=d=3 -shortest \
  -c:v libx264 -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k clip.mp4
ffmpeg -loglevel error -f lavfi -i testsrc2=d=2:size=1280x720:rate=30 \
  -c:v libx265 -pix_fmt yuv420p10le -x265-params log-level=error -tag:v hvc1 hdr.mov
ffmpeg -loglevel error -f lavfi -i testsrc2=d=2:size=641x361:rate=30 -c:v mjpeg -q:v 2 odd.avi
print "Quality test page" > page.txt
cupsfilter page.txt > page.pdf 2>/dev/null

print "Images: lossless targets must be pixel-identical"
for t in png tiff bmp webp heic avif; do
  [[ $t == png ]] && { cp photo.png src.tiff; src=src.tiff } || src=photo.png
  out=$("$CLI" --to $t $src 2>/dev/null)
  d=$(pixels_diff photo.png "$out")
  check "photo -> ${(U)t}" "$d pixels differ" [ "$d" = 0 ]
done
out=$("$CLI" --to jpg photo.png)
p=$(psnr photo.png "$out")
check "photo -> JPG (lossy format)" "PSNR ${p} dB, 4:4:4 chroma" gte ${p%.*} 45

print "Images: smaller-file variants must shrink a JPEG photo and stay above 40 dB PSNR"
magick -seed 7 -size 1920x1080 plasma:fractal -blur 0x1.2 -quality 92 scenery.jpg
for t in webp heic avif; do
  out=$("$CLI" --to $t-small scenery.jpg)
  p=$(psnr scenery.jpg "$out")
  size=$(stat -f %z "$out") source=$(stat -f %z scenery.jpg)
  check "JPG -> ${(U)t} (smaller file)" "$(( size / 1024 )) KB vs $(( source / 1024 )) KB source, PSNR ${p} dB" \
    eval '(( size < source && ${p%.*} >= 40 ))'
done

print "Audio: lossless targets must be sample-identical and keep bit depth"
ref=$(pcm_md5 studio.wav)
for t in flac aiff m4a; do
  out=$("$CLI" --to $t studio.wav)
  check "24-bit/96 kHz WAV -> ${(U)t}" "$(probe "$out" a:0 codec_name), $(probe "$out" a:0 bits_per_raw_sample)-bit, $(probe "$out" a:0 sample_rate) Hz" \
    [ "$(pcm_md5 "$out")" = "$ref" ]
done
flac=$("$CLI" --to flac cd.wav)
back=$("$CLI" --to wav "$flac")
check "16-bit WAV -> FLAC -> WAV round trip" "$(probe "$back" a:0 codec_name)" [ "$(pcm_md5 "$back")" = "$(pcm_md5 cd.wav)" ]
out=$("$CLI" --to mp3 studio.wav)
check "WAV -> MP3 (lossy format)" "$(( $(probe "$out" a:0 bit_rate) / 1000 )) kbps" [ "$(probe "$out" a:0 bit_rate)" = 320000 ]
out=$("$CLI" --to m4a clip.mp4)
check "MP4 -> M4A extracts AAC without re-encoding" "audio copied" [ "$(stream_md5 "$out" a)" = "$(stream_md5 clip.mp4 a)" ]

print "Video: container changes must copy streams untouched"
for t in mov mkv; do
  out=$("$CLI" --to $t clip.mp4)
  check "H.264 MP4 -> ${(U)t}" "video and audio copied" \
    [ "$(stream_md5 "$out" v)$(stream_md5 "$out" a)" = "$(stream_md5 clip.mp4 v)$(stream_md5 clip.mp4 a)" ]
done
out=$("$CLI" --to mp4 hdr.mov)
check "10-bit HEVC MOV -> MP4" "copied, tag $(ffprobe -v error -select_streams v:0 -show_entries stream=codec_tag_string -of csv=p=0 "$out")" \
  [ "$(stream_md5 "$out" v)" = "$(stream_md5 hdr.mov v)" ]
out=$("$CLI" --to webm hdr.mov)
check "10-bit HEVC -> WebM stays 10-bit" "$(probe "$out" v:0 pix_fmt)" [ "$(probe "$out" v:0 pix_fmt)" = yuv420p10le ]

print "Video: required re-encodes must be visually lossless (SSIM >= 0.99)"
out=$("$CLI" --to mp4 odd.avi)
s=$(ssim "$out" odd.avi)
check "MJPEG AVI 641x361 -> MP4" "SSIM $s, $(probe "$out" v:0 width)x$(probe "$out" v:0 height), cropped not scaled" gte ${s:-0} 0.99
out=$("$CLI" --to webm clip.mp4)
s=$(ssim "$out" clip.mp4)
check "H.264 MP4 -> WebM (VP9)" "SSIM $s" gte ${s:-0} 0.99

if [[ -s page.pdf ]]; then
  print "PDF"
  out=$("$CLI" --to png page.pdf)
  pages=("$out"/*.png)
  check "PDF -> PNG renders at 300 dpi" "$(magick identify -format '%wx%h' "$pages[1]") px" \
    gte $(magick identify -format '%w' "$pages[1]") 2400
fi

print
print "$pass passed, $fail failed"
(( fail )) && print "Outputs kept in $WORK; details in ~/Library/Logs/rightconvert.log" || rm -rf "$WORK"
(( fail == 0 ))
