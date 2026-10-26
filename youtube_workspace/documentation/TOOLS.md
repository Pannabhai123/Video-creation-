# Tool reference — every command, what it does, when to use it

All commands assume:

```bash
cd /home/user/Video-creation-/youtube_workspace
PY=/home/user/Video-creation-/.venv/bin/python
```

| Module | One-line purpose |
|---|---|
| `bootstrap.sh` | rebuild venv + folders + verify, in one command |
| `automation/check_env.py` | verify the environment is intact |
| `automation/newproject.py` | scaffold a new video project from a template |
| `automation/hinditext.py` | correct Devanagari text → PNG (HarfBuzz + FreeType) |
| `automation/visuals.py` | 1080p scene frames: title, section, bullets, stat, quote, split, image |
| `automation/thumbnail.py` | 1280×720 thumbnails + 168 px mobile check |
| `automation/music.py` | synthesise royalty-free music beds and SFX |
| `automation/imagetovideo.py` | still images -> cinematic clips (zoom/pan, transitions, Hindi text) |
| `automation/media.py` | FFmpeg/PyAV layer: probe, encode, mix, loudness, concat, shorts |
| `automation/captions.py` | script → timed `.srt` + styled `.ass` |
| `automation/projector.py` | timeline → finished video, plus Shorts cutting |
| `automation/vo.py` | import / split / normalise / check narration audio |
| `automation/qc.py` | automated pre-publish QC with a markdown report |
| `automation/seo.py` | titles, description, chapters, tags, Shorts ideas |

---

## bootstrap.sh

```bash
bash youtube_workspace/bootstrap.sh          # venv + packages + folders + verify
bash youtube_workspace/bootstrap.sh --test   # also run the 16 pipeline tests
bash youtube_workspace/bootstrap.sh --force  # delete and recreate the venv
```
Idempotent and safe to run every session; it skips work that is already done.

## check_env.py

```bash
$PY automation/check_env.py            # human summary
$PY automation/check_env.py --json     # machine-readable
$PY automation/check_env.py --strict   # exit 1 on any problem (use in CI)
```
Checks Python deps, the bundled FFmpeg build and its codec features, all workspace
folders, all fonts, and runs a **live Devanagari shaping test** (कर्म vs करम width).

## newproject.py

```bash
$PY automation/newproject.py --id book_ikigai --type book_summary \
   --title "Ikigai — जीने का तरीका" --mood calm --scenes 9
```
Types: `longform`, `book_summary`, `self_improvement`, `motivational`, `documentary`, `shorts`.
Creates `projects/<id>/{project.json,script.md,research.md,thumb.json,voiceover/}`.

## hinditext.py — Devanagari typography

```python
from hinditext import HindiText
t = HindiText("display", 84)          # Mukta ExtraBold at 84 px
img = t.render("कर्म और ज्ञान", max_width=900, align="center",
               color="#FFFFFF", stroke=6, stroke_color="#0A0A0A",
               shadow=(0, 8, 16))
w, h, lines = t.measure("कुछ टेक्स्ट", max_width=600)
```

Font keys: `deva-regular`, `deva-medium`, `deva-bold`, `deva-black`, `display`,
`display-bold`, `display-regular`, `latin-bold`, `latin-semibold` (or an absolute path).

Why not Pillow's own `ImageDraw.text`: this build has **no libraqm**, so matras and
conjuncts break. Verified: `कर्म` shapes to 71 px here versus 92 px for `करम`.

## visuals.py — scene frames

```python
import visuals
visuals.title_card("शुरुआत क्यों नहीं होती?", "2 मिनट का नियम", "PRODUCTIVITY")
visuals.bullet_card("दिमाग़ क्यों टालता है?", ["कारण 1", "कारण 2", "कारण 3"])
visuals.section_card(1, "नियम", "THE RULE")
visuals.stat_card("2 मिनट", "शुरुआत का दरवाज़ा", "Atomic Habits")
visuals.quote_card("शुरुआत छोटी रखिए।", "लेखक")
visuals.split_card("पहले बनाम बाद में", image_path="images/x.png", points=["...", "..."])
visuals.image_scene("images/photo.jpg", "शीर्षक", "उपशीर्षक")
visuals.render_scene(spec_dict, "out.png", size=(1920, 1080))   # used by the pipeline
```
Colours and margins come from `presets/brand.json` — change the brand once, every
frame and thumbnail follows.

## thumbnail.py

```bash
$PY automation/thumbnail.py --spec projects/<id>/thumb.json --out thumbnails/<id>.png
$PY automation/thumbnail.py --demo --out thumbnails     # built-in examples + mobile previews
```
Auto-shrinks the headline until it fits 3 lines, always ≥ 62 px, thick outline,
left accent bar, badge chip, optional subject photo with feathered blend.

## music.py

```bash
$PY automation/music.py bed --mood inspiring --seconds 120 --out music/bed.wav
$PY automation/music.py sfx --kind whoosh --out sound_effects/whoosh.wav
$PY automation/music.py all-sfx --dir sound_effects
```
Moods: `calm`, `reflective`, `inspiring`, `tense`, `upbeat`. SFX: `whoosh`, `pop`,
`tick`, `thud`, `riser`, `sweep`. Output is 48 kHz stereo WAV, fades included.
All synthesised here → no attribution needed, safe to monetise.

