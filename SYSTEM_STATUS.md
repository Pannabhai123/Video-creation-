# System Status & Persistence Architecture

**Last Verified:** 2026-10-26  
**Repository:** `Pannabhai123/Video-creation-`  
**Current Session Branch:** `arena/9aa0950b-video-creation` (Active)  
**Overall Production System Status:** **OPERATIONAL & VERIFIED**

---

## 1. Hardware & OS Environment
- **OS:** Debian GNU/Linux 12 (bookworm), Kernel `6.1.158+` (`x86_64`)
- **CPU:** Intel(R) Xeon(R) @ 2.60 GHz (2 vCPUs; `AVX2` & `AVX-512` SIMD supported)
- **RAM:** 3.85 GiB (~3.5 GiB available), 0 Swap -> Configured for `concurrency=1` (Remotion) and `threads=2` (FFmpeg) with streaming/segmented rendering
- **Storage:** 21 GB root disk (~17.0 GiB free)
- **GPU:** None attached (`cpu_simd_fallback` + `SwiftShader` `--gl=swangle` active)
- **Network Allowlist:** `github.com`, `codeload.github.com`, `api.github.com`, `registry.npmjs.org`, `pypi.org`, `files.pythonhosted.org` (plus platform-managed tools `web_search`, `fetch_page`, `generate_image`, `add_voice`, `generate_speech`)

---

## 2. Verified Persistence Behavior (Empirical Ground Truth)

1. **Workspace Files Inside `/home/user/Video-creation-` (Within Same Session):**
   - **Persisted** across turns and multi-day container restarts (verified across `2026-10-24` -> `2026-10-26` cold boot), **except** directories excluded from snapshots (`node_modules`, `.venv`, `.cache`, `build`, `dist`, `out`, `.output`) and `.gitignore`-excluded build caches.
2. **System Binaries & Packages Outside `/home/user` (`/usr/local/bin`, `/usr/local/lib`):**
   - **Not persisted** across container VM cold-boots or new chat sandboxes.
   - **Automated Fast Recovery:** Running `bash scripts/setup_environment.sh` checks each tool first (`0s` no-op when already warm; `~55s` clean restore from PyPI/npm after a container cold-boot). Never run `pip` or `npm` unconditionally—always check `which ffmpeg` and `python3 -c "import moviepy"` first.
3. **Cross-Chat Persistence Across Different Conversations:**
   - **No Global Platform Memory API:** Arena Agent Mode does **not** expose an agent-writable global user memory or account-wide system prompt store that automatically transfers across unrelated chats.
   - **GitHub Repository Persistence (Supported Mechanism):**
     - All permanent instructions and configurations (`AGENTS.md`, `CLAUDE.md`, `CHANNEL_PREFERENCES.md`, `WORKFLOW_CONFIG.json`, `SYSTEM_STATUS.md`, `TOOL_INVENTORY.md`, `ERROR_LOG.md`, and `yt_studio/`) are stored in this repository.
     - **Important Branch Requirement:** New Arena chats attached to `Pannabhai123/Video-creation-` branch from `main`. Therefore, changes committed on `arena/9aa0950b-video-creation` become automatically available to **all future chats on this repository** only after this branch is pushed and merged into `main` on GitHub.

---

## 3. Startup Checklist for Every New Chat / Cold-Boot Session
1. Read `CHANNEL_PREFERENCES.md`, `WORKFLOW_CONFIG.json`, `SYSTEM_STATUS.md`, `TOOL_INVENTORY.md`, and `ERROR_LOG.md`.
2. Run a quick non-destructive readiness check:
   ```bash
   command -v ffmpeg && command -v chromium && python3 -c "import moviepy" && [ -d node_modules/remotion ]
   ```
3. **Only if step 2 reports a missing component** (e.g., fresh VM cold-boot), run:
   ```bash
   bash scripts/setup_environment.sh && sudo pip3 install --break-system-packages --no-deps -e .
   ```
4. Proceed directly to executing the user's video request using `yt-studio` and the 15-step workflow without asking the user to repeat their preferences.
