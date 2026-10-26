# Resuming in a new session

Arena re-attaches this repository to the conversation branch, so the workspace
usually comes back as it was. The venv and generated renders may not. Follow this
in order — it takes under a minute, and it tells you exactly what state you are in.

## 1. Confirm the workspace is here

```bash
ls /home/user/Video-creation-/youtube_workspace
git -C /home/user/Video-creation- log --oneline -3
```

If the folder is missing, the repo did not come back: clone it, then continue.

## 2. Recreate the Python environment (only if the check fails)

```bash
python3 -m venv /home/user/Video-creation-/.venv
/home/user/Video-creation-/.venv/bin/pip install -r \
  /home/user/Video-creation-/youtube_workspace/requirements.txt
```

## 3. Verify

```bash
cd /home/user/Video-creation-/youtube_workspace
/home/user/Video-creation-/.venv/bin/python automation/check_env.py
```

You want `RESULT: all required components available ✅`. If FFmpeg features are
missing or shaping fails, stop and read `README.md` → Troubleshooting; do not start
rendering on a broken setup.

## 4. See what already exists

```bash
ls projects/                 # projects and their state
ls rendered_videos/          # finished videos (gitignored, may be empty)
ls quality_reports/ | tail   # last QC results
git -C /home/user/Video-creation- status --short
```

For a specific project:

```bash
PY=/home/user/Video-creation-/.venv/bin/python
$PY automation/vo.py check  --project projects/<id>/project.json   # narration present?
$PY automation/projector.py plan projects/<id>/project.json        # timings + audio flags
```

The `plan` output tells you the truth in one screen: which scenes have audio, how
long each is, and what visual each uses.

## 5. Tell me this at the start of a new chat

Paste the block below so I pick up with zero guesswork:

```
PROJECT: YouTube Education Content Production — Ronny Raj (Hindi)
WORKSPACE: /home/user/Video-creation-/youtube_workspace (git branch arena/...)
STATE: <run `check_env.py` and paste the RESULT line>
ACTIVE PROJECT: <project id, or "none">
NEXT STEP: <research / script / narration / build / QC / publish>
```

## 6. What I will check before touching anything

1. `automation/check_env.py` — environment intact?
2. `projects/<id>/build_manifest.json` — what was last built, and when?
3. `quality_reports/` — were the last QC issues fixed?
4. `render.md`-style notes inside the project folder, if present.

## Known environment facts to remember (do not re-test blindly)

- `apt-get` cannot reach Debian mirrors; do not try to install system packages.
- `raw.githubusercontent.com` and GitHub **release assets** are blocked;
  `api.github.com` works — that is how fonts are fetched.
- Hugging Face is unreachable → no Whisper, no Piper models.
- Cloud TTS endpoints are unreachable → narration via Arena's speech tool or your mic.
- Everything else (FFmpeg, PyAV, Pillow, HarfBuzz, fonts) comes from PyPI wheels.

## If the repository itself is gone

Rebuild the whole workspace from scratch with me: I regenerate the automation
modules and templates, then you re-add `assets/fonts` with:

```bash
cd youtube_workspace/assets/fonts
gh api repos/google/fonts/contents/ofl/mukta/Mukta-ExtraBold.ttf --jq .content | base64 -d > Mukta-ExtraBold.ttf
# …repeat per font; licences in ./licenses/
```
Then `pip install -r requirements.txt` and `check_env.py` again.
