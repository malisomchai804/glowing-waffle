"""Original background music and sound effects, synthesized with numpy.

Everything here is generated from sine waves and noise at render time, so there is
no licensed audio, nothing for Content ID to match, and nothing to download.
The music is a calm I-V-vi-IV progression (warm pad, soft electric piano, sub bass)
that loops seamlessly and ducks under the narrator's voice.
"""

from __future__ import annotations

import wave
from pathlib import Path

import numpy as np

RATE = 44100

# --- small building blocks -------------------------------------------------


def _t(seconds: float) -> np.ndarray:
    return np.arange(int(seconds * RATE), dtype=np.float32) / RATE


def _env(n: int, attack: float, release: float) -> np.ndarray:
    env = np.ones(n, dtype=np.float32)
    a = min(n, max(1, int(attack * RATE)))
    r = min(n - a, max(1, int(release * RATE)))
    env[:a] = np.linspace(0, 1, a, dtype=np.float32)
    if r > 0:
        env[n - r :] = np.linspace(1, 0, r, dtype=np.float32) ** 2
    return env


def _midi(note: float) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


def _epiano(freq: float, seconds: float) -> np.ndarray:
    """Soft FM electric piano: bright attack that mellows as the modulation decays."""
    t = _t(seconds)
    index = 1.6 * np.exp(-t * 5.0)
    tone = np.sin(2 * np.pi * freq * t + index * np.sin(2 * np.pi * freq * t))
    tone += 0.18 * np.sin(2 * np.pi * freq * 2 * t) * np.exp(-t * 7)
    return (tone * np.exp(-t * 2.2) * _env(len(t), 0.004, 0.25)).astype(np.float32)


def _pad(freqs: list[float], seconds: float) -> np.ndarray:
    t = _t(seconds)
    out = np.zeros_like(t)
    for freq in freqs:
        for detune in (-0.12, 0.0, 0.12):  # slight chorus
            f = freq * 2 ** (detune / 12)
            out += np.sin(2 * np.pi * f * t + np.random.default_rng(int(f)).uniform(0, 6.28))
            out += 0.25 * np.sin(2 * np.pi * 2 * f * t)
    trem = 1 + 0.06 * np.sin(2 * np.pi * 0.25 * t)
    return (out * trem * _env(len(t), 1.2, 1.4) / (len(freqs) * 3.6)).astype(np.float32)


def _bass(freq: float, seconds: float) -> np.ndarray:
    t = _t(seconds)
    tone = np.sin(2 * np.pi * freq * t) + 0.2 * np.sin(2 * np.pi * 2 * freq * t)
    return (tone * _env(len(t), 0.03, 0.8)).astype(np.float32)


def _add_wrapped(buf: np.ndarray, sound: np.ndarray, at: float, gain: float) -> None:
    """Add a sound into a looping buffer; tails wrap to the start so the loop is seamless."""
    start = int(at * RATE) % len(buf)
    idx = (start + np.arange(len(sound))) % len(buf)
    np.add.at(buf, idx, sound * gain)


# --- music -------------------------------------------------------------------

# C major: C, G/B, Am, F  (MIDI root, chord tones)
_PROGRESSION = [
    (48, [60, 64, 67, 72]),
    (47, [59, 62, 67, 71]),
    (45, [57, 60, 64, 69]),
    (41, [57, 60, 65, 69]),
]
# Arpeggio orders for each 4-chord pass; variety keeps the loop from feeling short.
_PATTERNS = [
    [0, 1, 2, 3, 2, 1, 2, 3],
    [0, 2, 1, 3, 0, 2, 3, 2],
    [3, 2, 1, 2, 0, 1, 2, 1],
    [0, 1, 3, 2, 1, 2, 3, 3],
]


def music_loop(bpm: float = 72) -> np.ndarray:
    beat = 60.0 / bpm
    bar = beat * 4
    passes = len(_PATTERNS)
    length = bar * len(_PROGRESSION) * passes
    buf = np.zeros(int(length * RATE), dtype=np.float32)
    for p, pattern in enumerate(_PATTERNS):
        for c, (root, chord) in enumerate(_PROGRESSION):
            at = (p * len(_PROGRESSION) + c) * bar
            _add_wrapped(buf, _pad([_midi(n) for n in chord[:3]], bar + 1.2), at, 0.55)
            _add_wrapped(buf, _bass(_midi(root), bar * 0.95), at, 0.32)
            # Plucks every half beat; sparser on the first pass so the music "opens up".
            for step, which in enumerate(pattern):
                if p == 0 and step % 2:
                    continue
                note = chord[which] + (12 if p == 2 and step in (3, 7) else 0)
                velocity = 0.22 if step % 2 == 0 else 0.15
                _add_wrapped(buf, _epiano(_midi(note), 1.6), at + step * beat / 2, velocity)
    # Gentle low-pass (short moving average) to round off any edge in the high end.
    kernel = np.hanning(9).astype(np.float32)
    kernel /= kernel.sum()
    smoothed = np.convolve(np.concatenate([buf[-8:], buf]), kernel, mode="same")[8:]
    return smoothed / (np.max(np.abs(smoothed)) + 1e-9)


