"""Keith's Woo Hoo plays at start-up only; engage and every other sound come from the theme (2026-11-24)."""
import ast
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_woo_hoo_is_a_playable_startup_sound():
  with wave.open(str(ROOT / "frogpilot/assets/other_sounds/woo_hoo.wav")) as w:
    assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 48000)


def test_no_override_of_theme_sounds_in_random_events():
  # anything named like a theme sound in random_events/sounds would replace the theme's sound
  theme_sounds = {"disengage", "engage", "prompt", "prompt_distracted", "refuse", "startup", "warning_immediate", "warning_soft"}
  overrides = {p.stem for p in (ROOT / "frogpilot/assets/random_events/sounds").glob("*.wav")} & theme_sounds
  assert not overrides


def test_soundd_uses_woo_hoo_for_startup_only():
  source = (ROOT / "selfdrive/ui/soundd.py").read_text(encoding="utf-8")
  ast.parse(source)
  assert 'other_sounds/woo_hoo.wav' in source
  assert "if sound == FrogPilotAudibleAlert.startup and KEITH_STARTUP_SOUND.exists():" in source
