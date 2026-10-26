# Complete YouTube Long-Form Video Creation System (`yt-studio`)

An end-to-end, local-first automated production studio for **professional YouTube long-form videos**, combining **FFmpeg 7**, **Python (`MoviePy 2`, `OpenCV`, `Pillow`, `Librosa`, `Noisereduce`, `Pyloudnorm`)**, and **Remotion 4 (`React 18` + Headless Chromium `SwiftShader`)**.

---

## Quick Start

### 1. Inspect System & Installed Production Stack
```bash
python3 scripts/inspect_system.py
```

### 2. List Reusable YouTube Export Presets
```bash
yt-studio presets
```
* **`youtube_1080p` (Default):** `1920x1080` (16:9), `30 FPS`, `H.264 High@4.2` (`yuv420p`, `bt709`, CRF 18, 2s closed GOP, `+faststart`), `AAC 192 kbps 48 kHz Stereo`, normalized to **`-14.0 LUFS`**.
* **`youtube_1080p60`:** `1920x1080` (16:9), `60 FPS`, `H.264 High@4.2` + `AAC 192 kbps`.
* **`youtube_4k`:** `3840x2160` (16:9), `30 FPS`, `H.264 High@5.1` + `AAC 256 kbps` (auto-adapts CPU preset & segmented rendering on low-RAM hosts).
* **`youtube_720p_draft`:** `1280x720` (16:9), `30 FPS` rapid preview preset.

### 3. Run the End-to-End Sample Video Test
```bash
yt-studio demo
```
Generates and verifies `renders/sample_youtube_video/exports/final_youtube_1080p.mp4` alongside 720p/1080p YouTube thumbnails, `.srt`/`.vtt`/`.ass` captions, chapter timestamps, and `verification_report.json`.

---

## Automated Workflow for New YouTube Videos

### Option A: Single-Command CLI Build
Supply any combination of **topic**, **script**, **voiceover**, **images/video clips**, **preferred duration**, **subtitle language**, and **output resolution**:

```bash
yt-studio build \
  --topic "Designing Scalable Distributed Databases" \
  --script path/to/script.md \
  --voiceover path/to/narration.wav \
  --assets path/to/diagram1.png --assets path/to/broll_clip.mp4 \
  --duration 600 \
  --language en \
  --resolution 1080p \
  --engine hybrid
```
* Omit `--script` to auto-generate a multi-chapter YouTube script & storyboard scaled to `--duration`.
* Omit `--voiceover` to synthesize narration locally via `espeak-ng` (with exact millisecond word-level caption sync) or via optional `OPENAI_API_KEY` / `ELEVENLABS_API_KEY` when configured in `.env`.
* Omit `--music` to synthesize a **100% copyright-safe stereo ambient soundtrack** that automatically ducks beneath speech and masters to **`-14.0 LUFS`**.

### Option B: Reusable Project Workspace (`projects/<name>/`)
```bash
# 1. Initialize a clean project folder
yt-studio init my_next_episode --topic "Modern Linux Performance Tuning"

# 2. Edit projects/my_next_episode/script.md and drop optional media into:
#    - projects/my_next_episode/assets/voiceover/
#    - projects/my_next_episode/assets/visuals/
#    - projects/my_next_episode/assets/music/

# 3. Render and verify the complete video
yt-studio run projects/my_next_episode/project.yaml
```

### Option C: Direct Remotion React Rendering
```bash
# List registered React video compositions
npx remotion compositions remotion_src/index.ts

# Render a standalone React composition
npx remotion render remotion_src/index.ts YouTubeShowcase renders/remotion_showcase.mp4
```

---

## Repository Structure

```text
Video-creation-/
├── config/
│   ├── export_presets.yaml       # YouTube 1080p30 (default), 1080p60, 4K 2160p30 & 720p presets
│   ├── workflow_defaults.yaml    # Channel branding, audio ducking, LUFS & subtitle styling
│   └── system_profile.json       # Auto-detected hardware, codec & environment profile
├── assets/
│   └── fonts/                    # OFL broadcast fonts (Poppins, Bebas Neue, JetBrains Mono)
├── scripts/
│   ├── setup_environment.sh      # Idempotent installer & environment verifier
│   ├── inspect_system.py         # Step 1 hardware, runtime, codec & API inspector
│   └── verify_video.py           # Step 5 automated MP4, OpenCV, LUFS & SRT QA validator
├── remotion_src/                 # Remotion 4 + React 18 compositions (Intro, SceneCards, EndScreen)
├── yt_studio/                    # Python production engine (CLI, storyboarder, audio, subtitles, graphics, renderer)
├── projects/
│   └── template_project/         # Ready-to-use template for future YouTube videos
├── renders/
│   └── sample_youtube_video/     # Verified 1080p sample video, thumbnails, subtitles & QA report
└── SYSTEM_REPORT.md              # Honest environment, installation & API report
```

See **[`SYSTEM_REPORT.md`](./SYSTEM_REPORT.md)** for the complete system inspection and honest installation/API report.
