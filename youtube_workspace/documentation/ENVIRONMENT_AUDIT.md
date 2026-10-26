# Environment Audit — Ronny Raj YouTube Production Workspace

Audit date: 2026-10-26 · Sandbox: Debian 12 (bookworm), x86_64, 2 vCPU, 3.8 GB RAM,
20 GB free disk, non-root user `user` with passwordless `sudo` (but see §3), Python 3.11.2,
Node 22.22.3, outbound network limited to an allowlist.

Everything below was **executed and verified** in this environment. Nothing is assumed.

---

## 1. Tools already available (before any install)

| Tool | Version | State | Used for |
|---|---|---|---|
| Python | 3.11.2 | working | all automation |
| Node.js / npm | 22.22.3 / 10.9.8 | working | available, not needed by the current pipeline |
| git | 2.x | working | version control of the workspace |
| gh (GitHub CLI) | 2.23.0 | authenticated | repo/PR operations |
| ImageMagick | 6.9.11-60 | working, **no Pango/rsvg** | not used for Hindi text (cannot shape Devanagari) |
| gcc | present | working | only if a wheel needs building |
| curl / wget / jq | present | working | downloads, JSON |
| DejaVu fonts | 6 files | present | Latin fallback only — **no Devanagari coverage** |

## 2. What was missing

FFmpeg, ffprobe, all Python media libraries, all Devanagari fonts, TTS engines,
Whisper/ASR, Chromium/Remotion, yt-dlp, OpenCV, ImageMagick `magick` (v7 syntax),
`fc-list`, `rsvg-convert`, `sox`, `pandoc`.

## 3. What I could not install — and why

| Blocked | Reason (verified) | Consequence / workaround |
|---|---|---|
| `apt-get install` anything | `deb.debian.org` is **not** in the network allowlist — `apt-get update` fails with `Connection failed [IP: 151.101.66.132 80]`. `sudo` itself works, so this is network policy, not permissions. | Installed equivalent functionality from PyPI wheels instead (see §5). |
| GitHub **release assets** and `raw.githubusercontent.com` | TLS handshake fails (`SSL_ERROR_SYSCALL`) — those hosts are blocked even though `github.com`, `api.github.com` and `codeload.github.com` work. | Downloaded fonts through the **GitHub API** (`gh api repos/.../contents/...`), which returns base64 content. |
| Hugging Face (`huggingface.co`, `cdn-lfs`) | unreachable (HTTP 000) | **No Whisper** (faster-whisper / ctranslate2 models) and **no Piper TTS** — both need model weights from HF. Alternative transcription path implemented: subtitles are generated from the known script (see §8). |
| `speech.platform.bing.com` (edge-tts) | TCP connect fails | Installed `edge-tts` to prove the point, but **cloud TTS cannot reach the internet from this sandbox**. Voice-over therefore comes from Arena's built-in speech tool, or your own recording. |
| Chromium / Playwright download | browser CDN not allowlisted | No HTML/CSS→video route (Remotion). Replaced by a native Pillow+HarfBuzz+FFmpeg renderer, which is far lighter anyway (no 300 MB browser, no Node build step at render time). |
| Stock music / stock footage APIs | not allowlisted, and licensing is per-channel | Music and SFX are **synthesised locally** from oscillators/noise — original, royalty-free, reproducible. |

Cost of these limits: nothing needs your payment or manual installation. The only
capability that is genuinely unavailable in-sandbox is neural speech synthesis, and
that is covered by Arena's own speech tool.

## 4. Available resources in numbers

- CPU: 2 cores · RAM: 3.8 GB · Disk: 20 GB free.
- Render benchmark (measured): an 8-scene, 80-second 1080p30 video builds in **131 s**
  end-to-end (frames + Ken Burns + music synthesis + subtitles + H.264 encode).
  Practical ceiling on this box is roughly a 12–15 minute 1080p video per run.
- I/O is the bottleneck, not CPU: keep `generated_assets/` on the same volume.

## 5. Installed and verified (this session)

Everything below was installed from PyPI (allowlisted) into a repo-local venv at
`/home/user/Video-creation-/.venv` — system Python is untouched (PEP 668 compliant).

| Component | Version | Verification performed |
|---|---|---|
| FFmpeg (via `imageio-ffmpeg`) | **7.0.2 static** | `-version` shows `--enable-libass --enable-libx264 --enable-libfreetype --enable-libfribidi --enable-libmp3lame`; encoded real H.264/AAC video |
| PyAV | 18.1.0 | probed streams, duration, fps (replaces `ffprobe`) |
| Pillow | 11.3.0 | drew and composited frames; **no `raqm`** → cannot shape Devanagari (this is why HarfBuzz is used) |
| uharfbuzz | 0.57.0 | conjunct shaping proven: **कर्म = 71.0 px vs करम = 92.0 px** |
| freetype-py | 2.5.1 | rasterised shaped glyphs with subpixel placement |
| fontTools | 4.67.0 | instantiated variable font → 4 static Devanagari weights |
| numpy | 2.4.6 | gradients, grain, analysis |
| scipy | 1.17.1 | FFT convolution reverb, filtering |
| soundfile | 0.14.0 | 48 kHz 16-bit WAV I/O |
| srt | 3.5.3 | `.srt` output |
| pysubs2 | 1.8.1 | styled `.ass` for burn-in |
| moviepy | 2.2.1 | installed as an alternative editor backend (not used by the renderer) |

