# Video Creation — Hindi YouTube Production Workspace

Production environment for **Ronny Raj**'s Hindi education channel:
book summaries, self-improvement, productivity, psychology, motivation,
documentaries, plus Shorts derived from long-form videos.

The environment is ready and verified. Start here:

- **Workspace guide** → [`youtube_workspace/README.md`](youtube_workspace/README.md)
- **Capability audit & limits** → [`youtube_workspace/documentation/ENVIRONMENT_AUDIT.md`](youtube_workspace/documentation/ENVIRONMENT_AUDIT.md)
- **Tool reference** → [`youtube_workspace/documentation/TOOLS.md`](youtube_workspace/documentation/TOOLS.md)
- **Production workflow** → [`youtube_workspace/documentation/WORKFLOW.md`](youtube_workspace/documentation/WORKFLOW.md)
- **New session / resume** → [`youtube_workspace/documentation/RESUME.md`](youtube_workspace/documentation/RESUME.md)

## 60-second start

```bash
python3 -m venv /home/user/Video-creation-/.venv
/home/user/Video-creation-/.venv/bin/pip install -r youtube_workspace/requirements.txt

cd /home/user/Video-creation-/youtube_workspace
PY=/home/user/Video-creation-/.venv/bin/python

$PY automation/check_env.py        # verify everything
$PY automation/newproject.py --id my_first_video --type book_summary --title "मेरी पहली वीडियो"
$PY automation/projector.py build projects/my_first_video/project.json --draft
```

## Stack

FFmpeg 7.0.2 (bundled) · PyAV · Pillow · HarfBuzz + FreeType for correct Devanagari ·
fontTools · numpy/scipy · soundfile · pysubs2 · srt — all free and open source,
installed from PyPI wheels. No paid services, no browser, no stock subscriptions.

## Status

| Item | State |
|---|---|
| Environment | verified — `check_env.py` all green |
| Tests | 16/16 passing (`python youtube_workspace/tests/test_pipeline.py`) |
| Demo render | `youtube_workspace/rendered_videos/demo_productivity.mp4` (79.8 s, 1080p30, silent by design) |
| Templates | 12 (6 script types, thumbnail, VO, QC, 3 project files) |
| Automation | 11 modules |
| Voice-over | via Arena speech tool or your recording — no in-sandbox TTS (see audit) |
