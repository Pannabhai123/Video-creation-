from __future__ import annotations

import ctypes
import math
import os
import subprocess
from pathlib import Path
from typing import Any

import espeakng_loader
import noisereduce as nr
import numpy as np
import pyloudnorm as pyln
import requests
import soundfile as sf
from scipy import signal

from .models import SceneSpec, WordTiming

TARGET_SR = 48000


class _EspeakEventId(ctypes.Union):
    _fields_ = [
        ("number", ctypes.c_int),
        ("name", ctypes.c_char_p),
        ("string", ctypes.c_char * 8),
    ]


class _EspeakEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("unique_identifier", ctypes.c_uint),
        ("text_position", ctypes.c_int),
        ("length", ctypes.c_int),
        ("audio_position", ctypes.c_int),
        ("sample", ctypes.c_int),
        ("user_data", ctypes.c_void_p),
        ("id", _EspeakEventId),
    ]


_ESPEAK_LIB: ctypes.CDLL | None = None
_ESPEAK_SR: int = 22050


def _get_espeak() -> tuple[ctypes.CDLL, int]:
    global _ESPEAK_LIB, _ESPEAK_SR
    if _ESPEAK_LIB is None:
        lib = ctypes.CDLL(espeakng_loader.get_library_path())
        lib.espeak_Initialize.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        lib.espeak_Initialize.restype = ctypes.c_int
        sr = lib.espeak_Initialize(0x02, 0, espeakng_loader.get_data_path().encode("utf-8"), 0)
        if sr <= 0:
            sr = 22050
        _ESPEAK_LIB = lib
        _ESPEAK_SR = sr
    return _ESPEAK_LIB, _ESPEAK_SR


def _enhance_voice_waveform(wav: np.ndarray, sr: int) -> np.ndarray:
    """
    Applies broadcast vocal shaping:
    - Highpass at 80 Hz (rumble removal)
    - Gentle lowpass at 9200 Hz (smooths formant edge)
    - Subtle presence boost & soft-knee compression
    """
    if wav.size == 0:
        return wav
    sos_hp = signal.butter(2, 80.0 / (sr * 0.5), btype="highpass", output="sos")
    sos_lp = signal.butter(3, min(9200.0, sr * 0.44) / (sr * 0.5), btype="lowpass", output="sos")
    shaped = signal.sosfilt(sos_hp, wav)
    shaped = signal.sosfilt(sos_lp, shaped)
    # Soft-knee tanh warmth & peak normalization
    peak = float(np.max(np.abs(shaped)))
    if peak > 1e-5:
        shaped = shaped / peak
        shaped = np.tanh(shaped * 1.35) / math.tanh(1.35) * 0.85
    return shaped.astype(np.float32)


