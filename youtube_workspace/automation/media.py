"""
media.py — FFmpeg / PyAV wrapper layer for the production pipeline.

Everything the pipeline needs to touch audio or video goes through here so
paths, presets and loudness standards stay consistent.

No system ffmpeg is required: the binary shipped by the `imageio-ffmpeg`
wheel is used (FFmpeg 7.0.2 static, GPL build with libass, libx264,
libmp3lame, libopus, libfreetype, libfribidi).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, asdict
from typing import Iterable, Sequence

import av
import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# ---------------------------------------------------------------- presets
PRESETS = {
    "longform_1080p30": dict(width=1920, height=1080, fps=30, v_bitrate="6M", a_bitrate="192k"),
    "longform_1080p25": dict(width=1920, height=1080, fps=25, v_bitrate="6M", a_bitrate="192k"),
    "shorts_1080x1920": dict(width=1080, height=1920, fps=30, v_bitrate="5M", a_bitrate="192k"),
    "draft_720p": dict(width=1280, height=720, fps=30, v_bitrate="2M", a_bitrate="160k"),
}

# EBU R128 / YouTube reference loudness
LOUDNESS_TARGET = dict(I=-14.0, TP=-1.5, LRA=11.0)


def preset(name: str) -> dict:
    if name not in PRESETS:
        raise KeyError(f"unknown preset {name!r}; available: {sorted(PRESETS)}")
    return dict(PRESETS[name])


@dataclass
class MediaInfo:
    path: str
    duration: float
    width: int | None
    height: int | None
    fps: float | None
    v_codec: str | None
    a_codec: str | None
    sample_rate: int | None
    channels: int | None
    filesize: int

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- probing
def probe(path: str) -> MediaInfo:
    """Inspect any audio/video file using PyAV (no ffprobe needed)."""
    path = os.path.abspath(path)
    width = height = fps = v_codec = a_codec = None
    sample_rate = channels = None
    with av.open(path) as container:
        duration = float(container.duration / av.time_base) if container.duration else 0.0
        for stream in container.streams:
            if stream.type == "video" and width is None:
                width, height = stream.codec_context.width, stream.codec_context.height
                v_codec = stream.codec_context.name
                if stream.average_rate:
                    fps = float(stream.average_rate)
                if not duration and stream.duration and stream.time_base:
                    duration = float(stream.duration * stream.time_base)
            elif stream.type == "audio" and a_codec is None:
                a_codec = stream.codec_context.name
                sample_rate = stream.codec_context.sample_rate
                channels = stream.codec_context.channels
                if not duration and stream.duration and stream.time_base:
                    duration = float(stream.duration * stream.time_base)
    return MediaInfo(
        path=path,
        duration=round(duration, 3),
        width=width,
        height=height,
        fps=round(fps, 3) if fps else None,
        v_codec=v_codec,
        a_codec=a_codec,
        sample_rate=sample_rate,
        channels=channels,
        filesize=os.path.getsize(path) if os.path.exists(path) else 0,
    )


# ---------------------------------------------------------------- running
def run(args: Sequence[str], desc: str = "", quiet: bool = True) -> str:
    """Run ffmpeg with the given args (without the leading binary). Returns stderr tail."""
    cmd = [FFMPEG, "-hide_banner", "-nostdin", "-y", *map(str, args)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed{' (' + desc + ')' if desc else ''}:\n{proc.stderr[-3000:]}")
    return proc.stderr[-1500:]


def duration_of(path: str) -> float:
    return probe(path).duration


# ---------------------------------------------------------------- audio
def to_wav(src: str, dst: str, sample_rate: int = 48000, channels: int = 2) -> str:
    run(["-i", src, "-vn", "-ac", channels, "-ar", sample_rate, "-c:a", "pcm_s16le", dst], "to_wav")
    return dst


def concat_audio(paths: Sequence[str], dst: str, sample_rate: int = 48000) -> str:
    """Sample-accurate concatenation via the concat filter (all inputs normalised first)."""
    paths = [os.path.abspath(p) for p in paths]
    if not paths:
        raise ValueError("no audio inputs")
    args: list[str] = []
    for p in paths:
        args += ["-i", p]
    filt = "".join(f"[{i}:a]aresample={sample_rate},aformat=channel_layouts=stereo[a{i}];" for i in range(len(paths)))
    filt += "".join(f"[a{i}]" for i in range(len(paths))) + f"concat=n={len(paths)}:v=0:a=1[out]"
    run([*args, "-filter_complex", filt, "-map", "[out]", "-c:a", "pcm_s16le", dst], "concat_audio")
    return dst


def _audio_codec_for(dst: str, a_bitrate: str = "192k") -> list[str]:
    """
    Pick an encoder that matches the output extension.

    Writing AAC into a .wav filename produces a mislabelled ADTS stream that can
    also resample to 96 kHz; downstream muxing then misreads its duration. So:
    .wav/.flac/.aiff stay uncompressed, everything else becomes AAC at 48 kHz.
    """
    ext = os.path.splitext(dst)[1].lower()
    if ext == ".wav":
        return ["-c:a", "pcm_s16le", "-ar", "48000"]
    if ext == ".flac":
        return ["-c:a", "flac", "-ar", "48000"]
    if ext in (".m4a", ".mp4", ".aac"):
        return ["-c:a", "aac", "-b:a", a_bitrate, "-ar", "48000"]
    return ["-c:a", "aac", "-b:a", a_bitrate, "-ar", "48000"]


def loudness_normalise(src: str, dst: str, target: dict | None = None, a_bitrate: str = "192k") -> dict:
    """Two-pass EBU R128 normalisation to YouTube-friendly -14 LUFS (48 kHz output)."""
    t = target or LOUDNESS_TARGET
    base = ["-i", src, "-af", f"loudnorm=I={t['I']}:TP={t['TP']}:LRA={t['LRA']}:print_format=json",
            "-f", "null", "-"]
    err = run(base, "loudnorm measure")
    stats = _last_json(err)
    if stats:
        af = (
            f"loudnorm=I={t['I']}:TP={t['TP']}:LRA={t['LRA']}:"
            f"measured_I={stats['input_i']}:measured_TP={stats['input_tp']}:"
            f"measured_LRA={stats['input_lra']}:measured_thresh={stats['input_thresh']}:"
            f"offset={stats['target_offset']}:linear=true,"
            f"aresample=48000,aformat=sample_fmts=s16:channel_layouts=stereo"
        )
        run(["-i", src, "-af", af, *_audio_codec_for(dst, a_bitrate), dst], "loudnorm apply")
        stats["applied"] = True

        # loudnorm lowers its gain when the true-peak ceiling would be exceeded,
        # which can leave music-led content a few dB under target. Recover it with
        # a limited make-up pass so the file actually lands at -14 LUFS.
        got = measure_loudness(dst)
        i_now = float(got.get("input_i", 0) or 0)
        tp_now = float(got.get("input_tp", -99) or -99)
        deficit = t["I"] - i_now
        if deficit > 0.6 and tp_now > t["TP"] - 0.6:
            tmp2 = dst + ".mk.wav"
            # aim slightly below the ceiling: true peak is an inter-sample
            # measurement and always reads a little above the sample peak
            limiter = 10 ** ((t["TP"] - 0.6) / 20.0)
            run(["-i", dst,
                 "-af", f"volume={deficit:.2f}dB,alimiter=limit={limiter:.4f}:attack=3:release=40:level=false",
                 *_audio_codec_for(tmp2, a_bitrate), tmp2], "loudnorm make-up")
            os.replace(tmp2, dst)
            stats["makeup_db"] = round(deficit, 2)

        stats["output_duration"] = round(duration_of(dst), 3)
        stats["source_duration"] = round(duration_of(src), 3)
        stats["achieved_lufs"] = float(measure_loudness(dst).get("input_i", 0) or 0)
    else:
        shutil.copyfile(src, dst)
        stats = {"applied": False}
    return stats


def _last_json(text: str) -> dict | None:
    start = text.rfind("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def measure_loudness(path: str) -> dict:
    err = run(["-i", path, "-af", "loudnorm=print_format=json", "-f", "null", "-"], "measure")
    return _last_json(err) or {}


def silence_points(path: str, noise_db: int = -35, min_len: float = 0.35) -> list[tuple[float, float]]:
    err = run(["-i", path, "-af", f"silencedetect=noise={noise_db}dB:d={min_len}", "-f", "null", "-"])
    starts = [float(l.split("silence_start:")[1]) for l in err.splitlines() if "silence_start:" in l]
    ends = [float(l.split("silence_end:")[1].split()[0]) for l in err.splitlines() if "silence_end:" in l]
    return list(zip(starts, ends))


def audio_stream_of(path: str) -> tuple[str, float]:
    """Best-effort per-scene narration duration."""
    return path, duration_of(path)


def mix(narration: str | None, music: str | None, dst: str,
        music_gain_db: float = -24.0, duck: bool = True,
        sfx: Iterable[str] = (), sample_rate: int = 48000) -> str:
    """Mix narration + ducked background music + optional SFX cues (all must exist)."""
    inputs: list[str] = []
    filters: list[str] = []
    labels: list[str] = []

    if narration:
        inputs += ["-i", narration]
        filters.append(f"[0:a]aresample={sample_rate},aformat=channel_layouts=stereo[voice]")
        labels.append("voice")
    if music:
        idx = len(inputs) // 2
        inputs += ["-stream_loop", "-1", "-i", music]
        # music_gain_db is a *relative* offset from the program level, not an absolute
        # gain. Measure the bed and place it accordingly, otherwise a quiet bed plus
        # a large negative gain lands the whole programme 40 dB too low and loudness
        # normalisation has to fight a lost cause.
        bed_lufs = float(measure_loudness(music).get("input_i", -20.0))
        program_ref = -16.0 if narration else -15.0
        delta = round(program_ref + music_gain_db - bed_lufs, 2)
        filters.append(
            f"[{idx}:a]aresample={sample_rate},aformat=channel_layouts=stereo,"
            f"volume={delta}dB,alimiter=limit=0.9:level=false[bgm]"
        )
        labels.append("bgm")

    sfx_list = list(sfx)
    for k, cue in enumerate(sfx_list):
        idx = len(inputs) // 2
        inputs += ["-i", cue]
        filters.append(f"[{idx}:a]aresample={sample_rate},aformat=channel_layouts=stereo[sfx{k}]")
        labels.append(f"sfx{k}")

    if not labels:
        raise ValueError("nothing to mix")

    if "voice" in labels and "bgm" in labels and duck:
        filters.append("[bgm][voice]sidechaincompress=threshold=0.03:ratio=8:attack=20:release=400[bgmd]")
        labels[labels.index("bgm")] = "bgmd"

    total = duration_of(narration) if narration else duration_of(music)
    filters.append(
        "".join(f"[{l}]" for l in labels)
        + f"amix=inputs={len(labels)}:duration=longest:normalize=0,alimiter=limit=0.95,atrim=0:{total:.3f}[out]"
    )
    run([*inputs, "-filter_complex", ";".join(filters), "-map", "[out]",
         "-c:a", "pcm_s16le", dst], "mix")
    return dst


# ---------------------------------------------------------------- video
def still_to_video(image: str, dst: str, duration: float, fps: int = 30,
                   width: int = 1920, height: int = 1080,
                   motion: str = "zoom_in", fade: float = 0.6, zoom: float = 0.10) -> str:
    """
    Render a still with a subtle Ken-Burns move (documentary style, no jitter).

    motion: zoom_in | zoom_out | pan_left | pan_right | static
    """
    frames = max(1, int(round(duration * fps)))
    big_w, big_h = width * 2, height * 2  # oversample so zooming stays smooth
    if motion == "static":
        filt = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
    else:
        z = f"1+{zoom}*on/{frames}"
        if motion == "zoom_out":
            z = f"{1 + zoom}-{zoom}*on/{frames}"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
        if motion == "pan_left":
            z = f"1+{zoom}"
            x = f"(iw-iw/zoom)*(on/{frames})"
        elif motion == "pan_right":
            z = f"1+{zoom}"
            x = f"(iw-iw/zoom)*(1-on/{frames})"
        filt = (
            f"scale={big_w}:{big_h}:force_original_aspect_ratio=increase,"
            f"crop={big_w}:{big_h},setsar=1,"
            f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={width}x{height}:fps={fps}"
        )
    vf = filt
    if fade > 0:
        vf += f",fade=t=in:st=0:d={fade},fade=t=out:st={max(0, duration - fade):.3f}:d={fade}"
    vf += ",format=yuv420p"
    run(["-loop", "1", "-i", image, "-t", f"{duration:.3f}", "-r", fps,
         "-vf", vf, "-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
         "-pix_fmt", "yuv420p", dst], "still_to_video")
    return dst


def frames_to_video(frames, dst: str, fps: int = 30, crf: str = "18",
                    preset: str = "medium") -> str:
    """
    Encode an in-memory list of RGB numpy frames straight to H.264.

    Frames are piped to FFmpeg over stdin, so nothing touches the disk — this is
    how the neural live-photo renderer streams its composited output.
    """
    import numpy as np

    if len(frames) == 0:
        raise ValueError("no frames to encode")
    h, w = frames[0].shape[:2]
    cmd = [
        FFMPEG, "-hide_banner", "-nostdin", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
        "-an", "-c:v", "libx264", "-preset", preset, "-crf", crf,
        "-pix_fmt", "yuv420p", "-movflags", "+faststart", dst,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE)
    try:
        for frame in frames:
            arr = np.ascontiguousarray(frame)
            if arr.dtype != np.uint8:
                arr = np.clip(arr, 0, 255).astype(np.uint8)
            if arr.shape[0] != h or arr.shape[1] != w:
                raise ValueError(f"frame size mismatch: {arr.shape[:2]} vs {(h, w)}")
            proc.stdin.write(arr.tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode("utf-8", "ignore")
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg frame encode failed:\n{err[-2500:]}")
    return dst


def concat_videos(paths: Sequence[str], dst: str, workdir: str | None = None) -> str:
    """Concat identically-encoded segments using the demuxer (fast, no re-encode)."""
    paths = [os.path.abspath(p) for p in paths]
    tmpdir = workdir or tempfile.mkdtemp(prefix="concat_")
    lst = os.path.join(tmpdir, "concat_list.txt")
    with open(lst, "w", encoding="utf-8") as fh:
        for p in paths:
            fh.write(f"file '{p}'\n")
    run(["-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", dst], "concat_videos")
    return dst


FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts")


def mux(video: str, audio: str | None, dst: str, subs: str | None = None,
        burn_subs: bool = False, a_bitrate: str = "192k", crf: str = "18") -> str:
    """Combine picture, sound and (optionally burned or soft) subtitles."""
    args = ["-i", video]
    if audio:
        args += ["-i", audio]
    if subs and burn_subs:
        esc = subs.replace("\\", "/").replace(":", r"\:").replace("'", r"\'")
        args += [
            "-vf", f"subtitles='{esc}':fontsdir='{FONT_DIR}'",
            "-c:v", "libx264", "-preset", "medium", "-crf", crf, "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", a_bitrate, "-movflags", "+faststart",
            "-shortest", dst,
        ]
    else:
        if subs:
            args += ["-i", subs, "-c:s", "mov_text"]
            args += ["-map", "0:v:0", "-map", "1:a:0", "-map", "2:s:0"]
        else:
            args += ["-map", "0:v:0", "-map", "1:a:0"]
        # Guard: if the audio is shorter than the picture, pad it rather than let
        # -shortest cut the video. A silent tail is a visible defect; a truncated
        # video is a lost video.
        v_dur = duration_of(video)
        a_dur = duration_of(audio) if audio else v_dur
        if a_dur + 0.05 < v_dur:
            args = [a for a in args]
            args += ["-af", f"apad,atrim=0:{v_dur:.3f}"]
        args += ["-c:v", "copy", "-c:a", "aac", "-b:a", a_bitrate, "-ar", "48000",
                 "-movflags", "+faststart", "-shortest", dst]
    run(args, "mux")
    return dst


def extract_frame(video: str, dst: str, at: float = 1.0) -> str:
    run(["-ss", f"{at:.3f}", "-i", video, "-frames:v", "1", dst], "extract_frame")
    return dst


def black_frames(video: str, min_duration: float = 0.4, pix_th: float = 0.10,
                 pic_th: float = 0.98) -> list[tuple[float, float]]:
    """Detect black runs. pix_th = luma threshold, pic_th = fraction of pixels that must be dark."""
    err = run(["-i", video, "-vf", f"blackdetect=d={min_duration}:pix_th={pix_th}:pic_th={pic_th}",
               "-f", "null", "-"], "blackdetect")
    out = []
    start = None
    for line in err.splitlines():
        if "black_start:" in line:
            start = float(line.split("black_start:")[1].split()[0])
        if "black_end:" in line and start is not None:
            end = float(line.split("black_end:")[1].split()[0])
            out.append((round(start, 2), round(end, 2)))
            start = None
    return out


def make_short_vertical(src: str, dst: str, start: float, end: float,
                        height: int = 1920, width: int = 1080) -> str:
    """Crop a 16:9 master to a 9:16 short with a blurred background pad."""
    dur = end - start
    filt = (
        f"[0:v]split=2[bg][fg];"
        f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},gblur=sigma=30,eq=brightness=-0.10[bg2];"
        f"[fg]scale={width}:-2[fg2];"
        f"[bg2][fg2]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]"
    )
    run(["-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", src,
         "-filter_complex", filt, "-map", "[v]", "-map", "0:a?",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19",
         "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{dur:.3f}", dst], "make_short")
    return dst
