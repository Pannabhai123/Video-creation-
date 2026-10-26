# System Inspection, Verification & Honest Tool Report

## 1. Environment & Hardware Inspection Summary

| Component | Detected Specification | Production Impact |
| :--- | :--- | :--- |
| **Operating System** | Debian GNU/Linux 12 (bookworm), Kernel `6.1.158+` (`x86_64`) | Full Linux static binary & Python `manylinux` compatibility |
| **CPU** | Intel(R) Xeon(R) @ 2.60 GHz, 2 logical cores (`sse4_2`, `avx`, `avx2`, `avx512f`, `avx512bw`, `avx512_vnni`) | Strong AVX2/AVX-512 SIMD acceleration for `libx264` CPU encoding |
| **Memory (RAM)** | 3.85 GiB total (~3.5 GiB available), 0 GiB swap | Requires memory-safe frame streaming & segmented rendering (`concurrency=1`, `threads=2`) |
| **Storage** | 21 GB root disk (~16.9 GiB free after full installation) | Sufficient for multi-scene 1080p/4K segmented production |
| **GPU / Hardware Accel** | None (`nvidia-smi` absent, `/dev/dri` absent; KVM virtual guest) | Hardware encoders (`NVENC`/`VAAPI`/`QSV`) auto-detected when available; cleanly falls back to CPU `libx264` + SwiftShader (`--gl=swangle`) |
| **Outbound Network** | Allowed: `pypi.org`, `files.pythonhosted.org`, `registry.npmjs.org`, `github.com`, `codeload.github.com`, `api.github.com`. Blocked: `deb.debian.org`, `storage.googleapis.com`, `huggingface.co`, `objects.githubusercontent.com` | Packages installed directly via self-contained PyPI wheels, npm tarballs, and shallow Git checkouts |

---

## 2. Honest Reporting Summary (Step 7)

### A. Tools Successfully Installed & Configured
1. **FFmpeg & FFprobe**
   * `ffmpeg 7.0.2-static` (`/usr/local/bin/ffmpeg`) — Full GPL static build with `libx264`, `libx265`, `libvpx-vp9`, `libaom-av1`, `aac`, `libmp3lame`, `libopus`, `mov_text`, `srt`, `ass`/`subtitles` (`libass`), `loudnorm`, `afftdn` (FFT noise reduction), `sidechaincompress`, `acompressor`, `acrossfade`, `xfade`, and `zoompan`.
   * `ffprobe` (`/usr/local/bin/ffprobe`, static build `N-66595`) — Stream, codec, FPS, resolution, and duration inspection.
2. **Python Video, Vision & Graphics Libraries**
   * `moviepy 2.2.1` — Programmatic video editing, `VideoClip`, `TextClip`, and compositing.
   * `opencv-python-headless 5.0.0.93` — Subpixel Ken Burns motion, image resizing, and frame QA decoding.
   * `Pillow 11.3.0` — High-DPI YouTube thumbnails (1280x720 & 1920x1080), title cards, diagrams, and kinetic bullet sprites.
   * `numpy 2.4.6` & `scipy 1.17.1` — Array DSP, procedural stereo music synthesis, and vocal EQ filtering.
   * `imageio 2.38.1`, `imageio-ffmpeg 0.6.0`, & `av 18.1.0` (PyAV) — Media container & frame I/O.
3. **Remotion & Headless Browser Rendering**
   * `remotion 4.0.538`, `@remotion/cli 4.0.538`, `@remotion/renderer 4.0.538`, `@remotion/transitions 4.0.538`, `@remotion/shapes 4.0.538`, `react 18.3.1`, `typescript 5.6.3`.
   * `Chromium 153.0.8010.0` (`/usr/local/bin/chromium`) — Extracted from `@sparticuz/chromium` with bundled `NSS`/`NSPR` shared libraries and `SwiftShader` Angle software WebGL (`--gl=swangle`), enabling 100% local React video rendering without X11 or GPU hardware.
4. **Audio Processing & Voiceover Tools**
   * `soundfile 0.14.0`, `soxr 1.1.0`, `librosa 0.11.0`, `pydub 0.25.1` — 48 kHz audio I/O, speech-interval detection, and mixing.
   * `noisereduce 3.0.3` — Spectral gating noise reduction for external microphone voiceovers.
   * `pyloudnorm 0.2.0` — ITU-R BS.1770-4 loudness metering & `-14.0 LUFS` YouTube mastering.
   * `espeakng-loader 0.2.4` (`libespeak-ng.so` + voice data) — Offline multi-language TTS synthesis with exact millisecond word-boundary events.
5. **Subtitle & Transcription Tools**
   * `pysrt 1.1.2`, `srt 3.5.3`, `webvtt-py 0.5.1` — SRT & WebVTT generation and validation, plus custom broadcast `.ass` styling.
   * `pocketsphinx 5.1.1` — Bundled offline English acoustic/language model for local speech-to-text transcription.
   * `faster-whisper 1.2.1` (`ctranslate2 4.8.3`, `onnxruntime 1.31.0`) — Installed and ready for local Whisper CTranslate2 model directories (`WHISPER_LOCAL_MODEL_PATH`).
6. **Broadcast Typography & CLI Tooling**
   * Open-source OFL studio fonts (`Poppins` Regular/Medium/SemiBold/Bold/ExtraBold/Black, `Bebas Neue`, `JetBrains Mono`) in `assets/fonts/` and `/usr/local/share/fonts/truetype/studio/`.
   * `yt-studio` CLI (`click 8.5.0`, `rich 15.0.0`, `PyYAML 6.0.3`).

