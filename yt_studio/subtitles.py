from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
import wave
from pathlib import Path
from typing import Any

import librosa
import numpy as np
import soundfile as sf
import srt

from .models import SceneSpec, SubtitleEntry, WordTiming


def _group_words_into_cues(
    words: list[WordTiming],
    max_words: int = 8,
    max_chars: int = 44,
) -> list[SubtitleEntry]:
    if not words:
        return []

    entries: list[SubtitleEntry] = []
    buf: list[WordTiming] = []

    def flush() -> None:
        if not buf:
            return
        text = " ".join(w.word for w in buf).strip()
        start = buf[0].start_sec
        end = max(start + 0.35, buf[-1].end_sec)
        # Ensure strict monotonicity with previous cue
        if entries and start < entries[-1].end_sec + 0.02:
            entries[-1].end_sec = round(max(entries[-1].start_sec + 0.20, start - 0.02), 3)
        entries.append(
            SubtitleEntry(
                index=len(entries) + 1,
                start_sec=round(start, 3),
                end_sec=round(end, 3),
                text=text,
            )
        )
        buf.clear()

    for wt in words:
        projected_len = sum(len(x.word) for x in buf) + len(buf) + len(wt.word)
        # Break if gap > 0.55s, max words/chars reached
        gap_break = bool(buf and (wt.start_sec - buf[-1].end_sec) > 0.55)
        if buf and (len(buf) >= max_words or projected_len > max_chars or gap_break):
            flush()
        buf.append(wt)
        if wt.word.endswith((".", "!", "?", ";", ":")) and len(buf) >= 3:
            flush()
        elif wt.word.endswith(",") and len(buf) >= 5:
            flush()

    flush()
    return entries


def transcribe_audio_offline(voiceover_wav: Path, language: str = "en") -> list[WordTiming]:
    """
    Automatic speech transcription from audio:
    1) Uses Faster-Whisper if WHISPER_LOCAL_MODEL_PATH points to local CTranslate2 weights.
    2) Otherwise runs offline PocketSphinx acoustic decoder bundled locally.
    """
    whisper_dir = os.environ.get("WHISPER_LOCAL_MODEL_PATH", "").strip()
    if whisper_dir and Path(whisper_dir).exists():
        from faster_whisper import WhisperModel

        model = WhisperModel(whisper_dir, device="cpu", compute_type="int8")
        segments, _ = model.transcribe(str(voiceover_wav), language=language.split("-")[0], word_timestamps=True)
        out: list[WordTiming] = []
        for seg in segments:
            for w in seg.words or []:
                token = w.word.strip()
                if token:
                    out.append(WordTiming(word=token, start_sec=round(w.start, 3), end_sec=round(w.end, 3)))
        if out:
            return out

    # Offline PocketSphinx 16 kHz mono PCM transcription
    from pocketsphinx import Decoder

    tmp_16k = voiceover_wav.parent / ".stt_16k.wav"
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(voiceover_wav),
                "-ar",
                "16000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(tmp_16k),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        with wave.open(str(tmp_16k), "rb") as wf:
            pcm = wf.readframes(wf.getnframes())
    finally:
        tmp_16k.unlink(missing_ok=True)

    decoder = Decoder()
    # Process in ~12-second speech chunks for accuracy on long-form audio
    bytes_per_sec = 16000 * 2
    chunk_bytes = bytes_per_sec * 12
    words_out: list[WordTiming] = []

    for offset_b in range(0, len(pcm), chunk_bytes):
        chunk = pcm[offset_b : offset_b + chunk_bytes]
        if len(chunk) < 1600:
            continue
        base_sec = offset_b / bytes_per_sec
        decoder.start_utt()
        decoder.process_raw(chunk, full_utt=True)
        decoder.end_utt()
        for seg in decoder.seg():
            clean_word = re.sub(r"\(\d+\)$", "", seg.word)
            if clean_word not in ("<s>", "</s>", "<sil>", "[SPEECH]", "[NOISE]"):
                s_sec = base_sec + (seg.start_frame / 100.0)
                e_sec = base_sec + max((seg.start_frame + 8) / 100.0, seg.end_frame / 100.0)
                words_out.append(WordTiming(word=clean_word, start_sec=round(s_sec, 3), end_sec=round(e_sec, 3)))

    return words_out


def align_script_to_voiceover_envelope(
    scenes: list[SceneSpec],
    voiceover_wav: Path,
) -> list[WordTiming]:
    """
    Synchronizes known script text to an external voiceover waveform by detecting
    non-silent speech intervals with Librosa and distributing syllable-weighted words
    across active speech spans.
    """
    audio, sr = sf.read(str(voiceover_wav), dtype="float32")
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)

    intervals = librosa.effects.split(audio, top_db=28, frame_length=2048, hop_length=512)
    speech_spans = [(float(s) / sr, float(e) / sr) for s, e in intervals if (e - s) > int(0.12 * sr)]

    timings: list[WordTiming] = []
    for scene in scenes:
        words = scene.narration.strip().split()
        if not words:
            continue
        # Clip speech spans intersecting this scene
        scene_spans = [
            (max(scene.start_sec, a), min(scene.end_sec, b))
            for a, b in speech_spans
            if b > scene.start_sec and a < scene.end_sec
        ]
        if not scene_spans:
            scene_spans = [(scene.start_sec + 0.25, max(scene.start_sec + 0.6, scene.end_sec - 0.25))]

        active_total = sum(max(0.05, b - a) for a, b in scene_spans)
        char_weights = [max(2, len(w)) for w in words]
        total_w = sum(char_weights)

        # Flatten active spans onto virtual spoken timeline, then map back to real timestamps
        virtual_cursor = 0.0
        for w_str, cw in zip(words, char_weights):
            w_dur = active_total * (cw / total_w)
            v_start = virtual_cursor
            v_end = virtual_cursor + w_dur
            virtual_cursor = v_end

            def _map_virtual(v_t: float) -> float:
                acc = 0.0
                for sa, sb in scene_spans:
                    slen = max(0.05, sb - sa)
                    if acc + slen >= v_t:
                        return sa + (v_t - acc)
                    acc += slen
                return scene_spans[-1][1]

            r_start = _map_virtual(v_start)
            r_end = max(r_start + 0.08, _map_virtual(v_end))
            timings.append(WordTiming(word=w_str, start_sec=round(r_start, 3), end_sec=round(r_end, 3)))

    return timings