# --- sound effects -------------------------------------------------------------


def sfx_whoosh(seconds: float = 0.55) -> np.ndarray:
    rng = np.random.default_rng(7)
    n = int(seconds * RATE)
    noise = rng.standard_normal(n).astype(np.float32)
    # Sweep a simple low-pass upward then down, which reads as air moving past.
    t = np.linspace(0, 1, n, dtype=np.float32)
    cutoff = 0.02 + 0.25 * np.abs(np.sin(np.pi * t)) ** 2
    out = np.empty_like(noise)
    acc = 0.0
    for i in range(n):
        acc += cutoff[i] * (noise[i] - acc)
        out[i] = acc
    env = np.abs(np.sin(np.pi * t)) ** 1.5
    out *= env
    return out / (np.max(np.abs(out)) + 1e-9)


def sfx_pop() -> np.ndarray:
    t = _t(0.12)
    freq = 380 + 520 * np.exp(-t * 40)
    phase = 2 * np.pi * np.cumsum(freq) / RATE
    return (np.sin(phase) * np.exp(-t * 32)).astype(np.float32)


def sfx_ding() -> np.ndarray:
    t = _t(1.4)
    f = 1318.5
    bell = np.sin(2 * np.pi * f * t + 1.2 * np.exp(-t * 6) * np.sin(2 * np.pi * f * 2.76 * t))
    bell += 0.35 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t * 5)
    return (bell * np.exp(-t * 3.2) * _env(len(t), 0.002, 0.2) * 0.8).astype(np.float32)


def sfx_alert() -> np.ndarray:
    parts = []
    for freq in (740, 587):
        t = _t(0.22)
        tone = np.sin(2 * np.pi * freq * t) + 0.3 * np.sin(2 * np.pi * freq * 3 * t)
        parts.append(tone * _env(len(t), 0.01, 0.12))
    return (np.concatenate(parts) * 0.7).astype(np.float32)


def sfx_tick() -> np.ndarray:
    t = _t(0.03)
    return (np.sin(2 * np.pi * 2200 * t) * np.exp(-t * 180) * 0.6).astype(np.float32)


_SFX_GAIN = {"whoosh": 0.16, "pop": 0.14, "ding": 0.11, "alert": 0.12, "tick": 0.05}


def _sfx_bank() -> dict[str, np.ndarray]:
    return {
        "whoosh": sfx_whoosh(),
        "pop": sfx_pop(),
        "ding": sfx_ding(),
        "alert": sfx_alert(),
        "tick": sfx_tick(),
    }


# --- mixing --------------------------------------------------------------------


def read_wav(path: Path) -> np.ndarray:
    with wave.open(str(path), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
        channels = handle.getnchannels()
        rate = handle.getframerate()
    data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    if rate != RATE:
        raise ValueError(f"expected {RATE} Hz, got {rate}")
    return data


def write_wav(path: Path, data: np.ndarray) -> None:
    pcm = (np.clip(np.nan_to_num(data), -1, 1) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(pcm.tobytes())


def _voice_envelope(voice: np.ndarray) -> np.ndarray:
    hop = 1024
    n = len(voice) // hop + 1
    padded = np.pad(voice, (0, n * hop - len(voice)))
    rms = np.sqrt((padded.reshape(n, hop) ** 2).mean(axis=1))
    active = (rms > 0.02).astype(np.float32)
    # Fast attack, slow release, so music dips as speech starts and swells in pauses.
    smooth = np.empty_like(active)
    acc = 0.0
    for i, x in enumerate(active):
        acc += (0.6 if x > acc else 0.08) * (x - acc)
        smooth[i] = acc
    return np.interp(np.arange(len(voice)), np.arange(n) * hop, smooth).astype(np.float32)


def mix(voice_wav: Path, dest: Path, cues: list[tuple[float, str]], music_level: float = 0.11) -> None:
    """Voice + ducked music bed + timed sound effects. cues are (seconds, sfx name)."""
    voice = read_wav(voice_wav)
    n = len(voice)
    loop = music_loop()
    music = np.tile(loop, n // len(loop) + 1)[:n]
    fade = min(n, int(2.0 * RATE))
    music[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
    music[n - fade :] *= np.linspace(1, 0, fade, dtype=np.float32)
    duck = 1.0 - 0.62 * _voice_envelope(voice)  # about -8 dB under speech
    out = voice + music * music_level * duck
    bank = _sfx_bank()
    for at, name in cues:
        sound = bank.get(name)
        if sound is None:
            continue
        start = int(at * RATE)
        if start >= n or start < 0:
            continue
        piece = sound[: n - start] * _SFX_GAIN[name]
        out[start : start + len(piece)] += piece
    # Soft limiter keeps peaks under 0 dBFS without audible pumping.
    peak = np.max(np.abs(out)) + 1e-9
    if peak > 0.95:
        out = np.tanh(out * 1.1) / np.tanh(1.1)
    write_wav(dest, out.astype(np.float32))
