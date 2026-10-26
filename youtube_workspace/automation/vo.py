"""
vo.py — voice-over handling for a project.

Narration can arrive three ways:
  1. generated speech (Arena speech tool, any online TTS) — one file per scene
  2. your own microphone recording — one file per scene, or one long take
  3. a single continuous recording that must be cut per scene

This tool gets any of those into the layout the renderer expects:

    projects/<id>/voiceover/s01.wav, s02.wav, ...

and normalises levels so all scenes sit at the same loudness.

    # one file per scene, any format/names
    python vo.py import --project ../projects/demo/project.json --src ~/Downloads/vo

    # single long take split by detected silences into N scenes
    python vo.py split --project ../projects/demo/project.json --file take.mp3

    # consistency + readiness check
    python vo.py normalize --project ../projects/demo/project.json
    python vo.py check --project ../projects/demo/project.json
"""

from __future__ import annotations

import argparse
import json
import os
import shutil

import media

AUDIO_EXT = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".webm", ".aiff"}


def _project(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _vo_dir(project_path: str) -> str:
    d = os.path.join(os.path.dirname(os.path.abspath(project_path)), "voiceover")
    os.makedirs(d, exist_ok=True)
    return d


def _to_wav(src: str, dst: str) -> str:
    """Convert anything to 48 kHz mono-safe stereo WAV, trimmed of leading/trailing silence."""
    tmp = dst + ".tmp.wav"
    media.run(["-i", src, "-vn", "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", tmp], "vo convert")
    # trim > -45 dB silence at head/tail, keep a 120 ms breath pad
    media.run([
        "-i", tmp,
        "-af", "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.12,"
               "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.18,areverse",
        "-c:a", "pcm_s16le", dst,
    ], "vo trim")
    if os.path.exists(tmp):
        os.remove(tmp)
    return dst


def cmd_import(args) -> None:
    proj = _project(args.project)
    ids = [sc["id"] for sc in proj["scenes"]]
    src = os.path.abspath(args.src)
    files = sorted(
        (os.path.join(src, f) for f in os.listdir(src) if os.path.splitext(f)[1].lower() in AUDIO_EXT),
        key=lambda p: _natural_key(os.path.basename(p)),
    )
    if not files:
        raise SystemExit(f"no audio files found in {src}")
    if len(files) != len(ids):
        raise SystemExit(
            f"{len(files)} audio files but {len(ids)} scenes — rename files to the scene ids "
            f"({', '.join(ids)}) or use the 'split' command for a single take")
    out = _vo_dir(args.project)
    for sc_id, f in zip(ids, files):
        dst = os.path.join(out, f"{sc_id}.wav")
        _to_wav(f, dst)
        print(f"  {os.path.basename(f)} -> {os.path.basename(dst)}  {media.duration_of(dst):.2f}s")


def cmd_split(args) -> None:
    """Split one continuous take into N scenes at the N-1 longest silences."""
    proj = _project(args.project)
    ids = [sc["id"] for sc in proj["scenes"]]
    need = len(ids)
    src = os.path.abspath(args.file)
    total = media.duration_of(src)
    sil = media.silence_points(src, noise_db=args.noise_db, min_len=args.min_len)
    if len(sil) < need - 1:
        raise SystemExit(
            f"found only {len(sil)} pauses for {need - 1} cuts — lower --min-len, "
            "record with clearer pauses, or import per-scene files instead")
    ranked = sorted(sil, key=lambda s: -(s[1] - s[0]))[: need - 1]
    cuts = sorted(((a + b) / 2 for a, b in ranked))
    bounds = [0.0, *cuts, total]
    out = _vo_dir(args.project)
    for i, sc_id in enumerate(ids):
        dst = os.path.join(out, f"{sc_id}.wav")
        media.run(["-ss", f"{bounds[i]:.3f}", "-to", f"{bounds[i+1]:.3f}", "-i", src,
                   "-ac", "2", "-ar", "48000", "-c:a", "pcm_s16le", dst], "split")
        print(f"  {bounds[i]:6.2f}-{bounds[i+1]:6.2f}s -> {os.path.basename(dst)} "
              f"({media.duration_of(dst):.2f}s)")


def cmd_normalize(args) -> None:
    """Bring every scene to the same speech loudness so the edit has no jumps."""
    proj = _project(args.project)
    out = _vo_dir(args.project)
    for sc in proj["scenes"]:
        src = os.path.join(out, f"{sc['id']}.wav")
        if not os.path.exists(src):
            continue
        tmp = src + ".norm.wav"
        stats = media.loudness_normalise(src, tmp, target={"I": -16.0, "TP": -2.0, "LRA": 7.0},
                                         a_bitrate="192k")
        # loudness_normalise writes AAC; re-wrap to PCM for downstream concat
        media.run(["-i", tmp, "-c:a", "pcm_s16le", src.replace(".wav", ".n.wav")], "rewrap")
        os.replace(src.replace(".wav", ".n.wav"), src)
        os.remove(tmp)
        print(f"  {sc['id']}: {stats.get('input_i', '?')} -> -16 LUFS")


def cmd_check(args) -> None:
    proj = _project(args.project)
    out = _vo_dir(args.project)
    rows, missing = [], []
    for sc in proj["scenes"]:
        path = os.path.join(out, f"{sc['id']}.wav")
        est = round(len(sc.get("narration", "").replace(" ", "")) / 13.5, 2)
        if not os.path.exists(path):
            missing.append(sc["id"])
            rows.append((sc["id"], "MISSING", est, "—", "—"))
            continue
        info = media.probe(path)
        loud = media.measure_loudness(path)
        rows.append((sc["id"], "ok", est, round(info.duration, 2),
                     round(float(loud.get("input_i", 0)), 1)))
    print(f"{'scene':>6} {'state':>8} {'est_s':>7} {'real_s':>7} {'LUFS':>6}")
    for r in rows:
        print(f"{r[0]:>6} {r[1]:>8} {r[2]:>7} {r[3]:>7} {r[4]:>6}")
    if missing:
        print(f"\n{len(missing)} scene(s) still need narration: {', '.join(missing)}")
    else:
        print("\nAll scenes have narration — the next build will use measured timings.")


def _natural_key(name: str):
    import re
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def main() -> None:
    ap = argparse.ArgumentParser(description="Import / normalise / verify narration")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("import")
    p.add_argument("--project", required=True)
    p.add_argument("--src", required=True, help="folder of per-scene audio files")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("split")
    p.add_argument("--project", required=True)
    p.add_argument("--file", required=True, help="one continuous recording")
    p.add_argument("--noise-db", type=int, default=-33)
    p.add_argument("--min-len", type=float, default=0.30)
    p.set_defaults(func=cmd_split)

    p = sub.add_parser("normalize")
    p.add_argument("--project", required=True)
    p.set_defaults(func=cmd_normalize)

    p = sub.add_parser("check")
    p.add_argument("--project", required=True)
    p.set_defaults(func=cmd_check)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
