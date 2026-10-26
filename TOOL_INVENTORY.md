# Tool Inventory & Integration Registry

**Last Updated:** 2026-10-26  
**Bootstrap / Health Script:** `scripts/setup_environment.sh` | `scripts/inspect_system.py`

---

## 1. Platform-Native Agent Tools (Zero Install Required)
Available directly to the Arena agent during interactive workflows:
| Tool | Role in 15-Step Workflow | Usage Policy |
| :--- | :--- | :--- |
| `web_search` & `fetch_page` | Step 1 (Topic Research) & Step 3 (Fact/Book Verification) | Use to verify book concepts, authors, psychological studies, and avoid fabricated quotes |
| `generate_image` | Step 5 (Scene-Specific Visuals & Thumbnail Hero Art) | Pass `offer_options: false` for multi-scene assets inside a video build; issue calls in parallel where helpful; cache saved PNG/JPGs in `projects/<slug>/assets/visuals/` |
| `add_voice` & `generate_speech` | Step 7 (Neural Hindi `hi` / `hi-IN` Voice-Over) | Requires one user voice selection via `add_voice` per session before `generate_speech`; use when high-naturalness neural Hindi narration is desired, or fall back to local `espeak-ng` (`hi`) for zero-pause unattended runs |
| `present_file` | Step 15 (Final Delivery) | Open the rendered master `.mp4` in the user's viewer upon completion |

---

## 2. Local CLI & Rendering Binaries
| Binary | Version | Path | Capabilities |
| :--- | :--- | :--- | :--- |
| `ffmpeg` | `7.0.2-static` | `/usr/local/bin/ffmpeg` | H.264 (`libx264`), H.265 (`libx265`), VP9, AV1, AAC, `loudnorm`, `afftdn`, `sidechaincompress`, `xfade`, `zoompan`, `ass`/`subtitles`, `mov_text` |
| `ffprobe` | `N-66595-static` | `/usr/local/bin/ffprobe` | Stream/container/codec/FPS/duration JSON QA inspection |
| `chromium` | `153.0.8010.0` | `/usr/local/bin/chromium` | Self-contained headless Chromium (`@sparticuz/chromium` + `NSS`/`NSPR` + `SwiftShader` `--gl=swangle`) with full **HarfBuzz Indic/Devanagari** shaping |
| `node` / `npm` | `v22.22.3` / `10.9.8` | `/usr/local/bin/node` | Pre-installed runtime for Remotion 4 |
| `convert` | `ImageMagick 6.9.11` | `/usr/bin/convert` | Pre-installed raster image utility |
| `yt-studio` | `1.0.0` | `/usr/local/bin/yt-studio` (`python3 -m yt_studio`) | Unified project initializer, asset organizer, storyboarder, renderer, and verifier |

---

## 3. Remotion & React Compositions (`remotion_src/`)
- **Packages:** `remotion@4.0.538`, `@remotion/cli@4.0.538`, `@remotion/renderer@4.0.538`, `@remotion/transitions@4.0.538`, `@remotion/shapes@4.0.538`, `react@18.3.1`
- **Registered Compositions:**
  - `YouTubeShowcase` — Full 1080p30 multi-scene video with HarfBuzz Hindi/Devanagari titles, scene images, kinetic bullets, `SubtitleOverlay`, and `YouTubeEndScreen`
  - `AnimatedIntro` — Spring-animated episode opener
  - `AnimatedEndScreen` — YouTube End Screen with Subscribe CTA + `WATCH NEXT` & `BEST FOR VIEWER` 16:9 slots
  - `YouTubeThumbnail` — `1920x1080` / `1280x720` HarfBuzz-shaped Hindi & English thumbnail renderer (`npx remotion still`)

---

## 4. Python Video, Audio & Subtitle Libraries
- **Video & Vision:** `moviepy 2.2.1`, `opencv-python-headless 5.0.0.93`, `Pillow 11.3.0`, `imageio 2.38.1`, `imageio-ffmpeg 0.6.0`, `av 18.1.0`
- **Audio, Music, SFX & Mastering:** `numpy 2.4.6`, `scipy 1.17.1`, `soundfile 0.14.0`, `soxr 1.1.0`, `librosa 0.11.0`, `noisereduce 3.0.3`, `pydub 0.25.1`, `pyloudnorm 0.2.0` (`-14.0 LUFS` mastering)
- **Offline TTS & STT:** `espeakng-loader 0.2.4` (`libespeak-ng.so` supporting Hindi `hi` and English `en-us` with exact Unicode character word-boundary timestamps), `pocketsphinx 5.1.1` (offline English STT), `faster-whisper 1.2.1` (ready when `WHISPER_LOCAL_MODEL_PATH` is set)
- **Subtitles:** `pysrt 1.1.2`, `srt 3.5.3`, `webvtt-py 0.6.0`
- **Bundled Studio Fonts (`assets/fonts/`):** `Poppins` (Regular/Medium/SemiBold/Bold/ExtraBold/Black — Latin + Devanagari), `NotoSansDevanagari[wdth,wght].ttf`, `BebasNeue-Regular.ttf`, `JetBrainsMono-Regular.ttf`

---

## 5. Optional External Cloud APIs (Disabled Unless Configured in `.env`)
None of these are assumed available or free:
- `OPENAI_API_KEY` (GPT scriptwriting / Whisper / TTS)
- `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` (LLM scriptwriting)
- `ELEVENLABS_API_KEY` (Cloud neural Hindi/English TTS)
- `PEXELS_API_KEY` / `PIXABAY_API_KEY` (Stock B-roll media)
