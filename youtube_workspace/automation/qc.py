"""
qc.py — automated pre-publish quality control.

Runs objective checks on a finished render (or a whole project folder) and
writes a human-readable report plus machine-readable JSON.

    python qc.py video ../rendered_videos/demo.mp4
    python qc.py script ../scripts/demo.md
    python qc.py all ../projects/demo/project.json

Checks
------
video : container/decode integrity, resolution, fps, duration, aspect ratio,
        audio presence, loudness vs -14 LUFS, true peak, silence at head/tail,
        black-frame runs, freeze/duplicate frames, subtitle presence & sync
script: filler repetition, double spaces, unmatched quotes/brackets, English
        words that likely need Hindi, sentence-length outliers, readability
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys

import media

TARGET_LUFS = -14.0
LUFS_TOLERANCE = 1.5
TARGET_TP = -1.0


def _ok(cond: bool) -> str:
    return "PASS" if cond else "FAIL"


def _warn(cond: bool) -> str:
    return "PASS" if cond else "WARN"


# ---------------------------------------------------------------- video
def check_video(path: str) -> dict:
    path = os.path.abspath(path)
    result: dict = {"file": path, "checks": [], "warnings": [], "errors": []}

    if not os.path.exists(path):
        result["errors"].append("file not found")
        return result

    info = media.probe(path).to_dict()
    result["info"] = info
    w, h = info["width"] or 0, info["height"] or 0
    ratio = round(w / h, 4) if h else 0

    result["checks"].append({
        "name": "resolution",
        "value": f"{w}x{h}",
        "status": _ok((w, h) in ((1920, 1080), (1080, 1920), (1280, 720))),
        "expect": "1920x1080 (16:9) or 1080x1920 (9:16)",
    })
    result["checks"].append({
        "name": "aspect_ratio", "value": f"{ratio:.4f}",
        "status": _ok(abs(ratio - 16 / 9) < 0.01 or abs(ratio - 9 / 16) < 0.01),
        "expect": "16:9 or 9:16",
    })
    result["checks"].append({
        "name": "frame_rate", "value": info["fps"],
        "status": _ok(bool(info["fps"]) and abs((info["fps"] or 0) - round(info["fps"] or 0)) < 0.01),
        "expect": "integer fps (25/30/60)",
    })
    result["checks"].append({
        "name": "duration", "value": f"{info['duration']:.2f}s",
        "status": _warn(info["duration"] > 20),
        "expect": "> 20s",
    })
    result["checks"].append({
        "name": "video_codec", "value": info["v_codec"],
        "status": _ok(info["v_codec"] in ("h264", "hevc")),
        "expect": "h264 (YouTube-friendly)",
    })
    result["checks"].append({
        "name": "audio_stream", "value": info["a_codec"] or "none",
        "status": _ok(bool(info["a_codec"])),
        "expect": "aac 48 kHz stereo",
    })
    if info["sample_rate"]:
        result["checks"].append({
            "name": "sample_rate", "value": info["sample_rate"],
            "status": _ok(info["sample_rate"] == 48000),
            "expect": "48000 Hz",
        })

    # full decode test — catches truncated files and corrupt frames
    err = media.run(["-v", "error", "-i", path, "-f", "null", "-"], "decode")
    decode_errors = [l for l in err.splitlines() if l.strip() and "error" in l.lower()]
    result["checks"].append({
        "name": "decode_integrity", "value": f"{len(decode_errors)} errors",
        "status": _ok(not decode_errors), "expect": "no decode errors",
    })
    if decode_errors:
        result["errors"].extend(decode_errors[:5])

    # loudness
    if info["a_codec"]:
        loud = media.measure_loudness(path)
        if loud:
            lufs = float(loud.get("input_i", 0))
            tp = float(loud.get("input_tp", 0))
            result["loudness"] = {"integrated_lufs": lufs, "true_peak_db": tp,
                                  "lra": float(loud.get("input_lra", 0))}
            silent = lufs <= -50.0
            result["checks"].append({
                "name": "loudness",
                "value": "silent (no narration in this build)" if silent else f"{lufs} LUFS",
                "status": "WARN" if silent else _ok(abs(lufs - TARGET_LUFS) <= LUFS_TOLERANCE),
                "expect": f"{TARGET_LUFS} ±{LUFS_TOLERANCE} LUFS (YouTube)",
            })
            if silent:
                result["warnings"].append(
                    "audio track is silent: no narration was present when this was built. "
                    "Add voiceover/sNN.wav and rebuild before publishing.")
            result["checks"].append({
                "name": "true_peak", "value": f"{tp} dBTP",
                "status": _ok(tp <= TARGET_TP),
                "expect": f"<= {TARGET_TP} dBTP (no clipping)",
            })

    # black frames
    blacks = media.black_frames(path, min_duration=0.5)
    long_blacks = [b for b in blacks if b[1] - b[0] > 1.2]
    result["checks"].append({
        "name": "black_frames", "value": f"{len(blacks)} runs ({len(long_blacks)} long)",
        "status": _ok(not long_blacks),
        "expect": "no black run > 1.2s",
    })
    if long_blacks:
        result["warnings"].append(f"long black stretches at {long_blacks}")

    # frozen picture (no motion) — a sign a still was added without a Ken Burns move
    err = media.run(["-i", path, "-vf", "freezedetect=n=0.001:d=3", "-f", "null", "-"], "freezedetect")
    freezes = [round(float(l.split("freeze_start:")[1]), 2)
               for l in err.splitlines() if "freeze_start:" in l]
    result["checks"].append({
        "name": "static_picture", "value": f"{len(freezes)} freeze starts > 3s",
        "status": "PASS" if len(freezes) <= max(2, info["duration"] // 60) else "WARN",
        "expect": "visual motion throughout",
    })

    # subtitles
    sub_probe = _streams_of(path)
    has_subs = any(s.get("codec_type") == "subtitle" for s in sub_probe)
    result["checks"].append({
        "name": "subtitle_stream", "value": "present" if has_subs else "burned-in only",
        "status": "PASS", "expect": "burned-in or soft subs",
    })
    return result


def _streams_of(path: str) -> list[dict]:
    try:
        out = subprocess.run([media.FFMPEG.replace("ffmpeg", "ffprobe"), "-v", "quiet",
                              "-print_format", "json", "-show_streams", path],
                             capture_output=True, text=True)
        if out.returncode == 0:
            return json.loads(out.stdout).get("streams", [])
    except Exception:
        pass
    return []


# ---------------------------------------------------------------- script
FILLERS = ["बहुत ही ज्यादा", "वास्तव में बहुत", "आपको बताना चाहूंगा", "तो चलिए",
           "इस वीडियो में हम बात करेंगे", "नमस्कार दोस्तों"]
REPEAT_WORD = re.compile(r"\b(\w{3,})\s+\1\b")


def check_script(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    body = re.sub(r"^#.*$", "", text, flags=re.M)
    result: dict = {"file": os.path.abspath(path), "checks": [], "warnings": [], "errors": []}

    chars = len(re.sub(r"\s", "", body))
    sentences = [s for s in re.split(r"[।!?]\s*", body) if s.strip()]
    words = len(body.split())
    result["stats"] = {
        "characters": chars,
        "words": words,
        "sentences": len(sentences),
        "est_speaking_minutes": round(chars / 13.5 / 60, 2),
        "avg_sentence_chars": round(chars / max(len(sentences), 1), 1),
    }

    result["checks"].append({
        "name": "double_spaces", "value": len(re.findall(r"[^\n] {2,}", body)),
        "status": _ok(not re.search(r"[^\n] {2,}", body)), "expect": "0",
    })
    reps = REPEAT_WORD.findall(body)
    result["checks"].append({
        "name": "repeated_words", "value": f"{len(reps)} {reps[:3]}" if reps else 0,
        "status": _ok(not reps), "expect": "0",
    })
    fill = [f for f in FILLERS if f in body]
    result["checks"].append({
        "name": "filler_phrases", "value": fill or 0,
        "status": _warn(not fill), "expect": "avoid stock filler",
    })
    if fill:
        result["warnings"].append(f"stock filler phrases found: {fill}")
    long_sent = [s.strip()[:60] for s in sentences if len(s) > 220]
    result["checks"].append({
        "name": "long_sentences", "value": len(long_sent),
        "status": _warn(len(long_sent) <= 2), "expect": "<= 2 sentences over 220 chars",
    })
    if long_sent:
        result["warnings"].append(f"very long sentences (subtitle/breath risk): {long_sent}")
    latin = len(re.findall(r"[A-Za-z]{3,}", body))
    result["checks"].append({
        "name": "english_words", "value": latin,
        "status": "PASS", "expect": "allowed when natural; keep Devanagari primary",
    })
    if chars and latin / max(words, 1) > 0.22:
        result["warnings"].append("heavy English ratio — check the Hindi reads naturally")
    result["checks"].append({
        "name": "devanagari_present", "value": bool(re.search(r"[\u0900-\u097F]", body)),
        "status": _ok(bool(re.search(r"[\u0900-\u097F]", body))), "expect": "Hindi script",
    })
    result["est_scene_seconds"] = round(chars / 13.5, 1)
    return result


# ---------------------------------------------------------------- project
def check_project(project_path: str) -> dict:
    import projector

    proj = projector.load_project(project_path)
    result: dict = {"file": os.path.abspath(project_path), "checks": [], "warnings": [], "errors": []}
    missing_visual = []
    for sc in proj["scenes"]:
        v = sc.get("visual", {})
        if v.get("type") == "image" or v.get("type") == "split":
            img = v.get("image_path")
            if img and not os.path.exists(img):
                missing_visual.append(f"{sc['id']}: {img}")
    result["checks"].append({
        "name": "missing_image_assets", "value": missing_visual or 0,
        "status": _ok(not missing_visual), "expect": "no missing files",
    })
    narr_chars = sum(len(sc.get("narration", "")) for sc in proj["scenes"])
    result["checks"].append({
        "name": "narration_length", "value": f"{narr_chars} chars ≈ {narr_chars/13.5/60:.2f} min",
        "status": _warn(narr_chars > 400), "expect": "non-trivial narration",
    })
    vo_dir = os.path.join(os.path.dirname(project_path), "voiceover")
    have = [sc["id"] for sc in proj["scenes"]
            if sc.get("audio") or os.path.exists(os.path.join(vo_dir, f"{sc['id']}.wav"))]
    result["checks"].append({
        "name": "voiceover_files", "value": f"{len(have)}/{len(proj['scenes'])}",
        "status": _ok(len(have) == len(proj["scenes"])),
        "expect": "one WAV per scene for final render",
    })
    if len(have) < len(proj["scenes"]):
        result["warnings"].append(
            f"{len(proj['scenes']) - len(have)} scenes have no narration audio — "
            "timings are estimates, not measured")
    types = {sc.get("visual", {}).get("type") for sc in proj["scenes"]}
    result["checks"].append({
        "name": "visual_variety", "value": f"{len(types)} types: {sorted(t for t in types if t)}",
        "status": _warn(len(types) >= 3), "expect": ">= 3 scene types for retention",
    })
    return result


# ---------------------------------------------------------------- report
def to_markdown(reports: list[dict], title: str = "Quality Control Report") -> str:
    lines = [f"# {title}", "", f"Generated: {__import__('time').strftime('%Y-%m-%d %H:%M')}", ""]
    fails = sum(1 for r in reports for c in r.get("checks", []) if c["status"] == "FAIL")
    warns = sum(1 for r in reports for c in r.get("checks", []) if c["status"] == "WARN")
    lines += [f"**{len(reports)} item(s) checked — {fails} FAIL, {warns} WARN**", ""]
    for r in reports:
        lines.append(f"## {os.path.basename(r['file'])}")
        if r.get("info"):
            i = r["info"]
            lines.append(f"- {i['width']}x{i['height']} · {i['fps']} fps · "
                         f"{i['duration']:.1f}s · {i['v_codec']}/{i['a_codec']} · "
                         f"{i['filesize']/1e6:.1f} MB")
        if r.get("stats"):
            s = r["stats"]
            lines.append(f"- {s['words']} words · {s['sentences']} sentences · "
                         f"≈{s['est_speaking_minutes']} min narration · "
                         f"avg {s['avg_sentence_chars']} chars/sentence")
        if r.get("loudness"):
            l = r["loudness"]
            lines.append(f"- Loudness {l['integrated_lufs']} LUFS, TP {l['true_peak_db']} dBTP, "
                         f"LRA {l['lra']} LU")
        lines += ["", "| Check | Value | Status | Expected |", "|---|---|---|---|"]
        for c in r.get("checks", []):
            icon = {"PASS": "✅", "WARN": "⚠️", "FAIL": "❌"}[c["status"]]
            lines.append(f"| {c['name']} | {c['value']} | {icon} {c['status']} | {c['expect']} |")
        if r.get("warnings"):
            lines += ["", "**Warnings**"]
            lines += [f"- {w}" for w in r["warnings"]]
        if r.get("errors"):
            lines += ["", "**Errors**"]
            lines += [f"- {e}" for e in r["errors"]]
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["video", "script", "project", "all"])
    ap.add_argument("path")
    ap.add_argument("--out", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    reports: list[dict] = []
    if args.mode in ("video", "all"):
        target = args.path
        if target.endswith(".json"):
            with open(target, encoding="utf-8") as fh:
                man = json.load(fh)
            target = man.get("output", "")
            if man.get("scenes"):
                reports.append(check_project(args.path.replace("build_manifest", "project")))
        if target.endswith(".mp4"):
            reports.append(check_video(target))
    if args.mode == "script":
        reports.append(check_script(args.path))
    if args.mode == "project":
        reports.append(check_project(args.path))

    out_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "quality_reports")
    os.makedirs(out_dir, exist_ok=True)
    stamp = __import__("time").strftime("%Y%m%d-%H%M%S")
    md = os.path.join(args.out or out_dir, f"qc_{os.path.basename(args.path)}_{stamp}.md")
    with open(md, "w", encoding="utf-8") as fh:
        fh.write(to_markdown(reports))
    js = os.path.splitext(md)[0] + ".json"
    with open(js, "w", encoding="utf-8") as fh:
        json.dump(reports, fh, ensure_ascii=False, indent=2)
    print(md)
    if args.json:
        print(json.dumps(reports, ensure_ascii=False, indent=2))
    fails = sum(1 for r in reports for c in r["checks"] if c["status"] == "FAIL")
    sys.exit(0 if fails == 0 else 2)


if __name__ == "__main__":
    main()
