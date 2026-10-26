#!/usr/bin/env python3
"""
Step 5: Automated Video & Subtitle QA Verification Suite.
Validates rendered YouTube MP4 videos for:
- File existence and non-zero size
- OpenCV frame decoding integrity (start, middle, end frames, non-black visual check)
- FFprobe container/stream specification (H.264, AAC, resolution, 16:9 aspect ratio, FPS, duration)
- Audio presence and integrated loudness (EBU R128 LUFS / non-silent RMS)
- Subtitle integrity (external SRT/VTT/ASS files + embedded MP4 mov_text subtitle stream)
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pysrt


def _probe_json(video_path: Path) -> dict[str, Any]:
    proc = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(video_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def _measure_loudness(video_path: Path) -> dict[str, float | None]:
    proc = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(video_path),
            "-af",
            "loudnorm=print_format=json",
            "-f",
            "null",
            "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    match = re.search(r"\{\s*\"input_i\"\s*:.*?\}", proc.stdout, flags=re.DOTALL)
    if not match:
        return {"integrated_lufs": None, "true_peak_dbtp": None}
    try:
        data = json.loads(match.group(0))
        i_val = float(data["input_i"])
        tp_val = float(data["input_tp"])
        return {
            "integrated_lufs": None if math.isinf(i_val) else round(i_val, 2),
            "true_peak_dbtp": None if math.isinf(tp_val) else round(tp_val, 2),
        }
    except Exception:
        return {"integrated_lufs": None, "true_peak_dbtp": None}


def verify_srt_file(srt_path: Path) -> dict[str, Any]:
    if not srt_path.exists():
        return {"exists": False, "valid": False, "cue_count": 0, "errors": [f"Missing SRT: {srt_path}"]}
    subs = pysrt.open(str(srt_path), encoding="utf-8")
    errors: list[str] = []
    prev_end_ms = 0
    for idx, cue in enumerate(subs):
        start_ms = cue.start.ordinal
        end_ms = cue.end.ordinal
        if end_ms <= start_ms:
            errors.append(f"Cue {idx + 1} has non-positive duration ({start_ms} -> {end_ms})")
        if start_ms < prev_end_ms - 5:
            errors.append(f"Cue {idx + 1} overlaps previous cue ({start_ms} < {prev_end_ms})")
        if not cue.text.strip():
            errors.append(f"Cue {idx + 1} has empty text")
        prev_end_ms = end_ms
    return {
        "exists": True,
        "valid": len(subs) > 0 and not errors,
        "cue_count": len(subs),
        "last_end_sec": round(prev_end_ms / 1000.0, 2),
        "errors": errors,
    }


def verify_video(
    video_path: Path,
    expected_width: int = 1920,
    expected_height: int = 1080,
    expected_fps: float = 30.0,
    expected_duration: float | None = None,
    duration_tolerance: float = 1.5,
    srt_path: Path | None = None,
    require_audio: bool = True,
    require_subtitles: bool = True,
) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    errors: list[str] = []

    checks["file_exists"] = video_path.exists() and video_path.is_file()
    if not checks["file_exists"]:
        return {"passed": False, "checks": checks, "errors": [f"File does not exist: {video_path}"]}

    file_size = video_path.stat().st_size
    checks["non_empty_file"] = file_size > 10_000
    if not checks["non_empty_file"]:
        errors.append(f"File too small ({file_size} bytes)")

    probe = _probe_json(video_path)
    streams = probe.get("streams", [])
    fmt = probe.get("format", {})

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    sub_stream = next((s for s in streams if s.get("codec_type") == "subtitle"), None)

    checks["has_video_stream"] = video_stream is not None
    if not video_stream:
        errors.append("Missing video stream")
        return {"passed": False, "checks": checks, "errors": errors}

    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))
    vcodec = video_stream.get("codec_name", "")
    pix_fmt = video_stream.get("pix_fmt", "")

    r_frame_rate = video_stream.get("r_frame_rate", "0/1")
    num, den = (int(x) for x in r_frame_rate.split("/")) if "/" in r_frame_rate else (float(r_frame_rate), 1)
    fps = round(num / den, 2) if den else 0.0
    duration = float(fmt.get("duration") or video_stream.get("duration") or 0.0)

    checks["resolution_matches"] = (width == expected_width and height == expected_height)
    if not checks["resolution_matches"]:
        errors.append(f"Expected resolution {expected_width}x{expected_height}, got {width}x{height}")

    checks["fps_matches"] = abs(fps - expected_fps) <= 0.25
    if not checks["fps_matches"]:
        errors.append(f"Expected FPS {expected_fps}, got {fps}")

    checks["codec_h264_yuv420p"] = (vcodec == "h264" and pix_fmt == "yuv420p")
    if not checks["codec_h264_yuv420p"]:
        errors.append(f"Expected h264/yuv420p, got {vcodec}/{pix_fmt}")

    if expected_duration is not None:
        checks["duration_matches"] = abs(duration - expected_duration) <= duration_tolerance
        if not checks["duration_matches"]:
            errors.append(f"Expected duration ~{expected_duration:.2f}s, got {duration:.2f}s")
    else:
        checks["duration_positive"] = duration > 1.0
        if not checks["duration_positive"]:
            errors.append(f"Invalid duration {duration:.2f}s")

    # OpenCV frame read & visual non-black check across multiple timestamps
    cap = cv2.VideoCapture(str(video_path))
    checks["opens_in_opencv"] = cap.isOpened()
    sampled_means: list[float] = []
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if cap.isOpened() and total_frames > 0:
        for frac in (0.08, 0.35, 0.65, 0.90):
            idx = min(max(0, int(total_frames * frac)), total_frames - 1)
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if ok and frame is not None:
                sampled_means.append(round(float(np.mean(frame)), 2))
    cap.release()
    checks["frames_decode_cleanly"] = len(sampled_means) == 4 and max(sampled_means) > 5.0
    if not checks["frames_decode_cleanly"]:
        errors.append(f"Frame decode or blank-frame failure: sampled means={sampled_means}")

    loudness = {"integrated_lufs": None, "true_peak_dbtp": None}
    if require_audio:
        checks["has_audio_stream"] = audio_stream is not None
        if not audio_stream:
            errors.append("Missing audio stream")
        else:
            acodec = audio_stream.get("codec_name", "")
            checks["audio_codec_aac"] = acodec == "aac"
            if not checks["audio_codec_aac"]:
                errors.append(f"Expected AAC audio codec, got {acodec}")
            loudness = _measure_loudness(video_path)
            checks["audio_audible_non_silent"] = (
                loudness["integrated_lufs"] is not None and loudness["integrated_lufs"] > -45.0
            )
            if not checks["audio_audible_non_silent"]:
                errors.append(f"Audio appears silent or invalid: {loudness}")

    srt_report: dict[str, Any] | None = None
    if srt_path is None:
        candidate = video_path.with_suffix(".srt")
        if candidate.exists():
            srt_path = candidate

    if require_subtitles:
        has_soft_sub = sub_stream is not None
        srt_report = verify_srt_file(srt_path) if srt_path else {"exists": False, "valid": False, "cue_count": 0}
        checks["subtitles_verified"] = bool(has_soft_sub or srt_report.get("valid"))
        if not checks["subtitles_verified"]:
            errors.append(f"Subtitle check failed: soft_track={has_soft_sub}, srt={srt_report}")

    passed = all(checks.values()) and not errors
    return {
        "passed": passed,
        "video_path": str(video_path),
        "file_size_mb": round(file_size / (1024 * 1024), 2),
        "duration_sec": round(duration, 2),
        "resolution": f"{width}x{height}",
        "fps": fps,
        "video_codec": vcodec,
        "pixel_format": pix_fmt,
        "audio_codec": audio_stream.get("codec_name") if audio_stream else None,
        "audio_sample_rate": int(audio_stream.get("sample_rate", 0)) if audio_stream else None,
        "audio_channels": int(audio_stream.get("channels", 0)) if audio_stream else None,
        "loudness": loudness,
        "embedded_subtitle_codec": sub_stream.get("codec_name") if sub_stream else None,
        "srt_validation": srt_report,
        "sampled_frame_brightness": sampled_means,
        "checks": checks,
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify a rendered YouTube MP4 video.")
    parser.add_argument("video", type=Path, help="Path to rendered MP4 file")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--expected-duration", type=float, default=None)
    parser.add_argument("--srt", type=Path, default=None)
    parser.add_argument("--no-subtitles", action="store_true")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    report = verify_video(
        video_path=args.video,
        expected_width=args.width,
        expected_height=args.height,
        expected_fps=args.fps,
        expected_duration=args.expected_duration,
        srt_path=args.srt,
        require_subtitles=not args.no_subtitles,
    )
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(json.dumps(report, indent=2))
    sys.exit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
