"""
newproject.py — scaffold a new video project in one command.

    python newproject.py --id book_deep_work --type book_summary \
        --title "Deep Work की समरी" --mood reflective

Creates:
    projects/<id>/project.json        timeline skeleton (edit this)
    projects/<id>/script.md           script template for the video type
    projects/<id>/voiceover/          drop s01.wav … here
    projects/<id>/research.md         source log
    projects/<id>/thumb.json          thumbnail brief

Types: longform · book_summary · self_improvement · motivational · documentary · shorts
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
TPL = os.path.join(ROOT, "templates")

TYPES = {
    "longform": ("script.longform.md", "longform", "longform_1080p30", "reflective"),
    "book_summary": ("script.book_summary.md", "longform", "longform_1080p30", "reflective"),
    "self_improvement": ("script.self_improvement.md", "longform", "longform_1080p30", "inspiring"),
    "motivational": ("script.motivational_story.md", "longform", "longform_1080p30", "inspiring"),
    "documentary": ("script.documentary.md", "longform", "longform_1080p30", "reflective"),
    "shorts": ("script.shorts.md", "short", "shorts_1080x1920", "upbeat"),
}


def scaffold(pid: str, vtype: str, title: str, mood: str | None = None,
             scenes: int = 8, overwrite: bool = False) -> str:
    if vtype not in TYPES:
        raise SystemExit(f"unknown type {vtype!r}; choose from {sorted(TYPES)}")
    script_tpl, fmt, preset, default_mood = TYPES[vtype]
    pdir = os.path.join(ROOT, "projects", pid)
    if os.path.exists(pdir) and not overwrite:
        raise SystemExit(f"{pdir} already exists — use --overwrite to refresh it")
    os.makedirs(os.path.join(pdir, "voiceover"), exist_ok=True)

    shutil.copyfile(os.path.join(TPL, script_tpl), os.path.join(pdir, "script.md"))

    n = 4 if fmt == "short" else scenes
    scene_defaults = _scene_skeleton(n, fmt)
    project = {
        "project": {
            "id": pid,
            "title": title,
            "category": vtype,
            "audience": "हिन्दी भाषी दर्शक",
            "promise": "",
            "format": fmt,
            "preset": preset,
            "music": {"mood": mood or default_mood, "gain_db": -26 if fmt == "longform" else -24},
        },
        "sources": [],
        "scenes": scene_defaults,
    }
    with open(os.path.join(pdir, "project.json"), "w", encoding="utf-8") as fh:
        json.dump(project, fh, ensure_ascii=False, indent=2)

    with open(os.path.join(pdir, "research.md"), "w", encoding="utf-8") as fh:
        fh.write(f"# Research log — {title}\n\n"
                 "| # | दावा | स्रोत / लिंक | भरोसा (उच्च/मध्यम/कम) | जाँचा |\n"
                 "|---|---|---|---|---|\n| 1 | | | | |\n\n"
                 "## जो अनिश्चित है\n- \n\n## जो अपनी राय है (स्रोत नहीं)\n- \n")

    with open(os.path.join(pdir, "thumb.json"), "w", encoding="utf-8") as fh:
        json.dump({"headline": title[:26], "kicker": vtype.upper().replace("_", " "),
                   "badge": "हिन्दी", "layout": "statement"}, fh,
                  ensure_ascii=False, indent=2)

    os.makedirs(os.path.join(ROOT, "scripts"), exist_ok=True)
    shutil.copyfile(os.path.join(pdir, "script.md"),
                    os.path.join(ROOT, "scripts", f"{pid}.md"))
    print(pdir)
    return pdir


def _scene_skeleton(n: int, fmt: str) -> list[dict]:
    if fmt == "short":
        heads = ["Hook", "विचार", "कदम", "अंत"]
    else:
        heads = ["Hook", "समस्या", "मुख्य विचार 1", "उदाहरण", "मुख्य विचार 2",
                 "आपत्ति / सीमा", "व्यावहारिक कदम", "निष्कर्ष", "अतिरिक्त 1", "अतिरिक्त 2"]
    out = []
    for i in range(n):
        head = heads[i] if i < len(heads) else f"सीन {i+1}"
        kind = "title" if i in (0, n - 1) else "bullets"
        visual = {"type": kind}
        if kind == "title":
            visual.update({"title": head, "subtitle": ""})
        else:
            visual.update({"heading": head, "items": ["", "", ""]})
        out.append({"id": f"s{i+1:02d}", "narration": "", "visual": visual,
                    "motion": "zoom_in" if i % 2 == 0 else "pan_left", "sfx": []})
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Scaffold a new video project")
    ap.add_argument("--id", required=True, help="short slug, e.g. book_deep_work")
    ap.add_argument("--type", default="longform", choices=sorted(TYPES))
    ap.add_argument("--title", required=True)
    ap.add_argument("--mood", default=None,
                    help="calm | reflective | inspiring | tense | upbeat")
    ap.add_argument("--scenes", type=int, default=8)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()
    pid = re.sub(r"[^a-z0-9_\-]", "_", args.id.lower())
    scaffold(pid, args.type, args.title, args.mood, args.scenes, args.overwrite)


if __name__ == "__main__":
    main()
