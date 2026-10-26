from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
from moviepy import VideoClip

from .config import FONTS_DIR, REPO_ROOT, get_iso639_2_lang
from .graphics import ContentSceneAnimator
from .models import ProjectSpec, SceneSpec, SubtitleEntry


def _segment_cache_key(
    scene: SceneSpec,
    width: int,
    height: int,
    fps: int,
    engine: str,
) -> str:
    payload = json.dumps(
        {
            "scene": scene.to_dict(),
            "width": width,
            "height": height,
            "fps": fps,
            "engine": engine,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:10]


def render_remotion_composition(
    composition_id: str,
    props: dict[str, Any],
    out_mp4: Path,
    work_dir: Path,
) -> bool:
    """
    Renders a React composition using Remotion CLI + Headless Chromium (SwiftShader Angle).
    Returns True on success, False if Remotion is unavailable so caller can fall back cleanly.
    """
    npx_bin = shutil.which("npx")
    remotion_entry = REPO_ROOT / "remotion_src" / "index.ts"
    if not npx_bin or not remotion_entry.exists():
        return False

    props_file = work_dir / f".remotion_props_{composition_id}.json"
    props_file.write_text(json.dumps(props), encoding="utf-8")
    try:
        proc = subprocess.run(
            [
                npx_bin,
                "remotion",
                "render",
                str(remotion_entry),
                composition_id,
                str(out_mp4),
                f"--props={props_file}",
                "--browser-executable=/usr/local/bin/chromium",
                "--gl=swangle",
                "--concurrency=1",
                "--log=error",
            ],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=240,
            check=False,
        )
        return proc.returncode == 0 and out_mp4.exists() and out_mp4.stat().st_size > 4096
    except Exception:
        return False
    finally:
        props_file.unlink(missing_ok=True)


def render_scene_via_moviepy(
    animator: ContentSceneAnimator,
    duration_sec: float,
    fps: int,
    out_mp4: Path,
    threads: int = 2,
) -> None:
    """
    Renders an animated scene using MoviePy 2.x VideoClip frame generator.
    """
    fade_d = min(0.28, duration_sec * 0.12)

    def make_frame(t: float) -> np.ndarray:
        rgb = animator.render_frame_rgb(t)
        if t < fade_d:
            rgb = (rgb.astype(np.float32) * (t / max(0.01, fade_d))).astype(np.uint8)
        elif t > duration_sec - fade_d:
            rem = max(0.0, duration_sec - t)
            rgb = (rgb.astype(np.float32) * (rem / max(0.01, fade_d))).astype(np.uint8)
        return rgb

    clip = VideoClip(frame_function=make_frame, duration=duration_sec)
    try:
        clip.write_videofile(
            str(out_mp4),
            fps=fps,
            codec="libx264",
            audio=False,
            preset="veryfast",
            ffmpeg_params=["-pix_fmt", "yuv420p", "-crf", "17"],
            threads=threads,
            logger=None,
        )
    finally:
        clip.close()


def render_scene_via_ffmpeg_pipe(
    animator: ContentSceneAnimator,
    duration_sec: float,
    width: int,
    height: int,
    fps: int,
    out_mp4: Path,
    threads: int = 2,
) -> None:
    """
    Memory-efficient frame-by-frame rawvideo pipe directly into FFmpeg.
    Keeps RAM flat (<15 MB frame buffer) even on hour-long 1080p/4K videos.
    """
    total_frames = max(1, int(round(duration_sec * fps)))
    fade_frames = max(1, min(int(round(0.28 * fps)), total_frames // 5))

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "rawvideo",
        "-vcodec",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "-",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "17",
        "-pix_fmt",
        "yuv420p",
        "-threads",
        str(threads),
        str(out_mp4),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for f_idx in range(total_frames):
            t = f_idx / float(fps)
            rgb = animator.render_frame_rgb(t)
            if f_idx < fade_frames:
                rgb = (rgb.astype(np.float32) * ((f_idx + 1) / float(fade_frames))).astype(np.uint8)
            elif f_idx >= total_frames - fade_frames:
                rem = total_frames - f_idx
                rgb = (rgb.astype(np.float32) * (rem / float(fade_frames))).astype(np.uint8)
            proc.stdin.write(rgb.tobytes())
        proc.stdin.close()
        stderr_out = proc.stderr.read().decode("utf-8", errors="ignore") if proc.stderr else ""
        rc = proc.wait()
        if rc != 0:
            raise RuntimeError(f"FFmpeg segment encode failed (rc={rc}): {stderr_out}")
    finally:
        if proc.poll() is None:
            proc.kill()


def render_project_video(
    project: ProjectSpec,
    preset: dict[str, Any],
    master_audio_wav: Path,
    srt_path: Path,
    ass_path: Path,
    subtitles: list[SubtitleEntry],
    work_dir: Path,
    final_mp4_path: Path,
    resumable: bool = True,
) -> dict[str, Any]:
    """
    Orchestrates scene segment rendering (Remotion + MoviePy + OpenCV/FFmpeg),
    concatenates segments, burns styled ASS subtitles (if enabled), embeds soft
    MP4 subtitle track (if enabled), muxes -14 LUFS stereo audio, and exports
    compliant YouTube H.264 + AAC MP4.
    """
    width = int(preset["width"])
    height = int(preset["height"])
    fps = int(preset["fps"])
    vcfg = preset["video"]
    acfg = preset["audio"]
    threads = int(vcfg.get("threads", 2))

    segments_dir = work_dir / "segments"
    segments_dir.mkdir(parents=True, exist_ok=True)
    final_mp4_path.parent.mkdir(parents=True, exist_ok=True)

    is_indic = project.language.lower().startswith(("hi", "mr", "bn", "ta", "te", "gu", "kn", "ml", "pa")) or any(
        ord(c) > 0x0900 for s in project.scenes for c in f"{s.headline}{s.narration}"
    )
    effective_engine = project.engine
    if effective_engine == "auto":
        effective_engine = "remotion" if (is_indic and width == 1920 and height == 1080 and fps == 30) else "hybrid"

    remotion_burned_subs = False

    def _img_to_data_uri(asset_path: str | None) -> str | None:
        if not asset_path:
            return None
        p = Path(asset_path)
        if p.exists() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} and p.stat().st_size < 8_000_000:
            mime = "image/jpeg" if p.suffix.lower() in {".jpg", ".jpeg"} else "image/png"
            return f"data:{mime};base64,{base64.b64encode(p.read_bytes()).decode('ascii')}"
        return None

    # Full-Remotion mode (default for Hindi/Indic so Chromium HarfBuzz shapes Devanagari titles, bullets & subtitles cleanly)
    if effective_engine == "remotion" and width == 1920 and height == 1080 and fps == 30:
        intro_scene = next((s for s in project.scenes if s.scene_type == "intro"), None)
        outro_scene = next((s for s in project.scenes if s.scene_type == "outro"), None)
        content_scenes = [s for s in project.scenes if s.scene_type == "content"]
        raw_remotion_mp4 = work_dir / "remotion_full_visual.mp4"
        props = {
            "channelName": project.channel_name,
            "channelTagline": project.channel_tagline,
            "episodeBadge": project.episode_badge,
            "videoTitle": project.video_title,
            "videoSubtitle": project.video_subtitle,
            "accentColor": project.accent_color,
            "secondaryColor": project.secondary_color,
            "introDurationSec": intro_scene.duration_sec if intro_scene else 3.5,
            "outroDurationSec": outro_scene.duration_sec if outro_scene else 4.0,
            "scenes": [
                {
                    "id": s.scene_id,
                    "chapterTitle": s.chapter_title,
                    "headline": s.headline,
                    "bullets": s.bullets,
                    "durationSec": s.duration_sec,
                    "accentColor": s.accent_color,
                    "imageUrl": _img_to_data_uri(s.visual_asset),
                    "statValue": s.stat_value,
                    "statLabel": s.stat_label,
                }
                for s in content_scenes
            ],
            "subtitles": [
                {"startSec": e.start_sec, "endSec": e.end_sec, "text": e.text}
                for e in (subtitles if project.burn_subtitles else [])
            ],
        }
        if render_remotion_composition("YouTubeShowcase", props, raw_remotion_mp4, work_dir):
            concat_visual_mp4 = raw_remotion_mp4
            segment_engines_used = ["remotion:YouTubeShowcase(HarfBuzz)"]
            remotion_burned_subs = bool(project.burn_subtitles and subtitles)
        else:
            effective_engine = "hybrid"

    if effective_engine != "remotion" or not (work_dir / "remotion_full_visual.mp4").exists():
        content_total = max(1, sum(1 for s in project.scenes if s.scene_type == "content"))
        content_counter = 0
        segment_files: list[Path] = []
        segment_engines_used = []

        for s in project.scenes:
            if s.scene_type == "content":
                content_counter += 1

            cache_hash = _segment_cache_key(s, width, height, fps, effective_engine)
            seg_path = segments_dir / f"{s.scene_id}_{cache_hash}.mp4"
            if resumable and seg_path.exists() and seg_path.stat().st_size > 4096:
                segment_files.append(seg_path)
                segment_engines_used.append(f"{s.scene_id}:cached")
                continue

            rendered_by_remotion = False
            if effective_engine == "hybrid" and s.scene_type in ("intro", "outro"):
                if s.scene_type == "intro":
                    r_ok = render_remotion_composition(
                        "AnimatedIntro",
                        {
                            "channelName": project.channel_name,
                            "episodeBadge": project.episode_badge,
                            "videoTitle": project.video_title,
                            "videoSubtitle": project.video_subtitle,
                            "accentColor": project.accent_color,
                            "secondaryColor": project.secondary_color,
                            "durationSec": s.duration_sec,
                            "width": width,
                            "height": height,
                            "fps": fps,
                        },
                        seg_path,
                        work_dir,
                    )
                    if r_ok:
                        rendered_by_remotion = True
                        segment_engines_used.append(f"{s.scene_id}:remotion(AnimatedIntro)")
                elif s.scene_type == "outro":
                    r_ok = render_remotion_composition(
                        "AnimatedEndScreen",
                        {
                            "channelName": project.channel_name,
                            "channelTagline": project.channel_tagline,
                            "accentColor": project.accent_color,
                            "secondaryColor": project.secondary_color,
                            "durationSec": s.duration_sec,
                            "width": width,
                            "height": height,
                            "fps": fps,
                        },
                        seg_path,
                        work_dir,
                    )
                    if r_ok:
                        rendered_by_remotion = True
                        segment_engines_used.append(f"{s.scene_id}:remotion(AnimatedEndScreen)")

            if not rendered_by_remotion:
                animator = ContentSceneAnimator(
                    scene=s,
                    total_content_scenes=content_total,
                    content_order=max(1, content_counter),
                    width=width,
                    height=height,
                    channel_name=project.channel_name,
                    channel_tagline=project.channel_tagline,
                    episode_badge=project.episode_badge,
                    secondary_hex=project.secondary_color,
                )
                try:
                    # Exercise MoviePy 2.x VideoClip on first content scene, streaming FFmpeg pipe on subsequent scenes
                    if content_counter == 1 and s.scene_type == "content":
                        render_scene_via_moviepy(
                            animator=animator,
                            duration_sec=s.duration_sec,
                            fps=fps,
                            out_mp4=seg_path,
                            threads=threads,
                        )
                        segment_engines_used.append(f"{s.scene_id}:moviepy+opencv+pillow")
                    else:
                        render_scene_via_ffmpeg_pipe(
                            animator=animator,
                            duration_sec=s.duration_sec,
                            width=width,
                            height=height,
                            fps=fps,
                            out_mp4=seg_path,
                            threads=threads,
                        )
                        segment_engines_used.append(f"{s.scene_id}:ffmpeg_pipe+opencv+pillow")
                finally:
                    animator.close()

            segment_files.append(seg_path)

        # Decode-safe filtergraph concatenation across mixed encoders (Remotion + MoviePy + FFmpeg)
        concat_visual_mp4 = None
    else:
        segment_files = [concat_visual_mp4]

    # Final YouTube Broadcast Mastering Pass:
    # Decodes all scene segments cleanly via filter_complex concat (avoiding H.264 SPS/PPS stream-copy mismatches),
    # encodes to exact YouTube Export Preset (H.264 High, yuv420p, bt709, closed 2s GOP, AAC 48kHz, +faststart),
    # plus styled ASS burn-in and/or soft MP4 mov_text subtitle stream!
    selected_vcodec = vcfg.get("selected_encoder", vcfg["codec"])
    gop = int(vcfg.get("gop_seconds", 2)) * fps
    iso_lang = get_iso639_2_lang(project.language)

    safe_ass = Path(f"/tmp/yt_studio_{hashlib.md5(str(ass_path).encode()).hexdigest()[:10]}.ass")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]
    for seg_p in segment_files:
        cmd.extend(["-i", str(seg_p)])

    audio_input_idx = len(segment_files)
    cmd.extend(["-i", str(master_audio_wav)])

    include_soft_subs = bool(project.embed_soft_subtitles and srt_path.exists() and subtitles)
    sub_input_idx = audio_input_idx + 1
    if include_soft_subs:
        cmd.extend(["-i", str(srt_path)])

    norm_chains: list[str] = []
    concat_inputs: list[str] = []
    for idx in range(len(segment_files)):
        norm_chains.append(
            f"[{idx}:v]fps={fps},scale={width}:{height}:flags=lanczos,setsar=1,format=yuv420p[v{idx}]"
        )
        concat_inputs.append(f"[v{idx}]")

    post_filters = ""
    if project.burn_subtitles and not remotion_burned_subs and ass_path.exists() and subtitles:
        shutil.copyfile(ass_path, safe_ass)
        post_filters = f",ass={safe_ass}:fontsdir={FONTS_DIR}"

    filter_complex = (
        ";".join(norm_chains)
        + f";{''.join(concat_inputs)}concat=n={len(segment_files)}:v=1:a=0[vcat];"
        + f"[vcat]format=yuv420p{post_filters}[vout]"
    )

    cmd.extend(["-filter_complex", filter_complex, "-map", "[vout]", "-map", f"{audio_input_idx}:a:0"])
    if include_soft_subs:
        cmd.extend(["-map", f"{sub_input_idx}:s:0"])

    if selected_vcodec == "libx264":
        cmd.extend(
            [
                "-c:v",
                "libx264",
                "-preset",
                str(vcfg.get("preset", "medium")),
                "-crf",
                str(vcfg.get("crf", 18)),
                "-profile:v",
                str(vcfg.get("profile", "high")),
                "-level:v",
                str(vcfg.get("level", "4.2")),
                "-maxrate",
                str(vcfg.get("maxrate", "12M")),
                "-bufsize",
                str(vcfg.get("bufsize", "24M")),
                "-g",
                str(gop),
                "-keyint_min",
                str(gop),
                "-sc_threshold",
                "0",
                "-bf",
                str(vcfg.get("bframes", 2)),
                "-pix_fmt",
                str(vcfg.get("pixel_format", "yuv420p")),
                "-colorspace",
                "bt709",
                "-color_primaries",
                "bt709",
                "-color_trc",
                "bt709",
                "-threads",
                str(threads),
            ]
        )
    else:
        # Hardware encoder path (NVENC / VAAPI / QSV)
        cmd.extend(
            [
                "-c:v",
                selected_vcodec,
                "-b:v",
                str(vcfg.get("maxrate", "12M")),
                "-maxrate",
                str(vcfg.get("maxrate", "12M")),
                "-bufsize",
                str(vcfg.get("bufsize", "24M")),
                "-g",
                str(gop),
                "-pix_fmt",
                "yuv420p",
            ]
        )

    cmd.extend(
        [
            "-c:a",
            str(acfg.get("codec", "aac")),
            "-b:a",
            str(acfg.get("bitrate", "192k")),
            "-ar",
            str(acfg.get("sample_rate", 48000)),
            "-ac",
            str(acfg.get("channels", 2)),
        ]
    )

    if include_soft_subs:
        cmd.extend(
            [
                "-c:s",
                "mov_text",
                "-metadata:s:s:0",
                f"language={iso_lang}",
                "-metadata:s:s:0",
                f"title={project.language.upper()} Captions",
            ]
        )

    cmd.extend(
        [
            "-metadata",
            f"title={project.video_title}",
            "-metadata",
            f"artist={project.channel_name}",
            "-movflags",
            str(vcfg.get("movflags", "+faststart")),
            "-shortest",
            str(final_mp4_path),
        ]
    )

    try:
        subprocess.run(cmd, check=True)
    finally:
        safe_ass.unlink(missing_ok=True)

    return {
        "preset_used": preset["name"],
        "encoder_used": selected_vcodec,
        "hardware_accelerated": vcfg.get("hardware_accelerated", False),
        "segment_engines": segment_engines_used,
        "runtime_warnings": preset.get("runtime_warnings", []),
    }