def synthesize_espeak_segment(
    text: str,
    language: str = "en-us",
    speed_wpm: int = 160,
    pitch: int = 46,
) -> tuple[np.ndarray, list[WordTiming]]:
    """
    Synthesizes spoken narration locally via libespeak-ng.so and extracts exact
    millisecond word-boundary timestamps. Returns 48 kHz mono float32 audio + WordTimings.
    """
    clean_text = " ".join(text.strip().split())
    if not clean_text:
        return np.zeros(int(TARGET_SR * 0.5), dtype=np.float32), []

    lib, src_sr = _get_espeak()
    samples: list[int] = []
    raw_word_events: list[tuple[int, int, int]] = []

    SYNTH_CB = ctypes.CFUNCTYPE(
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_short),
        ctypes.c_int,
        ctypes.POINTER(_EspeakEvent),
    )

    def _callback(wav_ptr, numsamples, ev_ptr) -> int:
        if wav_ptr and numsamples > 0:
            samples.extend(wav_ptr[:numsamples])
        idx = 0
        while ev_ptr and ev_ptr[idx].type != 0:
            ev = ev_ptr[idx]
            if ev.type == 1:  # espeakEVENT_WORD
                raw_word_events.append((ev.text_position, ev.length, ev.audio_position))
            idx += 1
        return 0

    c_cb = SYNTH_CB(_callback)
    lib.espeak_SetSynthCallback(c_cb)

    voice_bytes = (language or "en-us").encode("utf-8")
    if lib.espeak_SetVoiceByName(voice_bytes) != 0:
        base_lang = (language or "en").split("-")[0].encode("utf-8")
        if lib.espeak_SetVoiceByName(base_lang) != 0:
            lib.espeak_SetVoiceByName(b"en-us")

    # espeakRATE=1, espeakPITCH=2
    lib.espeak_SetParameter(1, int(speed_wpm), 0)
    lib.espeak_SetParameter(2, int(pitch), 0)

    btext = clean_text.encode("utf-8")
    lib.espeak_Synth(btext, len(btext) + 1, 0, 0, 0, 1, None, None)

    if not samples:
        return np.zeros(int(TARGET_SR * 0.5), dtype=np.float32), []

    arr = np.array(samples, dtype=np.float32) / 32768.0
    # Resample to 48000 Hz
    gcd = math.gcd(TARGET_SR, src_sr)
    resampled = signal.resample_poly(arr, TARGET_SR // gcd, src_sr // gcd).astype(np.float32)
    enhanced = _enhance_voice_waveform(resampled, TARGET_SR)
    total_dur = len(enhanced) / TARGET_SR

    # Map eSpeak 1-based Unicode CHARACTER events onto exact whitespace-delimited tokens from clean_text.
    # Verified empirically: espeak_EVENT.text_position is 1-based Unicode codepoint index (works for Hindi Devanagari & English).
    token_spans: list[tuple[str, int, int]] = []
    char_cursor = 0
    for tok in clean_text.split(" "):
        if tok:
            token_spans.append((tok, char_cursor, char_cursor + len(tok)))
        char_cursor += len(tok) + 1  # +1 for single space character

    token_time_map: dict[int, list[float]] = {}
    for i, (char_pos, _char_len, start_ms) in enumerate(raw_word_events):
        c_start = max(0, char_pos - 1)
        start_s = max(0.0, start_ms / 1000.0)
        next_s = (
            raw_word_events[i + 1][2] / 1000.0
            if i + 1 < len(raw_word_events)
            else total_dur
        )
        end_s = max(start_s + 0.08, min(total_dur, next_s))

        matched_idx: int | None = None
        for t_idx, (_tok, ts_c, te_c) in enumerate(token_spans):
            if ts_c <= c_start <= te_c:
                matched_idx = t_idx
                break
        if matched_idx is not None:
            if matched_idx not in token_time_map:
                token_time_map[matched_idx] = [start_s, end_s]
            else:
                token_time_map[matched_idx][0] = min(token_time_map[matched_idx][0], start_s)
                token_time_map[matched_idx][1] = max(token_time_map[matched_idx][1], end_s)

    timings: list[WordTiming] = []
    last_end = 0.0
    for t_idx, (tok, _ts_c, _te_c) in enumerate(token_spans):
        if t_idx in token_time_map:
            s_t, e_t = token_time_map[t_idx]
            last_end = e_t
            timings.append(WordTiming(word=tok, start_sec=round(s_t, 3), end_sec=round(e_t, 3)))
        else:
            s_t = last_end
            e_t = min(total_dur, s_t + 0.12)
            last_end = e_t
            timings.append(WordTiming(word=tok, start_sec=round(s_t, 3), end_sec=round(e_t, 3)))

    return enhanced, timings


def _try_external_tts_api(text: str, out_wav: Path, provider: str) -> bool:
    """
    Optional external neural TTS integration (OpenAI TTS / ElevenLabs) ONLY when keys are configured.
    """
    if provider in ("auto", "elevenlabs") and os.environ.get("ELEVENLABS_API_KEY", "").strip():
        key = os.environ["ELEVENLABS_API_KEY"].strip()
        voice_id = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM").strip()
        mp3_tmp = out_wav.with_suffix(".tmp.mp3")
        try:
            r = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={"xi-api-key": key, "Content-Type": "application/json"},
                json={"text": text, "model_id": "eleven_multilingual_v2"},
                timeout=25,
            )
            if r.status_code == 200 and len(r.content) > 1000:
                mp3_tmp.write_bytes(r.content)
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(mp3_tmp), "-ar", str(TARGET_SR), "-ac", "1", str(out_wav)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )
                mp3_tmp.unlink(missing_ok=True)
                return True
        except Exception:
            mp3_tmp.unlink(missing_ok=True)

    if provider in ("auto", "openai") and os.environ.get("OPENAI_API_KEY", "").strip():
        key = os.environ["OPENAI_API_KEY"].strip()
        mp3_tmp = out_wav.with_suffix(".tmp.mp3")
        try:
            r = requests.post(
                "https://api.openai.com/v1/audio/speech",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={"model": "tts-1", "voice": "onyx", "input": text},
                timeout=25,
            )
            if r.status_code == 200 and len(r.content) > 1000:
                mp3_tmp.write_bytes(r.content)
                subprocess.run(
                    ["ffmpeg", "-y", "-i", str(mp3_tmp), "-ar", str(TARGET_SR), "-ac", "1", str(out_wav)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=True,
                )
                mp3_tmp.unlink(missing_ok=True)
                return True
        except Exception:
            mp3_tmp.unlink(missing_ok=True)

    return False


def decode_audio_to_mono_48k(src_path: Path, apply_denoise: bool = True) -> np.ndarray:
    """
    Loads any external audio file (.wav, .mp3, .m4a, .flac, .ogg) into 48 kHz mono float32
    and optionally applies spectral gating noise reduction + high-pass filter.
    """
    tmp_wav = src_path.parent / f".decoded_{src_path.stem}_48k.wav"
    try:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(src_path),
                "-vn",
                "-ar",
                str(TARGET_SR),
                "-ac",
                "1",
                "-c:a",
                "pcm_f32le",
                str(tmp_wav),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        audio, _ = sf.read(str(tmp_wav), dtype="float32")
    finally:
        tmp_wav.unlink(missing_ok=True)

    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)

    if apply_denoise and len(audio) > TARGET_SR // 2:
        audio = nr.reduce_noise(y=audio, sr=TARGET_SR, stationary=True, prop_decrease=0.72).astype(np.float32)

    sos_hp = signal.butter(2, 75.0 / (TARGET_SR * 0.5), btype="highpass", output="sos")
    audio = signal.sosfilt(sos_hp, audio).astype(np.float32)
    return audio


