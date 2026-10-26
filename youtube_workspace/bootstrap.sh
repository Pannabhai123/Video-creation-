#!/usr/bin/env bash
# bootstrap.sh — rebuild the whole working environment in one command.
#
# Use this at the start of every new chat/session: the workspace code, templates,
# fonts and docs persist (they are in git), but the Python environment (.venv)
# does NOT survive a new sandbox. This script recreates it in ~15 seconds and
# verifies everything.
#
#   bash youtube_workspace/bootstrap.sh            # setup + verify
#   bash youtube_workspace/bootstrap.sh --test     # setup + verify + run test suite
#   bash youtube_workspace/bootstrap.sh --force    # recreate the venv from scratch

set -uo pipefail

WS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(dirname "$WS")"
VENV="$REPO/.venv"
PY="$VENV/bin/python"
RUN_TESTS=0
FORCE=0

for arg in "$@"; do
  case "$arg" in
    --test) RUN_TESTS=1 ;;
    --force) FORCE=1 ;;
    -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}"; exit 0 ;;
  esac
done

say() { printf '%s\n' "$*"; }
fail() { printf '\n✗ %s\n' "$*" >&2; exit 1; }

say "Repository : $REPO"
say "Workspace  : $WS"

# ---------------------------------------------------------------- 1. python
if ! command -v python3 >/dev/null 2>&1; then
  fail "python3 not found — this environment cannot run the pipeline"
fi
say "Python     : $(python3 --version 2>&1)"

# ---------------------------------------------------------------- 2. venv
if [ "$FORCE" -eq 1 ] && [ -d "$VENV" ]; then
  say "→ removing existing venv (--force)"
  rm -rf "$VENV"
fi

NEED_INSTALL=0
if [ ! -x "$PY" ]; then
  say "→ creating venv at $VENV"
  python3 -m venv "$VENV" || fail "could not create the venv"
  NEED_INSTALL=1
fi

if [ "$NEED_INSTALL" -eq 0 ]; then
  # existing venv: confirm the critical imports still work
  if ! "$PY" -c "import av, PIL, uharfbuzz, soundfile, scipy, srt, pysubs2, imageio_ffmpeg" 2>/dev/null; then
    say "→ venv exists but packages are incomplete; reinstalling"
    NEED_INSTALL=1
  fi
fi

# ---------------------------------------------------------------- 3. packages
if [ "$NEED_INSTALL" -eq 1 ]; then
  say "→ installing packages from requirements.txt (pip, ~10–20 s)"
  "$PY" -m pip install --quiet --upgrade pip >/dev/null 2>&1
  if ! "$PY" -m pip install --quiet -r "$WS/requirements.txt"; then
    fail "pip install failed — check that pypi.org is reachable in this sandbox"
  fi
  say "  packages installed"
else
  say "  packages already present — skipping install"
fi

# ---------------------------------------------------------------- 4. folders
# git does not track empty directories, so recreate the skeleton every time.
REQUIRED_DIRS="research scripts book_summaries voiceovers music sound_effects images
generated_assets stock_footage thumbnails subtitles projects rendered_videos shorts
templates presets automation documentation quality_reports assets/fonts assets/brand tests"
CREATED=0
for d in $REQUIRED_DIRS; do
  if [ ! -d "$WS/$d" ]; then
    mkdir -p "$WS/$d"
    CREATED=$((CREATED + 1))
  fi
  # keep the folder tracked by git (git ignores empty directories)
  case "$d" in assets/*|automation|documentation|templates|presets|tests) ;; *)
    [ -f "$WS/$d/.gitkeep" ] || touch "$WS/$d/.gitkeep" ;;
  esac
done
[ "$CREATED" -gt 0 ] && say "Folders    : recreated $CREATED missing folder(s)"

# ---------------------------------------------------------------- 5. fonts
FONT_COUNT=$(ls "$WS"/assets/fonts/*.ttf 2>/dev/null | wc -l | tr -d ' ')
if [ "${FONT_COUNT:-0}" -lt 4 ]; then
  fail "Devanagari fonts are missing from $WS/assets/fonts — see documentation/RESUME.md"
fi
say "Fonts      : $FONT_COUNT files"

# ---------------------------------------------------------------- 5b. models
MODEL_COUNT=$(ls "$WS"/assets/models/*.tflite 2>/dev/null | wc -l | tr -d ' ')
if [ "${MODEL_COUNT:-0}" -lt 2 ]; then
  say "Models     : restoring neural models from the mediapipe wheel"
  "$PY" "$WS/automation/restore_models.py" || say "  ! model restore failed — live-photo modes will be unavailable"
fi

# ---------------------------------------------------------------- 6. verify
say ""
say "────────────────────── environment check ──────────────────────"
if ! "$PY" "$WS/automation/check_env.py" --strict; then
  fail "environment check reported problems (see the table above)"
fi

if [ "$RUN_TESTS" -eq 1 ]; then
  say ""
  say "────────────────────── pipeline tests ─────────────────────────"
  "$PY" "$WS/tests/test_pipeline.py" || fail "tests failed"
fi

say ""
say "Ready. Next:"
say "  PY=$PY"
say "  cd $WS"
say "  \$PY automation/newproject.py --id my_video --type book_summary --title \"...\""
say "  \$PY automation/projector.py build projects/my_video/project.json --draft"
exit 0
