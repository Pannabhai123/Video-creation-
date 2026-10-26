"""
music.py — royalty-free background music and sound effects, synthesised locally.

Why: stock music libraries are unreachable from this sandbox (and most are
licensed per-channel). Everything here is generated from oscillators and noise,
so it is original, royalty-free, safe to monetise with, and reproducible.

Moods: calm · reflective · inspiring · tense · upbeat
Output: 48 kHz 16-bit stereo WAV, loop-ready, with gentle fades.

    python music.py bed  --mood inspiring --seconds 120 --out ../music/bed.wav
    python music.py sfx  --kind whoosh --out ../sound_effects/whoosh.wav
"""

from __future__ import annotations

import argparse
import math
import os

import numpy as np
import soundfile as sf
from scipy.signal import fftconvolve

SR = 48000

# note frequencies
def note(name: str, octave: int) -> float:
    names = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6,
             "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
    n = names[name] + 12 * (octave + 1)
    return 440.0 * 2 ** ((n - 69) / 12)


MOODS = {
    # (root, scale intervals, tempo bpm, brightness, progression as scale degrees)
    "calm":       dict(root="C", oct=3, scale=[0, 2, 3, 5, 7, 8, 10], bpm=62, bright=0.35, prog=[0, 5, 3, 4], arp=False),
    "reflective": dict(root="A", oct=3, scale=[0, 2, 3, 5, 7, 8, 10], bpm=68, bright=0.30, prog=[0, 3, 5, 4], arp=False),
    "inspiring":  dict(root="F", oct=3, scale=[0, 2, 4, 5, 7, 9, 11], bpm=84, bright=0.55, prog=[0, 4, 5, 3], arp=True),
    "tense":      dict(root="D", oct=2, scale=[0, 1, 3, 5, 7, 8, 10], bpm=76, bright=0.25, prog=[0, 1, 0, 6], arp=False),
    "upbeat":     dict(root="G", oct=3, scale=[0, 2, 4, 5, 7, 9, 11], bpm=104, bright=0.7, prog=[0, 5, 3, 4], arp=True),
}

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _semitones(root: str, degree: int, scale: list[int]) -> float:
    base = NOTE_NAMES.index(root)
    oct_shift, idx = divmod(degree, len(scale))
    return 440.0 * 2 ** (((base + 12 * (oct_shift + 1) + scale[idx]) - 69) / 12)


def _adsr(n: int, attack: float, decay: float, sustain: float, release: float) -> np.ndarray:
    a = int(n * attack)
    d = int(n * decay)
    r = int(n * release)
    s = max(0, n - a - d - r)
    env = np.concatenate([
        np.linspace(0, 1, max(a, 1)),
        np.linspace(1, sustain, max(d, 1)),
        np.full(s, sustain),
        np.linspace(sustain, 0, max(r, 1)),
    ])
    return env[:n] if len(env) >= n else np.pad(env, (0, n - len(env)))


def _lowpass_fast(x: np.ndarray, cutoff: float, sr: int = SR, order: int = 2) -> np.ndarray:
    """FFT brick-ish low-pass with a soft roll-off — fast on long buffers."""
    if cutoff >= sr / 2:
        return x
    X = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    roll = 1.0 / (1.0 + (freqs / cutoff) ** (2 * order))
    return np.fft.irfft(X * roll, n=len(x))


def _reverb(x: np.ndarray, amount: float = 0.28, decay: float = 2.4) -> np.ndarray:
    """Cheap convolution reverb with an exponentially decaying noise tail."""
    rng = np.random.default_rng(11)
    n = int(SR * decay)
    ir = rng.normal(0, 1, n) * np.exp(-np.linspace(0, 6, n))
    ir = _lowpass_fast(ir, 4200)
    ir /= np.abs(ir).sum() ** 0.5 * 40
    wet = fftconvolve(x, ir, mode="full")[: len(x)]
    return (1 - amount) * x + amount * wet


def _pad(freq: float, n: int, gain: float, detune: float = 0.004) -> np.ndarray:
    t = np.arange(n) / SR
    sig = np.zeros(n)
    for d in (-detune, 0.0, detune):
        f = freq * (1 + d)
        sig += np.sin(2 * np.pi * f * t) + 0.28 * np.sin(2 * np.pi * f * 2 * t) + 0.12 * np.sin(2 * np.pi * f * 3 * t)
    sig /= 3.0
    env = _adsr(n, 0.22, 0.10, 0.65, 0.30)
    return sig * env * gain