def generate_copyright_safe_music(duration_sec: float, sr: int = TARGET_SR, seed: int = 42) -> np.ndarray:
    """
    Synthesizes a lush, 100% copyright-safe stereo ambient background soundtrack
    using polyphonic warm detuned chord pads (Am9 -> Fmaj7 -> Cmaj9 -> G6),
    sub-bass pulse, and gentle harmonic shimmer. Returns shape (N, 2) float32.
    """
    rng = np.random.default_rng(seed)
    total_samples = max(sr, int(round(duration_sec * sr)))
    stereo = np.zeros((total_samples, 2), dtype=np.float32)

    # 4-chord progression, 4.0 seconds per chord bar
    chords_hz = [
        [110.00, 220.00, 261.63, 329.63, 392.00, 493.88],  # Am9
        [87.31, 174.61, 220.00, 261.63, 329.63, 440.00],   # Fmaj7(add13)
        [130.81, 196.00, 246.94, 293.66, 329.63, 392.00],  # Cmaj9
        [98.00, 196.00, 246.94, 293.66, 329.63, 440.00],   # G6/9
    ]
    bar_sec = 4.0
    crossfade_sec = 0.65
    bar_samples = int(bar_sec * sr)
    xfade_samples = int(crossfade_sec * sr)
    step_samples = bar_samples - xfade_samples

    num_bars = math.ceil(total_samples / max(1, step_samples)) + 1
    t_bar = np.arange(bar_samples, dtype=np.float32) / sr

    # Smooth ADSR envelope per chord bar
    env = np.ones(bar_samples, dtype=np.float32)
    env[:xfade_samples] = np.linspace(0.0, 1.0, xfade_samples, dtype=np.float32)
    env[-xfade_samples:] = np.linspace(1.0, 0.0, xfade_samples, dtype=np.float32)

    for b_idx in range(num_bars):
        start = b_idx * step_samples
        if start >= total_samples:
            break
        end = min(total_samples, start + bar_samples)
        length = end - start
        t = t_bar[:length]
        e = env[:length]
        freqs = chords_hz[b_idx % len(chords_hz)]

        left = np.zeros(length, dtype=np.float32)
        right = np.zeros(length, dtype=np.float32)

        for n_idx, f in enumerate(freqs):
            weight = 0.36 if n_idx == 0 else (0.20 / math.sqrt(n_idx))
            phase_l = float(rng.uniform(0, 2 * math.pi))
            phase_r = phase_l + 0.35
            detune = 1.0022 if (n_idx % 2 == 0) else 0.9978
            # Warm fundamental + soft octave harmonic + slow LFO movement
            lfo = 0.85 + 0.15 * np.sin(2 * math.pi * 0.25 * t + n_idx)
            left += weight * lfo * (
                np.sin(2 * math.pi * f * t + phase_l)
                + 0.25 * np.sin(2 * math.pi * (f * 2.0) * t + phase_l * 0.5)
            )
            right += weight * lfo * (
                np.sin(2 * math.pi * (f * detune) * t + phase_r)
                + 0.25 * np.sin(2 * math.pi * (f * 2.0 * detune) * t + phase_r * 0.5)
            )

        # Gentle arpeggio bell note on beat 2 & beat 4
        for beat_offset_s, note_hz in ((0.75, freqs[-1] * 2.0), (2.25, freqs[-2] * 2.0)):
            b_pos = int(beat_offset_s * sr)
            if b_pos < length:
                bell_len = min(int(1.3 * sr), length - b_pos)
                tb = np.arange(bell_len, dtype=np.float32) / sr
                bell_env = np.exp(-tb * 3.8) * np.minimum(1.0, tb / 0.015)
                bell_sig = 0.075 * bell_env * np.sin(2 * math.pi * note_hz * tb)
                left[b_pos : b_pos + bell_len] += bell_sig
                right[b_pos : b_pos + bell_len] += bell_sig * 0.9

        stereo[start:end, 0] += left * e
        stereo[start:end, 1] += right * e

    # Warm lowpass filter at 2.8 kHz so music never clashes with human speech intelligibility band!
    sos_lp = signal.butter(3, 2800.0 / (sr * 0.5), btype="lowpass", output="sos")
    stereo[:, 0] = signal.sosfilt(sos_lp, stereo[:, 0])
    stereo[:, 1] = signal.sosfilt(sos_lp, stereo[:, 1])

    peak = float(np.max(np.abs(stereo)))
    if peak > 1e-6:
        stereo /= peak
    return stereo


