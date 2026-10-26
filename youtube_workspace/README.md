# YouTube Production Workspace — Ronny Raj (Hindi)

A reusable, self-contained production environment for Hindi educational videos:
book summaries, self-improvement, productivity, psychology, motivation and
documentaries — plus YouTube Shorts cut from the long-form masters.

Everything here runs on **free, open-source, offline-verified** tooling. No paid
APIs, no stock subscriptions, no data leaving the machine.

| | |
|---|---|
| Workspace | `/home/user/Video-creation-/youtube_workspace` |
| Python env | `/home/user/Video-creation-/.venv` (repo-local, PEP 668 compliant) |
| Default output | 1920×1080 · 30 fps · H.264 · AAC 48 kHz · −14 LUFS |
| Shorts output | 1080×1920 · 30 fps · ≤ 58 s |
| Typography | Devanagari shaped with HarfBuzz (not Pillow's fallback) |
| Music / SFX | synthesised locally → royalty-free, safe to monetise |

---

## Quick start

```bash
PY=/home/user/Video-creation-/.venv/bin/python
cd /home/user/Video-creation-/youtube_workspace

$PY automation/check_env.py                                   # 1. verify setup
$PY automation/newproject.py --id book_atomic_habits \
      --type book_summary --title "Atomic Habits — पूरी समरी"  # 2. scaffold
$PY automation/projector.py build projects/book_atomic_habits/project.json --draft
$PY automation/projector.py build projects/book_atomic_habits/project.json
$PY automation/qc.py video rendered_videos/book_atomic_habits.mp4
```

## Folder map

```
youtube_workspace/
  research/          source notes and claim tables
  scripts/           finished Hindi scripts (+ copy inside each project)
  book_summaries/    book-specific research and summaries
  voiceovers/        raw narration takes before they enter a project
  music/             synthesised beds (gitignored, regenerate any time)
  sound_effects/     whoosh/pop/tick/thud/riser/sweep
  images/            reference photos and stills you supply
  generated_assets/  rendered frames per project (cache; gitignored)
  stock_footage/     clips you are licensed to use
  thumbnails/        finished 1280×720 thumbnails + mobile previews
  subtitles/         per-project hindi.srt and hindi.ass
  projects/          one folder per video: project.json, script, VO, manifest
  rendered_videos/   final MP4s (gitignored)
  shorts/            9:16 cuts (gitignored)
  templates/         scripts, briefs, checklists, example project files
  presets/           brand.json — colours, fonts, margins, encoder settings
  automation/        all Python tooling (see documentation/TOOLS.md)
  documentation/     audit, tool reference, workflow, resume guide
  quality_reports/   QC markdown + JSON
  assets/fonts/      OFL fonts + licences
```

## Installed tools (verified in this environment)

| Tool | Version | Role |
|---|---|---|
| FFmpeg (bundled via pip) | 7.0.2 static — libass, libx264, libfreetype, libfribidi, libmp3lame, libopus | encode, subtitles, loudness, mixing |
| PyAV | 18.1.0 | probing/decode without ffprobe |
| Pillow | 11.3.0 | compositing |
| uharfbuzz + freetype-py | 0.57.0 / 2.5.1 | correct Devanagari shaping + raster |
| fontTools | 4.67.0 | variable-font instancing |
| numpy / scipy | 2.4.6 / 1.17.1 | gradients, grain, FFT reverb |
| soundfile | 0.14.0 | WAV I/O |
| srt / pysubs2 | 3.5.3 / 1.8.1 | subtitles |
| moviepy | 2.2.1 | alternative editing backend |
| Python / Node / git / gh | 3.11.2 / 22.22.3 / 2.x / 2.23.0 | platform |

Fonts: Noto Sans Devanagari (OFL), Mukta (OFL), Poppins (OFL) — licences in
`assets/fonts/licenses/`.

## Templates available

| Template | Use |
|---|---|
| `script.longform.md` | general 8–15 min educational script |
| `script.book_summary.md` | book summaries with a copyright-safe structure |
| `script.self_improvement.md` | habits, productivity, discipline |
| `script.motivational_story.md` | 5-beat storytelling arc |
| `script.documentary.md` | chapters, sourcing discipline, 15–30 min |
| `script.shorts.md` | 20–58 s vertical scripts |
| `thumbnail_brief.md` | thumbnail design rules + JSON spec |
| `voiceover_script.md` | recording/TTS sheet with pronunciation guide |
| `qc_checklist.md` | automated + human pre-publish checklist |
| `project.example.json` | working 8-scene long-form project |
| `project.book_summary.json` | working book-summary project |
| `project.shorts.json` | working vertical project |

## Commands you will actually use

```bash
$PY automation/check_env.py                     # environment health
$PY automation/newproject.py ...                # new project from template
$PY automation/projector.py plan  <project>     # timings, audio flags
$PY automation/projector.py build <project> [--draft]
$PY automation/projector.py shorts <project> --count 3
$PY automation/vo.py import|split|normalize|check --project <project>
$PY automation/qc.py video|script|project|all <path>
$PY automation/seo.py pack <project> --topic "..." --out publish.md
$PY automation/thumbnail.py --spec <thumb.json> --out <png>
$PY automation/music.py bed --mood inspiring --seconds 120 --out music/bed.wav
```

Full reference: `documentation/TOOLS.md` · Process: `documentation/WORKFLOW.md`
· Audit and limits: `documentation/ENVIRONMENT_AUDIT.md` · New session: `documentation/RESUME.md`

## Known limitations

1. **No in-sandbox neural TTS.** Narration comes from Arena's speech tool or your mic.
   Cloud TTS endpoints and Hugging Face are unreachable from this sandbox.
2. **No ASR/Whisper.** Subtitles are generated from the script — more accurate for
   Hindi than small ASR models. If your recorded words differ, edit the script.
3. **No stock footage pipeline.** Visuals are typography-led cards (documentary style)
   plus stills you supply in `images/`. 100 % copyright-clean, not a B-roll montage.
4. **No HTML/CSS rendering** (no Chromium) — motion is zoom/pan/fade and card layout.
5. **2 vCPU:** plan ~1.5× real-time for the final 1080p encode.
6. **Publishing is manual** — the workspace prepares video, thumbnail, subtitles,
   title, description, tags and chapters; you upload.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError: av` | venv missing or wrong interpreter | recreate venv, `pip install -r requirements.txt`, use the `.venv` python |
| Subtitles show boxes/`□□□□` | libass did not find the Devanagari font | the mux call must pass `fontsdir` (already default); confirm `assets/fonts/NotoSansDevanagari-700.ttf` exists |
| Hindi text looks broken in an image | something used Pillow's `draw.text` | use `hinditext.HindiText` |
| `ffmpeg failed` | path with spaces/colons, or missing input | check the path; FFmpeg needs `:` escaped — `media.mux` already does this |
| Build says "no narration audio" | `voiceover/sNN.wav` missing | run `vo.py check`, then import or generate narration |
| Music too loud/quiet | per-project gain | edit `project.music.gain_db` (−26 is a good bed) |
| QC fails loudness | narration not normalised | `vo.py normalize`, then rebuild |
| Render very slow | 2 vCPU + 1080p | use `--draft` for iteration, final render once |
| `apt-get` fails | Debian mirrors blocked in this sandbox | don't use apt; pip wheels only |

## Reinstall (fresh machine / venv lost)

```bash
python3 -m venv /home/user/Video-creation-/.venv
/home/user/Video-creation-/.venv/bin/pip install -r \
  /home/user/Video-creation-/youtube_workspace/requirements.txt
cd /home/user/Video-creation-/youtube_workspace && \
  /home/user/Video-creation-/.venv/bin/python automation/check_env.py
```

Fonts live in `assets/fonts/` (in git). If they are ever lost, fetch them via the
GitHub API — see `documentation/RESUME.md` §"If the repository itself is gone".

## Rebuilding music and demo assets

```bash
$PY automation/music.py all-sfx --dir sound_effects
$PY automation/music.py bed --mood reflective --seconds 180 --out music/bed_reflective_long.wav
rm -rf generated_assets/* rendered_videos/* && $PY automation/projector.py build \
  projects/demo_productivity/project.json
```

## Proven output

`rendered_videos/demo_productivity.mp4` — 79.8 s, 1920×1080, 30 fps, H.264/AAC,
8 scenes, Devanagari typography, burned-in Hindi captions, synthesised music bed with
ducking. Built from `projects/demo_productivity/project.json` in 131 s.
This demo has **no narration by design** (audio is silent) — it verifies structure,
typography, timing and encoding. A narrated build additionally requires the
voice-over step.