def bed(mood: str = "calm", seconds: float = 90.0, gain: float = 0.55, seed: int = 5) -> np.ndarray:
    cfg = MOODS.get(mood, MOODS["calm"])
    root, oct_, scale = cfg["root"], cfg["oct"], cfg["scale"]
    beat = 60.0 / cfg["bpm"]
    bar = beat * 4
    total = int(SR * seconds)
    mix = np.zeros(total)
    rng = np.random.default_rng(seed)

    n_bars = max(1, int(math.ceil(seconds / bar)))
    for b in range(n_bars):
        deg = cfg["prog"][b % len(cfg["prog"])]
        start = int(b * bar * SR)
        if start >= total:
            break
        length = min(int(bar * SR), total - start)
        f_root = _semitones(root, deg, scale) * (2 ** (oct_ - 3))
        # chord: root, third/fourth, fifth (diatonic)
        chord = [f_root, _semitones(root, deg + 2, scale) * (2 ** (oct_ - 3)),
                 _semitones(root, deg + 4, scale) * (2 ** (oct_ - 3))]
        seg = np.zeros(length)
        for f in chord:
            seg += _pad(f, length, 0.30)
        # sub bass
        seg += 0.22 * np.sin(2 * np.pi * f_root / 2 * np.arange(length) / SR) * _adsr(length, 0.15, 0.2, 0.8, 0.3)
        mix[start:start + length] += seg

        # gentle arpeggio / pulse for brighter moods
        if cfg["arp"]:
            for k in range(4):
                s2 = start + int(k * beat * SR)
                if s2 >= total:
                    break
                l2 = min(int(beat * 1.6 * SR), total - s2)
                f = _semitones(root, deg + (2 * k) % 7, scale) * (2 ** (oct_ - 1))
                tt = np.arange(l2) / SR
                tone = 0.5 * np.sin(2 * np.pi * f * tt) + 0.2 * np.sin(2 * np.pi * f * 2 * tt)
                tone *= np.exp(-6 * tt)
                mix[s2:s2 + l2] += tone * 0.16

    # soft noise texture / vinyl-ish air
    air = rng.normal(0, 1, total)
    air = _lowpass_fast(air, 900) * 0.006
    mix += air

    mix = _lowpass_fast(mix, 1800 + 3200 * cfg["bright"], order=2)
    mix = _reverb(mix, amount=0.32, decay=2.8)

    # normalise + fades
    peak = np.max(np.abs(mix)) or 1.0
    mix = mix / peak * 0.5 * gain
    fade = int(SR * min(3.0, seconds / 6))
    mix[:fade] *= np.linspace(0, 1, fade)
    mix[-fade:] *= np.linspace(1, 0, fade)
    return mix


# ---------------------------------------------------------------- SFX
def _norm(x: np.ndarray, peak: float = 0.8) -> np.ndarray:
    m = np.max(np.abs(x)) or 1.0
    return x / m * peak


def whoosh(seconds: float = 0.9, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(SR * seconds)
    noise = rng.normal(0, 1, n)
    t = np.linspace(0, 1, n)
    # band-pass sweep by mixing two filtered copies with moving balance
    lo = _lowpass_fast(noise, 500)
    hi = noise - _lowpass_fast(noise, 2500)
    env = np.sin(np.pi * t) ** 2
    return _norm((lo * (1 - t) + hi * t) * env, 0.6)


def pop(seconds: float = 0.18) -> np.ndarray:
    n = int(SR * seconds)
    t = np.arange(n) / SR
    f = 680 * np.exp(-t * 18)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 34)
    return _norm(x, 0.7)


def tick(seconds: float = 0.09) -> np.ndarray:
    n = int(SR * seconds)
    t = np.arange(n) / SR
    x = np.sin(2 * np.pi * 1900 * t) * np.exp(-t * 90)
    return _norm(x, 0.5)


def thud(seconds: float = 0.5) -> np.ndarray:
    n = int(SR * seconds)
    t = np.arange(n) / SR
    f = 120 * np.exp(-t * 5) + 42
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 8)
    click = np.random.default_rng(2).normal(0, 1, n) * np.exp(-t * 120) * 0.2
    return _norm(x + click, 0.85)


