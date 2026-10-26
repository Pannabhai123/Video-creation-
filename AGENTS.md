# Permanent Agent Operating Instructions (`Video-creation-`)

Whenever a session starts in this repository, treat these rules and the five state files below as the **active default YouTube production policy**. Do **not** ask the user to repeat these instructions.

## 1. Mandatory Startup Sequence (Every Session)
1. Read:
   - `CHANNEL_PREFERENCES.md` (Niche, Hindi default language, factual & non-clickbait rules, security rules)
   - `WORKFLOW_CONFIG.json` (15-step workflow, defaults, checkpoints, tool priorities)
   - `SYSTEM_STATUS.md` (Hardware limits, snapshot persistence rules, branch status)
   - `TOOL_INVENTORY.md` (Installed local tools & platform-native AI tools)
   - `ERROR_LOG.md` (Known failures & verified solutions—never repeat solved mistakes)
2. Verify runtime readiness **before** installing anything:
   ```bash
   command -v ffmpeg >/dev/null && command -v chromium >/dev/null && python3 -c "import moviepy" 2>/dev/null && [ -d node_modules/remotion ]
   ```
   - If and **only if** a component is missing (e.g., fresh container cold-boot), run:
     ```bash
     bash scripts/setup_environment.sh && sudo pip3 install --break-system-packages --no-deps -e .
     ```
   - Never reinstall working tools unnecessarily or create duplicate production frameworks.

## 2. Default Channel & Content Policy
- **Channel Niches:** Book Summaries, Self-Improvement, Personal Development, Psychology, Productivity, Habits & Discipline, Motivation, Educational Content.
- **Default Language:** **Hindi (`hi` / Devanagari)** unless the user specifies another language for the current video.
- **Editorial Integrity:** Original scripts only; verify important facts/authors/studies (`web_search`); **zero fabricated facts or fake quotes**; use practical real-life examples; honest non-clickbait titles and thumbnails; copyright-safe media only.

## 3. Default 15-Step Video Creation Workflow
Unless the user specifies a custom format, execute automatically:
1. Research topic (`web_search` / `fetch_page`).
2. Write original, engaging Hindi script with practical examples.
3. Verify important facts & citations.
4. Divide script into structured scenes (`storyboard.json`).
5. Generate scene-specific consistent images (`generate_image` with `offer_options: false`, cached in `projects/<slug>/assets/visuals/`).
6. Generate dynamic motion scenes from images & prompts (Remotion / OpenCV Ken Burns + kinetic callouts).
7. Create Hindi voice-over (`add_voice` + `generate_speech` in `hi`/`hi-IN` when interactive neural voice is appropriate, user-supplied audio, or local `espeak-ng` `hi` fallback).
8. Add copyright-safe auto-ducked background music + transition/chapter sound effects (`yt_studio.audio_engine`).
9. Synchronize all audio, scene timings, and visuals (`-14.0 LUFS` master).
10. Generate synchronized Hindi subtitles (`.srt`, `.vtt`, `.ass`, plus HarfBuzz React `SubtitleOverlay` burn-in & MP4 `mov_text` track).
11. Create `1280x720` & `1920x1080` YouTube thumbnails (via Remotion HarfBuzz `YouTubeThumbnail` for Hindi Devanagari).
12. Prepare YouTube title, SEO description, `00:00` chapters, and tags (`youtube_metadata.txt`).
13. Render final `1920x1080` 30 FPS H.264 + AAC MP4 (`yt-studio`).
14. Run automated QA verification (`python3 scripts/verify_video.py`).
15. Present final deliverables (`present_file`) and concise status report.

## 4. Failure, Efficiency & Security Rules
- **Failure Policy:** Read error -> diagnose cause -> repair & retry -> fall back if needed -> log in `ERROR_LOG.md` -> resume from last checkpoint (`checkpoints.json` / `work/segments/`). Never restart the entire project for a single-step failure.
- **Security Policy:** Never spend money, buy subscriptions, publish videos, expose secrets, or run destructive actions without explicit user permission.
