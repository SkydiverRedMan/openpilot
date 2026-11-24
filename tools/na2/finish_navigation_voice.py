"""Even out Navigation Assist's spoken prompts: trim silence, -18 dB RMS (a little under openpilot's own sounds), peak
under -1 dB, short fades. Writes them back in place as 48 kHz mono 16-bit (what soundd requires)."""
import sys
import wave
from pathlib import Path

import numpy as np

FOLDER = Path(__file__).resolve().parents[2] / "frogpilot/assets/navigation_voice"
TARGET_RMS_DB = -18.0
PEAK_DB = -1.0

for path in sorted(FOLDER.glob("*.wav")):
  with wave.open(str(path)) as w:
    assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 48000), path
    x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(float) / 32768
  level = np.abs(x)
  loud = np.where(level > level.max() * 0.03)[0]
  x = x[max(loud[0] - 960, 0):min(loud[-1] + 2400, len(x))]           # 20 ms before, 50 ms after the speech
  gain = 10 ** (TARGET_RMS_DB / 20) / (np.sqrt(np.mean(x ** 2)) or 1)
  gain = min(gain, 10 ** (PEAK_DB / 20) / (np.max(np.abs(x)) or 1))
  x = x * gain
  fade = 480
  x[:fade] *= np.linspace(0, 1, fade)
  x[-fade:] *= np.linspace(1, 0, fade)
  with wave.open(str(path), "wb") as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(48000)
    w.writeframes((np.clip(x, -1, 1) * 32767).astype("<i2").tobytes())
  print(f"{path.name}: {len(x) / 48000:.2f} s, {20 * np.log10(np.sqrt(np.mean(x ** 2))):.1f} dB RMS")
sys.exit(0)
