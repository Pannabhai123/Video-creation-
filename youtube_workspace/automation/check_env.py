"""
check_env.py — verify the production environment in one command.

Run this at the start of any new session (or after a rebuild) to confirm that
every tool the pipeline depends on is present and working — not merely importable.

    python automation/check_env.py            # human summary
    python automation/check_env.py --json     # machine-readable
    python automation/check_env.py --strict   # exit 1 if any required tool is missing
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REPO = os.path.dirname(ROOT)

REQUIRED_DIRS = [
    "research", "scripts", "book_summaries", "voiceovers", "music", "sound_effects",
    "images", "generated_assets", "stock_footage", "thumbnails", "subtitles",
    "projects", "rendered_videos", "shorts", "templates", "presets", "automation",
    "documentation", "quality_reports", "assets/fonts",
]

FONTS = [
    "NotoSansDevanagari-400.ttf", "NotoSansDevanagari-700.ttf",
    "Mukta-ExtraBold.ttf", "Poppins-Bold.ttf",
]

FONTS_PERMISSIVE_PATHS = ["/usr/share/fonts", os.path.expanduser("~/.fonts"), os.path.expanduser("~/.local/share/fonts")]


def _python_dep(mod: str, attr: str = "__version__") -> tuple[bool, str]:
    try:
        m = __import__(mod)
        v = getattr(m, attr, None)
        return True, str(v) if v else "ok"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def _ffmpeg() -> dict:
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": str(exc)}
    try:
        out = subprocess.run([exe, "-version"], capture_output=True, text=True, timeout=20).stdout
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "detail": str(exc)}
    first = out.splitlines()[0] if out else ""
    feats = {k: (k in out) for k in ("libass", "libx264", "libfreetype", "libfribidi",
                                     "libmp3lame", "libopus", "loudnorm")}
    return {"ok": k_ok(out), "detail": first, "features": feats, "exe": exe}


def k_ok(out: str) -> bool:
    return "ffmpeg version" in out


def check() -> dict:
    report: dict = {"repo": REPO, "workspace": ROOT, "python": sys.version.split()[0],
                    "tools": {}, "dirs": {}, "fonts": {}, "system": {}}

    for mod in ("av", "imageio_ffmpeg", "PIL", "uharfbuzz", "freetype", "numpy",
                "soundfile", "scipy", "srt", "pysubs2", "moviepy", "fontTools",
                "cv2", "ai_edge_litert"):
        ok, v = _python_dep(mod)
        report["tools"][mod] = {"ok": ok, "version": v}

    report["tools"]["ffmpeg"] = _ffmpeg()

    # system binaries we *use* but do not require
    for b in ("git", "node", "npm", "curl", "jq", "gh"):
        path = shutil.which(b)
        report["system"][b] = {"ok": bool(path), "path": path or ""}

    for d in REQUIRED_DIRS:
        p = os.path.join(ROOT, d)
        report["dirs"][d] = os.path.isdir(p)

    for f in FONTS:
        p = os.path.join(ROOT, "assets", "fonts", f)
        report["fonts"][f] = os.path.exists(p)

    # NEURAL MODELS (live-photo / 2.5D parallax)
    try:
        import aivision
        report["neural"] = {"ok": all(aivision.available().values()),
                            "models": aivision.available()}
    except Exception as exc:  # noqa: BLE001
        report["neural"] = {"ok": False, "models": {}, "detail": f"{type(exc).__name__}: {exc}"}

    # Devanagari shaping smoke test
    try:
        sys.path.insert(0, HERE)
        from hinditext import HindiText
        t = HindiText("deva-bold", 48)
        w_conjunct = t.measure_line("कर्म")
        w_plain = t.measure_line("करम")
        report["shaping"] = {"ok": abs(w_conjunct - w_plain) > 0.5,
                             "detail": f"कर्म={w_conjunct:.1f}px करम={w_plain:.1f}px "
                                       "(differ => conjunct shaping active)"}
    except Exception as exc:  # noqa: BLE001
        report["shaping"] = {"ok": False, "detail": f"{type(exc).__name__}: {exc}"}

    neural_ok = report.get("neural", {}).get("ok", False)
    report["ok"] = (neural_ok
                    and all(v["ok"] for v in report["tools"].values())
                    and all(report["dirs"].values())
                    and all(report["fonts"].values())
                    and report["shaping"]["ok"])
    return report


def human(r: dict) -> str:
    L = []
    L.append(f"Environment check — {r['repo']}")
    L.append(f"Python {r['python']} | workspace {r['workspace']}")
    L.append("")
    L.append(f"{'tool':<18} {'status':<8} version/detail")
    L.append("-" * 78)
    for name, d in r["tools"].items():
        status = "OK" if d["ok"] else "MISSING"
        L.append(f"{name:<18} {status:<8} {str(d.get('version') or d.get('detail',''))[:52]}")
    ff = r["tools"].get("ffmpeg", {})
    if ff.get("features"):
        have = [k for k, v in ff["features"].items() if v]
        L.append(f"  ffmpeg features: {', '.join(have)}")
    L.append("")
    L.append("System binaries (optional): " +
             ", ".join(f"{k}{'' if v['ok'] else ' (absent)'}" for k, v in r["system"].items()))
    L.append("")
    missing_dirs = [k for k, v in r["dirs"].items() if not v]
    L.append(f"Workspace folders: {len(r['dirs']) - len(missing_dirs)}/{len(r['dirs'])} present"
             + (f" — missing {missing_dirs}" if missing_dirs else ""))
    missing_fonts = [k for k, v in r["fonts"].items() if not v]
    L.append(f"Fonts: {len(r['fonts']) - len(missing_fonts)}/{len(r['fonts'])} present"
             + (f" — missing {missing_fonts}" if missing_fonts else ""))
    L.append(f"Devanagari shaping: {'OK' if r['shaping']['ok'] else 'FAIL'} — {r['shaping']['detail']}")
    n = r.get("neural", {})
    mid = [k for k, v in (n.get("models") or {}).items() if v]
    L.append(f"Neural models: {'OK' if n.get('ok') else 'MISSING'} — {', '.join(mid) or n.get('detail','none')}")
    L.append("")
    L.append("RESULT: " + ("all required components available ✅" if r["ok"] else "problems found ❌"))
    return "\n".join(L)


def main() -> None:
    r = check()
    if "--json" in sys.argv:
        print(json.dumps(r, indent=2))
    else:
        print(human(r))
    if "--strict" in sys.argv and not r["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