def generate_scene_sfx_track(
    scenes: list[SceneSpec],
    total_samples: int,
    sr: int = TARGET_SR,
) -> np.ndarray:
    """
    Synthesizes copyright-safe broadcast sound effects (soft filtered transition whoosh
    and warm harmonic chapter chime) aligned to scene transitions.
    """
    sfx = np.zeros((total_samples, 2), dtype=np.float32)
    rng = np.random.default_rng(108)

    # Pre-build a 0.42s filtered soft whoosh + 0.85s warm bell chime
    w_len = int(0.42 * sr)
    tw = np.arange(w_len, dtype=np.float32) / sr
    noise = rng.standard_normal(w_len).astype(np.float32)
    sos_bp = signal.butter(2, [180.0 / (sr * 0.5), 1400.0 / (sr * 0.5)], btype="bandpass", output="sos")
    whoosh_mono = signal.sosfilt(sos_bp, noise) * np.sin(np.pi * (tw / 0.42)) ** 2
    peak_w = float(np.max(np.abs(whoosh_mono))) or 1.0
    whoosh_mono = (whoosh_mono / peak_w) * 0.35

    c_len = int(0.85 * sr)
    tc = np.arange(c_len, dtype=np.float32) / sr
    chime_env = np.exp(-tc * 4.8) * np.minimum(1.0, tc / 0.012)
    chime_l = (0.55 * np.sin(2 * np.pi * 523.25 * tc) + 0.30 * np.sin(2 * np.pi * 783.99 * tc)) * chime_env
    chime_r = (0.55 * np.sin(2 * np.pi * 524.0 * tc) + 0.30 * np.sin(2 * np.pi * 785.0 * tc)) * chime_env

    for s in scenes:
        pos = int(round(s.start_sec * sr))
        if s.index > 0 and pos > w_len // 2:
            ws = max(0, pos - w_len // 2)
            we = min(total_samples, ws + w_len)
            seg_n = we - ws
            pan = np.linspace(0.25, 0.75, seg_n, dtype=np.float32)
            sfx[ws:we, 0] += whoosh_mono[:seg_n] * (1.0 - pan)
            sfx[ws:we, 1] += whoosh_mono[:seg_n] * pan

        if s.scene_type in ("intro", "content") and pos + c_len < total_samples:
            ce = min(total_samples, pos + c_len)
            cn = ce - pos
            sfx[pos:ce, 0] += chime_l[:cn] * 0.45
            sfx[pos:ce, 1] += chime_r[:cn] * 0.45

    return sfx


def load_or_generate_music(
    duration_sec: float,
    music_path: Path | None = None,
) -> np.ndarray:
    target_len = max(TARGET_SR, int(round(duration_sec * TARGET_SR)))
    if music_path and music_path.exists():
        tmp_wav = music_path.parent / f".music_{music_path.stem}_48k.wav"
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(music_path),
                    "-vn",
                    "-ar",
                    str(TARGET_SR),
                    "-ac",
                    "2",
                    "-c:a",
                    "pcm_f32le",
                    str(tmp_wav),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
            )
            music, _ = sf.read(str(tmp_wav), dtype="float32")
        finally:
            tmp_wav.unlink(missing_ok=True)
        if music.ndim == 1:
            music = np.column_stack([music, music])
        if len(music) < target_len:
            reps = math.ceil(target_len / len(music))
            music = np.tile(music, (reps, 1))
        music = music[:target_len]
        peak = float(np.max(np.abs(music)))
        if peak > 1e-6:
            music = music / peak
        return music.astype(np.float32)

    return generate_copyright_safe_music(duration_sec=duration_sec, sr=TARGET_SR)


