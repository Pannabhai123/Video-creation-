#!/usr/bin/env bash
# Idempotent Environment Installer & Verifier for YouTube Long Video Creation System
# Checks existing binaries/packages first to avoid duplicate installations.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "=== [1/5] Checking Python Video, Audio & Subtitle Dependencies ==="
python3 -c "import moviepy, cv2, PIL, numpy, scipy, imageio_ffmpeg, av, soundfile, librosa, noisereduce, pydub, pyloudnorm, pysrt, srt, webvtt, espeakng_loader, pocketsphinx, faster_whisper, yaml, rich" 2>/dev/null || {
  echo "Installing Python production packages..."
  sudo pip3 install --break-system-packages --no-cache-dir \
    moviepy opencv-python-headless Pillow numpy scipy imageio imageio-ffmpeg av \
    soundfile librosa noisereduce pydub pyloudnorm pysrt srt webvtt-py \
    espeakng-loader pocketsphinx faster-whisper pyyaml rich click requests python-dotenv
}

if [ ! -d "$REPO_ROOT/.venv" ]; then
  python3 -m venv --system-site-packages "$REPO_ROOT/.venv"
fi

echo "=== [2/5] Checking FFmpeg & FFprobe ==="
if ! command -v ffmpeg >/dev/null 2>&1; then
  FFMPEG_SRC="$(python3 -c 'import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())')"
  sudo cp "$FFMPEG_SRC" /usr/local/bin/ffmpeg
  sudo chmod 755 /usr/local/bin/ffmpeg
fi

if ! command -v ffprobe >/dev/null 2>&1 || ! command -v chromium >/dev/null 2>&1; then
  TMP_BIN="$(mktemp -d)"
  pushd "$TMP_BIN" >/dev/null
  npm init -y >/dev/null 2>&1
  npm install @ffprobe-installer/linux-x64 @sparticuz/chromium --no-audit --no-fund >/dev/null 2>&1

  if ! command -v ffprobe >/dev/null 2>&1; then
    sudo cp "$TMP_BIN/node_modules/@ffprobe-installer/linux-x64/ffprobe" /usr/local/bin/ffprobe
    sudo chmod 755 /usr/local/bin/ffprobe
  fi

  if ! command -v chromium >/dev/null 2>&1; then
    echo "Installing self-contained Headless Chromium for Remotion..."
    sudo mkdir -p /usr/local/lib/chromium-headless
    sudo TMP_BIN="$TMP_BIN" node -e '
      const fs = require("fs");
      const zlib = require("zlib");
      const path = require("path");
      const binDir = path.join(process.env.TMP_BIN, "node_modules/@sparticuz/chromium/bin");
      const outDir = "/usr/local/lib/chromium-headless";
      fs.writeFileSync(path.join(outDir, "chromium-bin"), zlib.brotliDecompressSync(fs.readFileSync(path.join(binDir, "chromium.br"))), {mode: 0o755});
      for (const name of ["al2023", "swiftshader", "fonts"]) {
        fs.writeFileSync(path.join(process.env.TMP_BIN, name + ".tar"), zlib.brotliDecompressSync(fs.readFileSync(path.join(binDir, name + ".tar.br"))));
      }
    '
    sudo tar -xf "$TMP_BIN/al2023.tar" -C /usr/local/lib/chromium-headless
    sudo tar -xf "$TMP_BIN/swiftshader.tar" -C /usr/local/lib/chromium-headless
    sudo tar -xf "$TMP_BIN/fonts.tar" -C /usr/local/lib/chromium-headless
    sudo tee /usr/local/bin/chromium >/dev/null << 'WRAP'
#!/usr/bin/env bash
export LD_LIBRARY_PATH="/usr/local/lib/chromium-headless/lib:/usr/local/lib/chromium-headless:${LD_LIBRARY_PATH:-}"
export FONTCONFIG_PATH="/etc/fonts"
exec /usr/local/lib/chromium-headless/chromium-bin \
  --no-sandbox \
  --disable-setuid-sandbox \
  --disable-dev-shm-usage \
  --use-gl=angle \
  --use-angle=swiftshader \
  --enable-unsafe-swiftshader \
  "$@"
WRAP
    sudo chmod 755 /usr/local/bin/chromium
    sudo ln -sf /usr/local/bin/chromium /usr/local/bin/chromium-browser
  fi
  popd >/dev/null
  sudo rm -rf "$TMP_BIN"
fi

echo "=== [3/5] Checking Studio Fonts ==="
if [ -d "$REPO_ROOT/assets/fonts" ]; then
  sudo mkdir -p /usr/local/share/fonts/truetype/studio
  sudo cp -f "$REPO_ROOT/assets/fonts/"*.ttf /usr/local/share/fonts/truetype/studio/ 2>/dev/null || true
fi

echo "=== [4/5] Checking Node.js & Remotion Dependencies ==="
if [ ! -d "$REPO_ROOT/node_modules/remotion" ]; then
  npm install --no-audit --no-fund
fi

echo "=== [5/5] Running System Verification ==="
python3 "$REPO_ROOT/scripts/inspect_system.py"
echo "Environment setup & verification complete!"