## imagetovideo.py — stills to video

```bash
# one image -> one clip
$PY automation/imagetovideo.py --image images/photo.jpg --out clips/one.mp4 \
    --size 16:9 --duration 6 --motion kenburns --music reflective \
    --headline "शीर्षक" --sub "उपशीर्षक"

# several images, transitions, captions, music -> finished video
$PY automation/imagetovideo.py --spec projects/<id>/spec.json --out rendered_videos/<id>.mp4 --json

# vertical Short from a landscape photo (whole image kept, blurred sides)
$PY automation/imagetovideo.py --image images/photo.jpg --out shorts/s1.mp4 \
    --size 9:16 --fit blurpad --duration 8 --motion zoom_in
```

Motion values: `zoom_in`, `zoom_out`, `pan_left`, `pan_right`, `diagonal`,
`parallax`, `kenburns` (random but seeded — same seed, same result), `static`.
Sizes: `16:9`, `9:16`, `1:1`, `4:5`, or `WxH`. `--fit cover` crops to fill;
`--fit blurpad` keeps the entire photo and fills the sides with a blurred copy.
Transitions (spec only): `fade`, `smoothleft`, `smoothright`, `circleopen`,
`wipeleft`, `dissolve`.

**What it does not do:** it does not invent new motion with an AI video model
(that needs GPU model weights this sandbox cannot download). It is the
documentary technique — camera movement over a still — which is what makes a
photo read as footage.

## media.py

```python
import media
media.probe("in.mp4").to_dict()          # duration/size/fps/codecs (no ffprobe needed)
media.loudness_normalise("in.wav", "out.wav")    # two-pass EBU R128 → -14 LUFS
media.mix("vo.wav", "bed.wav", "mix.wav", music_gain_db=-26)  # ducking included
media.still_to_video("frame.png", "clip.mp4", 11.7, motion="zoom_in")
media.concat_videos([...], "picture.mp4")
media.mux("picture.mp4", "mix.wav", "final.mp4", subs="hi.ass", burn_subs=True)
media.make_short_vertical("final.mp4", "short.mp4", 12.0, 60.0)
media.black_frames("final.mp4")          # QC helper
```

## captions.py

```python
import captions
captions.build_for_scenes(scene_list, "subtitles/<id>", scene_audio=vo_map)
# → subtitles/<id>/hindi.srt  (upload), hindi.ass (burn-in), cue stats report
```
Rules: ≤ 38 chars/line, ≤ 2 lines, ≤ 16 chars/sec, cues snapped to detected pauses.

## projector.py — the main builder

```bash
$PY automation/projector.py plan   projects/<id>/project.json    # timings only
$PY automation/projector.py frames projects/<id>/project.json    # frames only
$PY automation/projector.py build  projects/<id>/project.json --draft
$PY automation/projector.py build  projects/<id>/project.json
$PY automation/projector.py shorts projects/<id>/project.json --count 3
```
Timing logic: real narration audio if present → else calibrated estimate
(13.5 Devanagari chars/sec + 0.45 s breath). Scene audio lives in
`projects/<id>/voiceover/sNN.wav`; the build re-times itself automatically.
Writes `projects/<id>/build_manifest.json` with every path and timestamp.

## vo.py — narration intake

```bash
$PY automation/vo.py import    --project projects/<id>/project.json --src ~/Downloads/vo
$PY automation/vo.py split     --project projects/<id>/project.json --file ~/take.m4a
$PY automation/vo.py normalize --project projects/<id>/project.json
$PY automation/vo.py check     --project projects/<id>/project.json
```
`import` converts any format to 48 kHz WAV, trims head/tail silence, and names files
`sNN.wav`. `split` cuts one long take at its N−1 longest pauses. `normalize` puts
every scene at −16 LUFS so the edit has no level jumps.

## qc.py

```bash
$PY automation/qc.py video   rendered_videos/<id>.mp4
$PY automation/qc.py script  scripts/<id>.md
$PY automation/qc.py project projects/<id>/project.json
$PY automation/qc.py all     projects/<id>/build_manifest.json
```
Writes `quality_reports/qc_*.md` and `.json`. Video checks: resolution, aspect,
fps, codecs, sample rate, full decode integrity, loudness/true peak, black runs,
frozen picture, subtitle presence. Script checks: double spaces, repeated words,
stock filler, over-long sentences, English ratio, Devanagari presence, speaking-time
estimate. Exit code 2 if anything FAILs.

## seo.py

```bash
$PY automation/seo.py pack projects/<id>/project.json --topic "Atomic Habits" \
   --angle "6 आदतें" --summary "..." --source "James Clear (2018)" \
   --tag "atomic habits summary hindi" --out projects/<id>/publish.md
```
Produces title options with character counts and a mobile-truncation flag, a
description with chapters from real scene timings, a keyword list inside YouTube's
500-character tag budget, hashtags, Shorts ideas, and an upload checklist.