def build_voiceover_and_master_audio(
    scenes: list[SceneSpec],
    work_dir: Path,
    language: str = "en",
    voiceover_file: Path | None = None,
    music_file: Path | None = None,
    music_enabled: bool = True,
    narration_cfg: dict[str, Any] | None = None,
    music_cfg: dict[str, Any] | None = None,
    target_lufs: float = -14.0,
) -> tuple[Path, Path, list[WordTiming], str]:
    """
    Produces:
    1) Clean 48kHz voiceover track (`voiceover_48k.wav`)
    2) Auto-ducked, -14 LUFS loudness-normalized stereo master (`master_mix_48k.wav`)
    3) Exact `WordTiming` list (when synthesized) and updates `scenes` start/end/duration_sec!
    Returns (voiceover_path, master_path, word_timings, voiceover_source_used).
    """
    work_dir.mkdir(parents=True, exist_ok=True)
    narration_cfg = narration_cfg or {}
    music_cfg = music_cfg or {}

    vo_path = work_dir / "voiceover_48k.wav"
    master_path = work_dir / "master_mix_48k.wav"

    all_word_timings: list[WordTiming] = []
    source_used = "espeak-ng (offline local TTS)"

    if voiceover_file and voiceover_file.exists():
        # External user-supplied voiceover file!
        apply_nr = bool(narration_cfg.get("apply_noise_reduction_on_external_audio", True))
        vo_mono = decode_audio_to_mono_48k(voiceover_file, apply_denoise=apply_nr)
        source_used = f"external_file ({voiceover_file.name}, denoised={apply_nr})"

        # Add 0.8s intro pad and 1.2s outro tail if needed, and scale scene durations proportionally
        lead_pad = np.zeros(int(0.6 * TARGET_SR), dtype=np.float32)
        tail_pad = np.zeros(int(1.2 * TARGET_SR), dtype=np.float32)
        vo_mono = np.concatenate([lead_pad, vo_mono, tail_pad])
        total_dur = len(vo_mono) / TARGET_SR

        raw_weights = [max(1.0, float(len(s.narration.split()))) for s in scenes]
        weight_sum = sum(raw_weights)
        cursor = 0.0
        for s, w in zip(scenes, raw_weights):
            s.start_sec = round(cursor, 3)
            s.duration_sec = round(total_dur * (w / weight_sum), 3)
            cursor += s.duration_sec
            s.end_sec = round(cursor, 3)
    else:
        # Synthesize per-scene narration so each scene's duration and visuals lock 100% to speech!
        provider = narration_cfg.get("provider", "auto")
        lang_clean = (language or "").strip().lower()
        if lang_clean == "en":
            espeak_voice = "en-us"
        elif lang_clean:
            espeak_voice = lang_clean
        else:
            espeak_voice = narration_cfg.get("espeak_voice", "hi")
        espeak_speed = int(narration_cfg.get("espeak_speed_wpm", 162))
        espeak_pitch = int(narration_cfg.get("espeak_pitch", 46))

        scene_chunks: list[np.ndarray] = []
        cursor_samples = 0

        for s in scenes:
            pre_pad_sec = 0.65 if s.scene_type == "intro" else 0.35
            post_pad_sec = 1.35 if s.scene_type == "outro" else 0.55

            api_wav = work_dir / f".api_{s.scene_id}.wav"
            used_api = _try_external_tts_api(s.narration, api_wav, provider=provider)
            if used_api and api_wav.exists():
                seg_audio = decode_audio_to_mono_48k(api_wav, apply_denoise=False)
                api_wav.unlink(missing_ok=True)
                seg_words: list[WordTiming] = []
                source_used = "external_tts_api"
            else:
                seg_audio, seg_words = synthesize_espeak_segment(
                    s.narration,
                    language=espeak_voice,
                    speed_wpm=espeak_speed,
                    pitch=espeak_pitch,
                )

            # Respect user's preferred longer scene duration if requested
            spoken_sec = pre_pad_sec + (len(seg_audio) / TARGET_SR) + post_pad_sec
            final_scene_sec = max(spoken_sec, s.duration_sec if s.scene_type in ("intro", "outro") else 0.0)
            extra_tail = max(0.0, final_scene_sec - spoken_sec)

            pre_samples = int(round(pre_pad_sec * TARGET_SR))
            post_samples = int(round((post_pad_sec + extra_tail) * TARGET_SR))

            offset_sec = (cursor_samples + pre_samples) / TARGET_SR
            for wt in seg_words:
                all_word_timings.append(
                    WordTiming(
                        word=wt.word,
                        start_sec=round(wt.start_sec + offset_sec, 3),
                        end_sec=round(wt.end_sec + offset_sec, 3),
                    )
                )

            full_scene_audio = np.concatenate(
                [
                    np.zeros(pre_samples, dtype=np.float32),
                    seg_audio,
                    np.zeros(post_samples, dtype=np.float32),
                ]
            )
            s.start_sec = round(cursor_samples / TARGET_SR, 3)
            s.duration_sec = round(len(full_scene_audio) / TARGET_SR, 3)
            cursor_samples += len(full_scene_audio)
            s.end_sec = round(cursor_samples / TARGET_SR, 3)
            scene_chunks.append(full_scene_audio)

        vo_mono = np.concatenate(scene_chunks) if scene_chunks else np.zeros(TARGET_SR, dtype=np.float32)

    sf.write(str(vo_path), vo_mono, TARGET_SR, subtype="PCM_16")

    total_samples = len(vo_mono)
    total_duration = total_samples / TARGET_SR
    vo_stereo = np.column_stack([vo_mono, vo_mono])

    if music_enabled:
        music_stereo = load_or_generate_music(total_duration, music_path=music_file)
        base_gain = 10.0 ** (float(music_cfg.get("base_gain_db", -16.5)) / 20.0)
        duck_gain = 10.0 ** (float(music_cfg.get("ducked_gain_db", -27.5)) / 20.0)

        # Compute smooth speech-activity envelope (100 Hz control rate -> upsampled)
        hop = TARGET_SR // 100
        num_frames = math.ceil(total_samples / hop)
        padded = np.pad(np.abs(vo_mono), (0, num_frames * hop - total_samples))
        frame_rms = np.sqrt(np.mean(padded.reshape(num_frames, hop) ** 2, axis=1))
        speech_active = (frame_rms > 0.018).astype(np.float32)

        # Asymmetric attack (80ms) & release (550ms) smoothing for natural broadcast ducking
        env_ctrl = np.zeros_like(speech_active)
        curr = 0.0
        alpha_attack = 0.35
        alpha_release = 0.045
        for i, val in enumerate(speech_active):
            if val > curr:
                curr = curr + alpha_attack * (val - curr)
            else:
                curr = curr + alpha_release * (val - curr)
            env_ctrl[i] = curr

        duck_curve = np.repeat(env_ctrl, hop)[:total_samples]
        gain_curve = base_gain * (1.0 - duck_curve) + duck_gain * duck_curve

        # Smooth fade-in and fade-out on music bed
        fade_in_n = min(total_samples // 3, int(float(music_cfg.get("fade_in_sec", 1.0)) * TARGET_SR))
        fade_out_n = min(total_samples // 3, int(float(music_cfg.get("fade_out_sec", 1.8)) * TARGET_SR))
        if fade_in_n > 0:
            gain_curve[:fade_in_n] *= np.linspace(0.0, 1.0, fade_in_n, dtype=np.float32)
        if fade_out_n > 0:
            gain_curve[-fade_out_n:] *= np.linspace(1.0, 0.0, fade_out_n, dtype=np.float32)

        mixed = vo_stereo + music_stereo[:total_samples] * gain_curve[:, None]
    else:
        mixed = vo_stereo.copy()

    if bool(music_cfg.get("sfx_enabled", True)):
        sfx_gain = 10.0 ** (float(music_cfg.get("sfx_gain_db", -20.0)) / 20.0)
        sfx_stereo = generate_scene_sfx_track(scenes, total_samples=total_samples, sr=TARGET_SR)
        mixed = mixed + sfx_stereo * sfx_gain

    # Soft-limit raw transients first, then normalize integrated loudness to YouTube -14.0 LUFS
    raw_peak = float(np.max(np.abs(mixed)))
    if raw_peak > 1e-6:
        mixed = np.tanh((mixed / raw_peak) * 1.35) / math.tanh(1.35) * 0.80

    meter = pyln.Meter(TARGET_SR)
    measured_lufs = meter.integrated_loudness(mixed)
    if not math.isinf(measured_lufs) and not math.isnan(measured_lufs):
        gain_db = target_lufs - measured_lufs
        mixed = mixed * (10.0 ** (gain_db / 20.0))

    # True-peak ceiling at -1.0 dBFS (0.891 linear) without boosting RMS
    ceiling = 10.0 ** (-1.05 / 20.0)
    mixed = np.clip(mixed, -ceiling, ceiling)

    sf.write(str(master_path), mixed.astype(np.float32), TARGET_SR, subtype="PCM_16")
    return vo_path, master_path, all_word_timings, source_used
