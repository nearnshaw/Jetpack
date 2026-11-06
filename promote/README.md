# Marketplace video — Retro Rocket Jetpack

Made with the promote-scene skill's video workflow (decentraland/sdk-skills PR #129). `promote` is in `.dclignore`, so nothing here goes into `smart-wearable.zip`.

## Videos

| File | Use | Length | Sources |
| --- | --- | --- | --- |
| `videos/jetpack-marketplace.mp4` | Builder → smart wearable video (`.mp4`, max 250 MB) | 20.3 s, 1920×1080, 30 fps, H.264 + AAC, ~33 MB | Explorer recording + Blender turntable |

Edit: launching off a roof and flying over the lattice building (14.2–22.7 s of the recording), the liftoff up the white building (8.2–11.4 s, the clearest flames), a 360° turntable of the suit, then an end card. The captions quote `wearable.json`'s description word for word. "Nearby players see the flames too" comes from the README: the flames are emote props.

- **Footage:** `footage/jetpack-flight.mp4` is the first 30 s of `~/Downloads/jetpack.mov` (1104×792, 75 fps). It is cropped to the centre 16:9 and scaled to 1920×1080 at 30 fps. The recording's glider section (36–47 s) is the Explorer's own glide feature, not the wearable, so it is left out.
- **Turntable:** `clips/turntable.mp4` is made from `tools/turntable.py`, a Workbench render of `blender/out/jetpack_suit_male.blend` laid over `images/backdrop.png`. `logo/jetpack_hero.png` is the end-card still.
- **Music:** `music/jetpack_theme.wav` is an original 112.5 BPM synthwave cue synthesised by `tools/make_music.py`, with no samples and nothing downloaded, so there is nothing to license. The cuts land on its beats (0, 6, 12, 16, 22, 32 of 38). The lead enters on the close rise, and a riser leads into the end card. To use a licensed track instead, drop it in `music/` and change `music.file` in the edit.
- **Thrust sound:** the wearable's own loop (`assets/sounds/jetpack_thrust.mp3`), cut to `music/thrust_*.mp3`. It sits under the music where the flames show.

## Re-render

```bash
B=/Applications/Blender.app/Contents/MacOS/Blender
F=/tmp/jetpack-turntable    # frames dir, anywhere
$B -b blender/out/jetpack_suit_male.blend -P promote/tools/turntable.py -- turntable $F
$B -b blender/out/jetpack_suit_male.blend -P promote/tools/turntable.py -- hero promote/logo/jetpack_hero.png   # then crop to its alpha bbox
ffmpeg -y -loop 1 -framerate 30 -i promote/images/backdrop.png -framerate 30 -i "$F/f%04d.png" \
  -filter_complex "[0][1]overlay=shortest=1,format=yuv420p" -c:v libx264 -crf 14 promote/clips/turntable.mp4

python3 promote/tools/make_music.py promote/music/jetpack_theme.wav

cd promote/video && npm install      # node_modules can be deleted any time
npx remotion studio                  # scrub and adjust timings live
npx remotion render marketplace ../videos/jetpack-marketplace.mp4 --crf=16
```

Shot times, cards and sounds are in `video/src/edits.ts` (edit `marketplace`). Times are in seconds; `trimStart` is the second in `footage/jetpack-flight.mp4`.
