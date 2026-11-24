"""Navigation Assist spoken prompts (2026-11-24): what is said, when, and that alerts always win."""
import ast
import wave
from pathlib import Path

from openpilot.frogpilot.navigation_assist import engine as E
from openpilot.frogpilot.navigation_assist.tests.test_engine import LANES_BOTH, Driver, nav

ROOT = Path(__file__).resolve().parents[3]


def drive(d, start, step, seconds, v=30.0, **kwargs):
  prompts = []
  last = d.engine.voice_count
  for k in range(int(seconds / 0.2)):
    out = d.step(nav(max(start - k * step, 0), **kwargs), v=v)
    if out.voice_prompt_count != last:
      prompts.append((round(k * 0.2, 1), out.voice_prompt))
      last = out.voice_prompt_count
  return prompts


def voiced_driver(**lane):
  d = Driver()
  d.lane = dict(LANES_BOTH, voice_enabled=True, **lane)
  return d


def test_exit_is_announced_then_the_lane_advice_once_each():
  d = voiced_driver()
  prompts = drive(d, 3000, 6, 60)
  phrases = [p for _, p in prompts]
  assert phrases[0] == "exit_right_ahead"
  assert "move_right_exit" in phrases
  assert len(phrases) == len(set(phrases)), phrases                # nothing twice
  times = [t for t, _ in prompts]
  assert all(b - a >= E.VOICE_MIN_GAP - 0.01 for a, b in zip(times, times[1:]))


def test_silent_when_switched_off():
  d = voiced_driver()
  d.lane["voice_enabled"] = False
  assert drive(d, 3000, 6, 60) == []


def test_never_speaks_about_traffic():
  d = voiced_driver(radar_right_alongside=True)
  phrases = [p for _, p in drive(d, 3000, 6, 60)]
  assert phrases and all(p in E.VOICE_PHRASES for p in phrases)
  assert not any("traffic" in p or "vehicle" in p for p in phrases)
  assert "move_right_exit" not in phrases                         # it never says "move" while a car is alongside


def test_every_phrase_has_a_sound_file():
  folder = ROOT / "frogpilot/assets/navigation_voice"
  for phrase in E.VOICE_PHRASES:
    with wave.open(str(folder / f"{phrase}.wav")) as w:
      assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 48000)
      assert 0.5 < w.getnframes() / 48000 < 3.0


def test_soundd_plays_prompts_only_when_no_alert_and_alerts_cut_them_off():
  source = (ROOT / "selfdrive/ui/soundd.py").read_text(encoding="utf-8")
  ast.parse(source)
  assert "'navigationAssist'" in source
  body = source[source.index("def get_sound_data"):source.index("def callback")]
  assert "if self.current_alert != AudibleAlert.none:\n      self.nav_voice = None" in body
  update = source[source.index("def update_nav_voice"):source.index("def update_alert")]
  assert "self.current_alert == AudibleAlert.none" in update and "self.nav_voice_count is None" in update


def test_nothing_is_said_right_at_the_maneuver():
  d = voiced_driver()
  assert drive(d, 25, 0, 10, v=1.0, mtype="turn", modifier="right") == []        # 25 m: too close
  d = voiced_driver()
  assert drive(d, 40, 0, 10, v=13.0, mtype="fork", modifier="left") == []        # 40 m at 29 mph: 3 s away


def test_a_turn_renamed_by_a_route_update_is_not_announced_again():
  # stopped 150 m before a right turn; a route update shifts distance_remaining so the turn gets a new key
  d = voiced_driver()
  first = drive(d, 150, 0, 20, v=0.0, mtype="turn", modifier="right")
  again = drive(d, 150, 0, 20, v=0.0, mtype="turn", modifier="right", remaining=5000)
  assert [p for _, p in first][0] == "turn_right_ahead" and again == []
  # once that turn is behind us, the next right turn is announced
  drive(d, 150, 10, 4, v=50.0, mtype="turn", modifier="right", remaining=5000)
  later = drive(d, 600, 0, 20, v=0.0, mtype="turn", modifier="right", remaining=3000)
  assert [p for _, p in later][0] == "turn_right_ahead"