def riser(seconds: float = 2.0, seed: int = 9) -> np.ndarray:
    rng = np.random.default_rng(seed)
    n = int(SR * seconds)
    t = np.linspace(0, 1, n)
    noise = rng.normal(0, 1, n)
    sweep = np.array([_lowpass_fast(noise, 300 + 6000 * p) for p in np.linspace(0, 1, 8)])
    # interpolate between the 8 filter states to avoid blockiness
    idx = np.linspace(0, len(sweep) - 1, n)
    lo = np.floor(idx).astype(int)
    hi = np.minimum(lo + 1, len(sweep) - 1)
    frac = idx - lo
    out = sweep[lo, np.arange(n)] * (1 - frac) + sweep[hi, np.arange(n)] * frac
    return _norm(out * (t ** 2), 0.55)


def transition_sweep(seconds: float = 0.7) -> np.ndarray:
    n = int(SR * seconds)
    t = np.linspace(0, 1, n)
    saw = 2 * (t * 6 % 1) - 1
    env = np.sin(np.pi * t) ** 1.5
    return _norm(_lowpass_fast(saw, 1800) * env, 0.45)


SFX = {"whoosh": whoosh, "pop": pop, "tick": tick, "thud": thud,
       "riser": riser, "sweep": transition_sweep}


def _tame_peaks(x: np.ndarray, drive: float = 2.6) -> np.ndarray:
    """
    Reduce crest factor so the bed can reach -14 LUFS without hitting the true-peak
    ceiling. Sub-bass thumps were eating all the headroom (19 dB crest) even though
    they contribute almost nothing to perceived loudness.
    """
    # strip rumble that only costs headroom
    x = _highpass(x, 32.0)
    peak = np.max(np.abs(x)) or 1.0
    x = x / peak
    shaped = np.tanh(x * drive) / np.tanh(drive)
    # leave ~2 dB of peak headroom so later gain staging cannot clip
    return shaped / (np.max(np.abs(shaped)) or 1.0) * 0.79


def _highpass(x: np.ndarray, cutoff: float, sr: int = SR) -> np.ndarray:
    """Frequency-domain 2nd-order high-pass (cheap, no ringing artefacts worth hearing)."""
    X = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(len(x), 1 / sr)
    roll = 1.0 - 1.0 / (1.0 + (freqs / max(cutoff, 1.0)) ** 4)
    return np.fft.irfft(X * roll, n=len(x))


def write_stereo(mono: np.ndarray, dst: str, sr: int = SR, width: float = 0.12,
                 tame: bool = True) -> str:
    """Save mono as a subtly widened stereo WAV (peaks tamed so it sits at -14 LUFS)."""
    if tame:
        mono = _tame_peaks(mono)
    if mono.ndim == 2:
        stereo = mono
    else:
        d = int(sr * 0.008 * (width / 0.12))
        left = mono
        right = np.pad(mono, (d, 0))[: len(mono)]
        stereo = np.stack([left, right * (1 - 0.15) + mono * 0.15], axis=1)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    sf.write(dst, np.clip(stereo, -1, 1), sr, subtype="PCM_16")
    return dst


def main() -> None:
    ap = argparse.ArgumentParser(description="Synthesise royalty-free music beds and SFX")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("bed")
    b.add_argument("--mood", default="calm", choices=sorted(MOODS))
    b.add_argument("--seconds", type=float, default=90)
    b.add_argument("--gain", type=float, default=0.55)
    b.add_argument("--out", required=True)
    s = sub.add_parser("sfx")
    s.add_argument("--kind", default="whoosh", choices=sorted(SFX))
    s.add_argument("--out", required=True)
    a = sub.add_parser("all-sfx")
    a.add_argument("--dir", required=True)
    args = ap.parse_args()

    if args.cmd == "bed":
        print(write_stereo(bed(args.mood, args.seconds, args.gain), args.out))
    elif args.cmd == "sfx":
        print(write_stereo(SFX[args.kind](), args.out))
    else:
        for name, fn in SFX.items():
            print(write_stereo(fn(), os.path.join(args.dir, f"{name}.wav")))


if __name__ == "__main__":
    main()
