# Production workflow — topic in, publishable package out

The pipeline is deliberately split so that **your judgement** (research, script,
angle) stays with you and me, while **repeatable work** (frames, timing, subtitles,
QC, SEO) is automated.

```
topic
  │
  ├─ 1. RESEARCH ........... research.md + verified source table
  ├─ 2. STRATEGY .......... project header: audience, promise, angle, duration
  ├─ 3. SCRIPT ............ script.md (Hindi, scene-wise, spoken-ready)
  ├─ 4. FACT-CHECK ........ every number/claim in research.md marked verified
  ├─ 5. VISUAL PLAN ....... project.json scenes (type + text + motion + sfx)
  ├─ 6. VOICE-OVER ........ projects/<id>/voiceover/sNN.wav
  ├─ 7. ASSEMBLY .......... rendered_videos/<id>.mp4
  ├─ 8. SUBTITLES ......... subtitles/<id>/hindi.srt (+ burned .ass)
  ├─ 9. THUMBNAIL ......... thumbnails/<id>.png
  ├─ 10. QC ............... quality_reports/qc_*.md  → fix → re-render
  └─ 11. PUBLISH PACK ..... publish.md (titles, description, tags, chapters, shorts)
```

## Stage detail

### 1. Research
- Write claims into `projects/<id>/research.md` as a table: claim · source · confidence.
- Rule: no number, date, name, or quotation enters the script unless it is in that table.
- Book summaries: main thesis, three ideas, the weakest part of the book, who it is not for.
- Never reproduce long passages. One short quotation maximum, with credit.

### 2. Strategy (project header)
Filled once, drives everything downstream:
`audience`, `promise` (what the viewer can do afterwards), `angle` (why this video
is not redundant), `format` (longform/short), `preset`, `music.mood`.

### 3. Script
Templates per category in `templates/`. Targets:
- longform 8–15 min → 6,500–12,000 Devanagari characters
- book summary 10–14 min → ~8,000–11,000
- short 30–55 s → 90–130 words

### 4. Fact-check
- Re-read every sentence containing a digit, a name, a date, or "सबसे" / "सिर्फ़" / "पहला".
- Disputed claims: two sources, or say "इस पर मतभेद है".
- Own opinion must be visibly opinion ("मेरी राय में").

### 5. Visual plan → `project.json`
Each scene: `id`, `narration`, `visual`, `motion`, `sfx`.
Visual types: `title`, `section`, `bullets`, `stat`, `quote`, `split`, `image`.
Motion: `zoom_in`, `zoom_out`, `pan_left`, `pan_right`, `static`.
Rhythm rule: nothing on screen longer than 8 s; change type every 1–2 scenes.

### 6. Voice-over
Three routes, all ending in `voiceover/sNN.wav`:
1. Arena speech tool (I generate a file per scene from the script);
2. your microphone, one file per scene → `vo.py import`;
3. your microphone, one long take → `vo.py split`.
Then `vo.py normalize` and `vo.py check`. The build re-times scenes to the measured
audio duration the moment the files exist.

### 7. Assembly
```bash
$PY automation/projector.py build projects/<id>/project.json --draft   # structure check
$PY automation/projector.py build projects/<id>/project.json           # final 1080p
```
`--draft` is 720p and ~3× faster; use it for pacing decisions, not for upload.

### 8. Subtitles
Generated automatically from the script, timed to the narration, snapped to pauses.
`hindi.srt` for the YouTube subtitle upload; also burned into the video by default
(remove with a one-line change in `projector.py` if you prefer soft subs only).

### 9. Thumbnail
Fill `projects/<id>/thumb.json` (see `templates/thumbnail_brief.md`), then:
```bash
$PY automation/thumbnail.py --spec projects/<id>/thumb.json --out thumbnails/<id>.png
```
Check it at 168 px wide before you commit to it.

### 10. QC
```bash
$PY automation/qc.py video rendered_videos/<id>.mp4
```
Fix any FAIL (loudness, black frames, silent audio), then re-render. The script and
project checks (`qc.py script`, `qc.py project`) catch language and asset problems
before you spend render time.

### 11. Publish pack
```bash
$PY automation/seo.py pack projects/<id>/project.json --topic "..." \
   --source "..." --out projects/<id>/publish.md
```
Then upload manually: video, `hindi.srt`, thumbnail, title, description, tags,
chapters, end screen, playlist, and schedule the Shorts from
`python automation/projector.py shorts ...`.

## Naming conventions

| Thing | Pattern | Example |
|---|---|---|
| Project id | `category_slug` | `book_atomic_habits` |
| Scene id | `sNN` | `s07` |
| Final video | `rendered_videos/<id>.mp4` | `rendered_videos/book_atomic_habits.mp4` |
| Short | `shorts/<id>_shortNN.mp4` | `shorts/book_atomic_habits_short01.mp4` |
| Frames | `generated_assets/<id>/frames/sNN.png` | cache, safe to delete |
| Manifest | `projects/<id>/build_manifest.json` | provenance for every build |

## Build-time budget (measured on this 2-vCPU box)

| Work | 80 s video | 12 min video (estimate) |
|---|---|---|
| frames + Ken Burns | ~35 s | ~5 min |
| music synthesis | ~4 s | ~15 s |
| subtitles | ~1 s | ~2 s |
| encode + burn subs | ~90 s | ~9 min |

Plan on ~1.5× real-time for the final 1080p pass.