def _format_vtt_ts(seconds: float) -> str:
    ms_total = max(0, int(round(seconds * 1000)))
    hh = ms_total // 3_600_000
    rem = ms_total % 3_600_000
    mm = rem // 60_000
    rem %= 60_000
    ss = rem // 1000
    ms = rem % 1000
    return f"{hh:02d}:{mm:02d}:{ss:02d}.{ms:03d}"


def _format_ass_ts(seconds: float) -> str:
    cs_total = max(0, int(round(seconds * 100)))
    hh = cs_total // 360_000
    rem = cs_total % 360_000
    mm = rem // 6_000
    rem %= 6_000
    ss = rem // 100
    cs = rem % 100
    return f"{hh}:{mm:02d}:{ss:02d}.{cs:02d}"


def write_subtitle_files(
    entries: list[SubtitleEntry],
    srt_path: Path,
    vtt_path: Path,
    ass_path: Path,
    width: int = 1920,
    height: int = 1080,
    sub_cfg: dict[str, Any] | None = None,
) -> None:
    sub_cfg = sub_cfg or {}
    srt_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. SRT file
    srt_objs = [
        srt.Subtitle(
            index=e.index,
            start=dt.timedelta(seconds=e.start_sec),
            end=dt.timedelta(seconds=e.end_sec),
            content=e.text,
        )
        for e in entries
    ]
    srt_path.write_text(srt.compose(srt_objs), encoding="utf-8")

    # 2. WebVTT file
    vtt_lines = ["WEBVTT", ""]
    for e in entries:
        vtt_lines.append(f"{e.index}")
        vtt_lines.append(f"{_format_vtt_ts(e.start_sec)} --> {_format_vtt_ts(e.end_sec)}")
        vtt_lines.append(e.text)
        vtt_lines.append("")
    vtt_path.write_text("\n".join(vtt_lines), encoding="utf-8")

    # 3. Broadcast Styled ASS file (scaled proportionally to target resolution)
    scale = height / 1080.0
    font_name = sub_cfg.get("font_name", "Poppins SemiBold")
    font_size = max(24, int(round(float(sub_cfg.get("font_size_1080p", 44)) * scale)))
    margin_v = max(32, int(round(float(sub_cfg.get("margin_v_1080p", 64)) * scale)))
    margin_h = max(60, int(round(120 * scale)))
    outline = max(2, int(round(3 * scale)))

    ass_header = f"""[Script Info]
Title: YouTube Studio Broadcast Subtitles
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},&H00FFFFFF,&H0038BDF8,&H000B1120,&H96050811,0,0,0,0,100,100,0.4,0,1,{outline},2,2,{margin_h},{margin_h},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ass_events: list[str] = []
    for e in entries:
        escaped = e.text.replace("\n", "\\N")
        # Subtle 80ms fade-in / fade-out per caption for broadcast polish
        ass_events.append(
            f"Dialogue: 0,{_format_ass_ts(e.start_sec)},{_format_ass_ts(e.end_sec)},Default,,0,0,0,,{{\\fad(80,80)}}{escaped}"
        )

    ass_path.write_text(ass_header + "\n".join(ass_events) + "\n", encoding="utf-8")


def generate_subtitles_for_project(
    scenes: list[SceneSpec],
    voiceover_wav: Path,
    word_timings: list[WordTiming],
    out_dir: Path,
    language: str = "en",
    width: int = 1920,
    height: int = 1080,
    sub_cfg: dict[str, Any] | None = None,
    transcribe_only: bool = False,
) -> tuple[list[SubtitleEntry], Path, Path, Path]:
    sub_cfg = sub_cfg or {}
    if not word_timings:
        has_script = any(s.narration.strip() for s in scenes) and not transcribe_only
        if has_script:
            word_timings = align_script_to_voiceover_envelope(scenes, voiceover_wav)
        else:
            word_timings = transcribe_audio_offline(voiceover_wav, language=language)

    entries = _group_words_into_cues(
        word_timings,
        max_words=int(sub_cfg.get("max_words_per_cue", 8)),
        max_chars=int(sub_cfg.get("max_chars_per_line", 44)),
    )

    srt_path = out_dir / f"subtitles.{language}.srt"
    vtt_path = out_dir / f"subtitles.{language}.vtt"
    ass_path = out_dir / f"subtitles.{language}.ass"

    write_subtitle_files(
        entries=entries,
        srt_path=srt_path,
        vtt_path=vtt_path,
        ass_path=ass_path,
        width=width,
        height=height,
        sub_cfg=sub_cfg,
    )
    return entries, srt_path, vtt_path, ass_path