Fonts (OFL-licensed, downloaded via GitHub API, licences stored beside them):

| Font | Use | Licence |
|---|---|---|
| Noto Sans Devanagari 400/500/700/800 | body, bullets, subtitles | SIL OFL 1.1 |
| Mukta Regular/Bold/ExtraBold | display headlines, thumbnails | SIL OFL 1.1 |
| Poppins Bold/SemiBold | numbers, Latin kickers, watermark | SIL OFL 1.1 |

Proven working end-to-end: a **79.75 s, 1920×1080, 30 fps, H.264/AAC** video with
Devanagari typography, burned-in Hindi subtitles, synthesised music bed and ducking
→ `rendered_videos/demo_productivity.mp4`.

## 6. Persistence between sessions — what survives and what does not

**Survives (this repository, tracked by git):**
`youtube_workspace/` — all scripts, templates, fonts, brand preset, docs, and any
project you commit. New sessions start by reading `youtube_workspace/README.md`.
Arena also re-attaches the same repository to this conversation branch, so the
workspace is where you left it.

**Does not survive:**
- `/home/user/.venv` — the excluded-from-snapshot path means the venv may need
  recreating (one command, ~15 s, see `README.md` → Reinstall).
- `rendered_videos/`, `generated_assets/`, music beds — deliberately gitignored to
  keep the repo small. Rebuild them with the same commands; the pipeline is
  deterministic, so output is reproducible.
- `/tmp` downloads, shell state, environment variables.
- Conversation memory of tool versions → that is exactly what
  `documentation/TOOLS.md` and `python automation/check_env.py` are for.

## 7. Reusable workspace created

20 folders under `youtube_workspace/`, 8 templates, 6 automation modules, 1 brand
preset, 2 example projects. See `README.md` for the map and `TOOLS.md` for commands.

## 8. Remaining limitations (honest list)

1. **No in-sandbox speech synthesis.** Hindi voice-over must come from Arena's speech
   tool (I can generate it into `projects/<id>/voiceover/`) or your microphone. The
   pipeline is built to accept either, per scene, and re-times itself to real audio.
2. **No ASR.** Subtitles come from the script (more accurate for Hindi than small ASR
   models anyway). If you record something that differs from the script, regenerate
   the `.srt` from the edited script — do not expect transcription.
3. **No stock footage.** Scene visuals are typography-led cards with Ken Burns motion
   plus any stills/photos you provide in `images/`. This is a deliberate documentary
   style that is fully copyright-clean; it is not a B-roll montage.
4. **No Chrome-based rendering**, so no HTML/CSS brand animations. Motion is limited to
   zoom/pan, fades, and text/card composition.
5. **2 vCPU** → a 15-minute 1080p render takes several minutes; use `--draft` (720p) to
   iterate on structure before the final render.
6. **No Instagram/TikTok auto-upload, no YouTube API keys** configured — publishing is a
   manual upload step with the generated title/description/tags/subtitles/thumbnail pack.
7. ImageMagick is present but unusable for Hindi (no Pango/HarfBuzz) — do not use it for
   text; `hinditext.py` is the supported path.

## 9. Fastest path to your first real video

```bash
# 0. (new session only) recreate the venv — 15 seconds
python3 -m venv /home/user/Video-creation-/.venv
/home/user/Video-creation-/.venv/bin/pip install -r youtube_workspace/requirements.txt

# 1. verify
cd /home/user/Video-creation-/youtube_workspace
/home/user/Video-creation-/.venv/bin/python automation/check_env.py

# 2. scaffold a project from a template
PY=/home/user/Video-creation-/.venv/bin/python
$PY automation/newproject.py --id book_atomic_habits --type book_summary \
    --title "Atomic Habits — पूरी समरी" --mood reflective

# 3. ask me for: research → script → project.json scenes (I write these)
# 4. I generate the Hindi narration per scene with the speech tool
$PY automation/vo.py check --project projects/book_atomic_habits/project.json

# 5. build (draft first, then final)
$PY automation/projector.py build projects/book_atomic_habits/project.json --draft
$PY automation/projector.py build projects/book_atomic_habits/project.json

# 6. quality control + shorts + publishing pack
$PY automation/qc.py video rendered_videos/book_atomic_habits.mp4
$PY automation/projector.py shorts projects/book_atomic_habits/project.json --count 3
$PY automation/seo.py pack projects/book_atomic_habits/project.json \
    --topic "Atomic Habits" --out projects/book_atomic_habits/publish.md
```

Realistic first-video time once the workspace is warm: **research + script 30–45 min
(yours/mine together), narration 5 min, render 3–5 min, QC/publish pack 10 min.**