### B. Tools Already Present Before Setup
* **Python `3.11.2`** (`pip 23.0.1`, `setuptools`, `wheel`, `python3-venv`)
* **Node.js `v22.22.3`**, **`npm 10.9.8`**, **`yarn 1.22.22`**, **`corepack 0.34.6`**
* **ImageMagick `6.9.11-60 Q16`** (`/usr/bin/convert`)
* **System Utilities & Build Chain**: `gcc 12`, `g++ 12`, `make`, `git`, `gh`, `jq`, `ripgrep`, `curl`, `wget`, and `DejaVuSans` system font.

### C. Installation Failures, Sandbox Constraints & Resolutions
1. **`apt-get` Debian Mirrors Blocked (`deb.debian.org` / `security.debian.org`)**:
   * *Impact:* System `.deb` packages (`apt-get install ffmpeg chromium espeak-ng`) cannot be fetched over the network in this sandbox.
   * *Resolution:* Installed static `ffmpeg 7.0.2`, static `ffprobe`, self-contained `Chromium 153` (with bundled `al2023` NSS/NSPR `.so` libraries and SwiftShader), and `libespeak-ng.so` (`espeakng-loader`) directly via verified PyPI wheels and npm registry tarballs.
2. **`ffmpeg-static` (npm) Postinstall Failure**:
   * *Impact:* `npm install ffmpeg-static` failed during `install.js` (`UNABLE_TO_VERIFY_LEAF_SIGNATURE`) because it attempts to download binaries from `objects.githubusercontent.com`, which is blocked by the sandbox egress allowlist.
   * *Resolution:* Replaced with `imageio-ffmpeg` (FFmpeg 7.0.2-static) and `@ffprobe-installer/linux-x64`, which bundle binaries directly inside allowed package archives.
3. **Remotion Default Browser Download (`storage.googleapis.com`)**:
   * *Impact:* Remotion's default runtime download of Chrome Headless Shell from `storage.googleapis.com` is blocked by sandbox network rules.
   * *Resolution:* Pre-installed self-contained Chromium 153 at `/usr/local/bin/chromium` and configured `remotion.config.ts` (`setBrowserExecutable('/usr/local/bin/chromium')`, `setChromiumOpenGlRenderer('swangle')`).
4. **Remote HuggingFace Model Downloads (`huggingface.co`)**:
   * *Impact:* `faster-whisper` and neural TTS libraries (`piper-tts` / `kokoro-onnx`) are installable via `pip`, but automatic runtime weight downloads from `huggingface.co` are blocked in this sandbox.
   * *Resolution:* Bundled offline `pocketsphinx` + `librosa` speech-envelope alignment for STT/synchronization and `espeakng-loader` for offline TTS, while keeping `faster-whisper` wired to `WHISPER_LOCAL_MODEL_PATH` whenever local model weights are provided.
5. **Hardware GPU Encoders (`h264_nvenc`, `h264_vaapi`, `h264_qsv`)**:
   * *Impact:* Virtualized KVM host has no physical GPU attached.
   * *Resolution:* Auto-detection implemented in `yt_studio/config.py` with clean fallback to AVX-512 CPU `libx264`.

### D. Tools Requiring Paid Subscriptions or External API Keys
The system does **not** assume any paid or external cloud APIs are free. Optional connectors in `.env.example` require user-supplied accounts/keys (and outbound network access to those endpoints):
* **LLM Scriptwriting / Storyboarding APIs:** OpenAI (`OPENAI_API_KEY`), Anthropic Claude (`ANTHROPIC_API_KEY`), Google Gemini (`GEMINI_API_KEY`).
* **Premium Cloud Neural Voiceover APIs:** ElevenLabs (`ELEVENLABS_API_KEY`), OpenAI Audio Speech (`OPENAI_API_KEY`).
* **Cloud Stock B-Roll APIs:** Pexels (`PEXELS_API_KEY` — free tier requires registration key), Pixabay (`PIXABAY_API_KEY` — free tier requires registration key).
* **Commercial Video Suites / Generative Video SaaS:** DaVinci Resolve Studio, Adobe Premiere Pro / After Effects, Runway Gen-3, OpenAI Sora, Luma Dream Machine, Midjourney, Epidemic Sound / Artlist (require commercial licenses or paid subscriptions).
* **Remotion Company License Note:** Remotion is free for individuals and organizations up to 3 employees under the Remotion License; companies with 4+ employees require a paid Remotion Company License.

---

## 3. Sample Render Verification Summary (Step 5)

* **Output File:** `renders/sample_youtube_video/exports/final_youtube_1080p.mp4` (`5.95 MB`)
* **Container / Video:** `MP4` (`+faststart`), `H.264 High`, `yuv420p`, `1920x1080` (`16:9`), `30.0 FPS`, `32.97s`
* **Hybrid Engines Verified:**
  * `scene_01` (Title Screen): `Remotion React (AnimatedIntro)`
  * `scene_02` (External Diagram + Kinetic Text): `MoviePy 2.x + OpenCV Ken Burns + Pillow`
  * `scene_03` (Timeline Visual + Kinetic Text): `FFmpeg Streaming Pipe + OpenCV + Pillow`
  * `scene_04` (Outro & End Screen): `Remotion React (AnimatedEndScreen)`
* **Audio Verification:** `AAC Stereo 48,000 Hz`, Voiceover + Auto-Ducked Procedural Soundtrack, **`-14.0 LUFS` integrated loudness** (`-2.95 dBTP` true peak)
* **Subtitle Verification:** 14 frame-accurate cues verified in `subtitles.en.srt`, `subtitles.en.vtt`, burned-in `subtitles.en.ass`, and soft-embedded MP4 `mov_text` stream (`errors: []`)
* **4K Verification:** Also verified `youtube_4k` (`3840x2160` @ `30.0 FPS`, `H.264` + `AAC`, `-13.61 LUFS`) with external voiceover noise reduction.
