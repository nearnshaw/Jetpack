"""Original synthwave cue for the marketplace video, synthesised from scratch (no samples, no downloads).

  python3 promote/tools/make_music.py promote/music/jetpack_theme.wav

112.5 BPM, so one beat = 0.5333 s and the video's cuts (beats 0, 6, 12, 16, 22, 32) land on the beat.
Bars of A minor: Am F C G. Drums + pumping saw bass + 16th pulse arp from the top, a square lead from beat 16
(the "nearby players" shot), a riser into the end card at beat 32, then a ringing Am chord.
"""
import sys
import numpy as np
from scipy.signal import butter, lfilter
import wave

SR = 44100
BPM = 112.5
BEAT = 60 / BPM
TOTAL_BEATS = 38
N = int(TOTAL_BEATS * BEAT * SR) + SR // 2
rng = np.random.default_rng(7)

def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)

def idx(beat):
    return int(round(beat * BEAT * SR))

def lp(x, fc, order=2):
    b, a = butter(order, fc / (SR / 2), 'low')
    return lfilter(b, a, x)

def hp(x, fc, order=2):
    b, a = butter(order, fc / (SR / 2), 'high')
    return lfilter(b, a, x)

def bp(x, lo, hi):
    b, a = butter(2, [lo / (SR / 2), hi / (SR / 2)], 'band')
    return lfilter(b, a, x)

def saw(f, n, detune=0.0, phase=0.0):
    t = np.arange(n) / SR
    f = f * 2 ** (detune / 1200)
    out = np.zeros(n)
    for k in range(1, max(2, min(40, int(SR / 2 / f)))):
        out += np.sin(2 * np.pi * k * f * t + phase * k) / k
    return out * 0.6

def square(f, n, detune=0.0, vib=None):
    t = np.arange(n) / SR
    f = f * 2 ** (detune / 1200)
    ph = 2 * np.pi * f * t if vib is None else 2 * np.pi * np.cumsum(f * vib) / SR
    out = np.zeros(n)
    for k in range(1, max(2, min(30, int(SR / 2 / f))), 2):
        out += np.sin(k * ph) / k
    return out * 0.8

def env(n, a=0.005, d=0.1, s=0.0, r=0.05, hold=None):
    """Attack, exponential decay towards sustain, release over the last r seconds."""
    t = np.arange(n) / SR
    e = np.minimum(1, t / max(a, 1e-4))
    e = e * (s + (1 - s) * np.exp(-np.maximum(0, t - a) / max(d, 1e-4)))
    rn = int(r * SR)
    if rn and n > rn:
        e[-rn:] *= np.linspace(1, 0, rn)
    return e

L = np.zeros(N); R = np.zeros(N)

def add(sig, beat, gain=1.0, pan=0.0):
    i = idx(beat)
    j = min(N, i + len(sig))
    if j <= i:
        return
    s = sig[: j - i] * gain
    L[i:j] += s * np.sqrt(0.5 * (1 - pan))
    R[i:j] += s * np.sqrt(0.5 * (1 + pan))

# ---- harmony -------------------------------------------------------------------------------------
CHORDS = {'Am': (57, 60, 64), 'F': (53, 57, 60), 'C': (48, 52, 55), 'G': (55, 59, 62)}
ROOTS = {'Am': 33, 'F': 29, 'C': 36, 'G': 31}
PROG = ['Am', 'F', 'C', 'G'] * 2 + ['Am', 'Am']

# ---- drums ---------------------------------------------------------------------------------------
def kick():
    n = int(0.4 * SR); t = np.arange(n) / SR
    f = 45 + 110 * np.exp(-t / 0.035)
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.22)
    s[: int(0.003 * SR)] += rng.standard_normal(int(0.003 * SR)) * 0.4
    return s

def snare():
    n = int(0.3 * SR); t = np.arange(n) / SR
    noise = bp(rng.standard_normal(n), 1200, 7000) * np.exp(-t / 0.12)
    tone = np.sin(2 * np.pi * 185 * t) * np.exp(-t / 0.05)
    return noise * 0.9 + tone * 0.5

def hat(open_=False):
    n = int((0.25 if open_ else 0.06) * SR); t = np.arange(n) / SR
    return hp(rng.standard_normal(n), 7500) * np.exp(-t / (0.09 if open_ else 0.018))

def crash():
    n = int(2.2 * SR); t = np.arange(n) / SR
    return hp(rng.standard_normal(n), 4500) * np.exp(-t / 0.7)

K, S, CH, OH, CR = kick(), snare(), hat(), hat(True), crash()
kick_env = np.zeros(N)
for b in range(32):
    add(K, b, 0.95)
    i = idx(b); n = int(0.3 * SR); kick_env[i:i + n] = np.maximum(kick_env[i:i + n], np.exp(-np.arange(n) / SR / 0.09)[: N - i])
    if b % 2 == 1 and b != 31:
        add(S, b, 0.45, 0.05)
    add(OH, b + 0.5, 0.10, 0.3)
    for q in (0, 0.25, 0.75):
        add(CH, b + q, 0.06 if q else 0.04, -0.3)
for q in range(4):                                      # fill into the end card
    add(S, 31 + q * 0.25, 0.25 + 0.1 * q, 0.05)
add(K, 32, 1.0)
kick_env[idx(32):idx(32) + int(0.3 * SR)] = np.exp(-np.arange(int(0.3 * SR)) / SR / 0.09)
for b in (0, 16, 32):
    add(CR, b, 0.22, 0.2 if b != 16 else -0.2)
pump = 1 - 0.55 * kick_env                              # sidechain on bass, pad and arp

