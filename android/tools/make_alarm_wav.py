"""Generate res/raw/o2_alarm.wav: a loud two-tone medical-style alarm (IEC 60601-1-8-like
high-priority burst: 10 pulses), ~2.6 s, loops cleanly. Run once; output is committed."""
import math
import struct
import wave
from pathlib import Path

RATE = 22050
OUT = Path(__file__).resolve().parents[1] / "app" / "src" / "main" / "res" / "raw" / "o2_alarm.wav"


def tone(freq, dur, amp=0.9):
    n = int(RATE * dur)
    out = []
    for i in range(n):
        env = min(1.0, i / (0.01 * RATE), (n - i) / (0.01 * RATE))      # 10 ms fade in/out, no clicks
        s = math.sin(2 * math.pi * freq * i / RATE) + 0.3 * math.sin(2 * math.pi * 2 * freq * i / RATE)
        out.append(amp * env * s / 1.3)
    return out


def silence(dur):
    return [0.0] * int(RATE * dur)


samples = []
pattern = [(880, 0.15), (660, 0.15), (880, 0.15)]
for burst in range(2):
    for _ in range(3):
        for f, d in pattern:
            samples += tone(f, d) + silence(0.05)
    samples += silence(0.35)
OUT.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(OUT), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(RATE)
    w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, s)) * 32000)) for s in samples))
print("wrote", OUT, f"{len(samples) / RATE:.2f}s")