# ---- bass: 8th-note octave pulse -----------------------------------------------------------------
bass = np.zeros(N)
for bar, ch in enumerate(PROG):
    for e in range(8):
        b = bar * 4 + e * 0.5
        if b >= 32:
            break
        f = hz(ROOTS[ch] + (12 if e % 2 else 0))
        n = int(BEAT * 0.5 * SR)
        s = lp(saw(f, n) + 0.5 * saw(f, n, 9), 700 if e % 2 else 950) * env(n, 0.003, 0.11, 0.25, 0.02)
        s += np.sin(2 * np.pi * hz(ROOTS[ch]) * np.arange(n) / SR) * 0.35 * env(n, 0.003, 0.2, 0.5, 0.02)
        i = idx(b); bass[i:i + n] += s[: N - i]
n = int(3.2 * SR)                                       # final low A rings under the end card
s = lp(saw(hz(33), n) + saw(hz(33), n, 8), 500) * env(n, 0.005, 1.0, 0, 0.4)
bass[idx(32):idx(32) + n] += s[: N - idx(32)]
add(bass * pump, 0, 0.42)

# ---- 16th pulse arp with ping-pong delay ---------------------------------------------------------
arp = np.zeros(N)
for bar, ch in enumerate(PROG):
    tones = [c + 12 for c in CHORDS[ch]] + [CHORDS[ch][0] + 24, CHORDS[ch][1] + 24]
    pattern = [0, 1, 2, 3, 4, 3, 2, 1]
    for sxt in range(16):
        b = bar * 4 + sxt * 0.25
        if b >= 36:
            break
        n = int(BEAT * 0.25 * SR)
        s = lp(square(hz(tones[pattern[sxt % 8]]), n), 3200) * env(n, 0.002, 0.07, 0.0, 0.01)
        fade = 1.0 if b < 32 else max(0.0, 1 - (b - 32) / 4)
        i = idx(b); arp[i:i + n] += s[: N - i] * (0.8 + 0.2 * (sxt % 4 == 0)) * fade
d = idx(0.75)
arpL = arp.copy(); arpR = arp.copy()
arpL[d:] += 0.38 * arp[:-d]; arpR[2 * d:] += 0.25 * arp[:-2 * d]
L += arpL * pump * 0.17; R += arpR * pump * 0.17

# ---- pad: detuned saws, slow attack --------------------------------------------------------------
for bar, ch in enumerate(PROG[:8]):
    n = int(4 * BEAT * SR)
    for m in CHORDS[ch]:
        for det, pan in ((-11, -0.7), (11, 0.7)):
            s = lp(saw(hz(m), n, det, phase=rng.random() * 6), 1600) * env(n, 0.35, 10, 1.0, 0.25)
            i = idx(bar * 4); j = min(N, i + n)
            g = s[: j - i] * pump[i:j] * 0.055
            L[i:j] += g * np.sqrt(0.5 * (1 - pan)); R[i:j] += g * np.sqrt(0.5 * (1 + pan))
n = int(3.4 * SR)                                       # final chord, bright stab that rings out
for m in (57, 60, 64, 69, 76):
    for det, pan in ((-9, -0.6), (9, 0.6)):
        s = lp(saw(hz(m), n, det), 3000) * env(n, 0.01, 1.3, 0.0, 0.5)
        add(s, 32, 0.07, pan)

# ---- lead from beat 16 ---------------------------------------------------------------------------
LEAD = [  # (beat, length in beats, midi)
    (16, 1, 76), (17, 0.5, 81), (17.5, 0.5, 79), (18, 1, 76), (19, 1, 74),
    (20, 1.5, 72), (21.5, 0.5, 74), (22, 2, 76),
    (24, 1, 79), (25, 0.5, 76), (25.5, 0.5, 79), (26, 1, 84), (27, 1, 83),
    (28, 1.5, 83), (29.5, 0.5, 81), (30, 1.5, 79), (31.5, 0.5, 83),
    (32, 4, 81),
]
lead = np.zeros(N)
for b, ln, m in LEAD:
    n = int(ln * BEAT * SR)
    t = np.arange(n) / SR
    vib = 1 + 0.006 * np.sin(2 * np.pi * 5.5 * t) * np.minimum(1, t / 0.25)
    s = square(hz(m), n, vib=vib) + 0.6 * saw(hz(m), n, 7)
    s = lp(s, 3800) * env(n, 0.01, 0.6 if ln < 4 else 1.2, 0.55 if ln < 4 else 0.0, 0.04)
    i = idx(b); lead[i:i + n] += s[: N - i]
dl = idx(0.75)
leadL = lead.copy(); leadR = lead.copy()
leadL[dl:] += 0.3 * lead[:-dl]; leadR[dl * 2:] += 0.22 * lead[:-dl * 2]
L += leadL * 0.12; R += leadR * 0.12

# ---- riser into the end card ---------------------------------------------------------------------
n = idx(4)
t = np.arange(n) / SR
noise = rng.standard_normal(n)
chunks = 32
riser = np.concatenate([bp(c, 400 + 7000 * (k / chunks) ** 2, 900 + 9000 * (k / chunks) ** 2)
                        for k, c in enumerate(np.array_split(noise, chunks))])
riser *= (t / t[-1]) ** 2
add(riser, 28, 0.10)

# ---- master --------------------------------------------------------------------------------------
mix = np.stack([L, R], 1)
mix = np.tanh(mix * 1.6) / np.tanh(1.6)
mix /= np.abs(mix).max() / 0.89
end = idx(TOTAL_BEATS)
mix = mix[:end]
mix[-int(0.6 * SR):] *= np.linspace(1, 0, int(0.6 * SR))[:, None]
out = sys.argv[1] if len(sys.argv) > 1 else 'jetpack_theme.wav'
with wave.open(out, 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((mix * 32767).astype('<i2').tobytes())
print('wrote', out, round(len(mix) / SR, 3), 's')
