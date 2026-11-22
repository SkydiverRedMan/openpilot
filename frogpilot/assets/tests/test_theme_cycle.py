"""Keith's theme test cycle (frogpilot/assets/theme_manager.py): next theme at each boot, same theme after a drive."""
import importlib
import json
import sys
import types

import pytest


@pytest.fixture
def tm(monkeypatch, tmp_path):
  # theme_manager imports heavy openpilot modules; only the cycle helpers are tested here
  for name in ("requests", "dateutil", "dateutil.easter", "dateutil.relativedelta"):
    monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
  sys.modules["dateutil"].easter = sys.modules["dateutil.easter"]
  sys.modules["dateutil"].relativedelta = sys.modules["dateutil.relativedelta"]
  common = types.ModuleType("openpilot.frogpilot.common")
  paths = types.SimpleNamespace(THEME_PACKS_PATH=tmp_path / "theme_packs", STEERING_WHEELS_PATH=tmp_path / "steering_wheels")
  for name, value in (("frogpilot_download_utilities", types.SimpleNamespace()), ("frogpilot_paths", paths),
                      ("frogpilot_utilities", types.SimpleNamespace()), ("frogpilot_variables", types.SimpleNamespace())):
    setattr(common, name, value)
  monkeypatch.setitem(sys.modules, "openpilot.frogpilot.common", common)
  monkeypatch.delitem(sys.modules, "openpilot.frogpilot.assets.theme_manager", raising=False)
  module = importlib.import_module("openpilot.frogpilot.assets.theme_manager")
  for key in ("alpha-user_created", "bravo-user_created", "charlie-user_created"):
    (tmp_path / "theme_packs" / key).mkdir(parents=True)
  return module, tmp_path / "cycle.json"


def write(path, **cycle):
  path.write_text(json.dumps(cycle))


def test_each_boot_shows_the_next_theme_and_wraps(tm):
  module, path = tm
  write(path, enabled=True, order=["alpha-user_created", "bravo-user_created", "charlie-user_created"], next=0)
  seen = [module.cycle_theme(advance=True, path=path) for _ in range(4)]
  assert seen == ["alpha-user_created", "bravo-user_created", "charlie-user_created", "alpha-user_created"]


def test_after_a_drive_the_theme_stays(tm):
  module, path = tm
  write(path, enabled=True, order=["alpha-user_created", "bravo-user_created"], next=0)
  assert module.cycle_theme(advance=True, path=path) == "alpha-user_created"
  assert module.cycle_theme(advance=False, path=path) == "alpha-user_created"
  assert module.cycle_theme(advance=False, path=path) == "alpha-user_created"
  assert module.cycle_theme(advance=True, path=path) == "bravo-user_created"


def test_deleted_themes_are_skipped(tm):
  module, path = tm
  write(path, enabled=True, order=["gone-user_created", "bravo-user_created"], next=0)
  assert module.cycle_theme(advance=True, path=path) == "bravo-user_created"


@pytest.mark.parametrize("content", [None, "{not json", json.dumps({"enabled": False, "order": ["alpha-user_created"]}),
                                     json.dumps({"enabled": True, "order": []}), json.dumps({"enabled": True})])
def test_cycle_off(tm, content):
  module, path = tm
  if content is not None:
    path.write_text(content)
  assert module.cycle_theme(advance=True, path=path) is None


def test_position_is_saved_across_restarts(tm):
  module, path = tm
  write(path, enabled=True, order=["alpha-user_created", "bravo-user_created", "charlie-user_created"], next=2)
  assert module.cycle_theme(advance=True, path=path) == "charlie-user_created"
  saved = json.loads(path.read_text())
  assert saved["current"] == "charlie-user_created" and saved["next"] == 0


def test_cycle_branch_uses_every_part_and_the_theme_wheel():
  from pathlib import Path
  source = (Path(__file__).resolve().parents[1] / "theme_manager.py").read_text(encoding="utf-8")
  branch = source[source.index("cycle_key := cycle_theme(advance=boot_run)"):]
  branch = branch[:branch.index("elif (boot_run or randomize_theme) and frogpilot_toggles.random_themes:")]
  for part in ("colors", "distance_icons", "icons", "sounds", "signals", "wheel_image"):
    assert f'("{part}", cycle_key)' in branch
  # the cycle sits after the holiday branch and before plain random themes
  assert source.index("if self.holiday_theme != \"stock\":") < source.index("cycle_key := cycle_theme") < \
         source.index("selected_theme = random.choice(available_themes)")


# ---------- theme picker ----------

def test_request_round_trip(tm, tmp_path):
  module, _ = tm
  path = tmp_path / "request"
  assert module.take_theme_request(path) is None
  module.request_theme("bravo-user_created", path)
  assert module.take_theme_request(path) == "bravo-user_created"
  assert not path.exists()                                   # taken once


def test_picked_mappings_use_every_part(tm, tmp_path):
  module, _ = tm
  wheels = tmp_path / "steering_wheels"
  wheels.mkdir()
  (wheels / "bravo-user_created.png").write_bytes(b"")
  (wheels / "paramotor.gif").write_bytes(b"")
  testing = module.picked_theme_mappings("bravo-user_created", theme_wheels=True)
  assert {v[1] for k, v in testing.items() if k != "wheel_image"} == {"bravo-user_created"}
  assert testing["wheel_image"] == ("wheel_image", "bravo-user_created")
  # outside the test cycle the paramotor wheel stays
  assert module.picked_theme_mappings("bravo-user_created", theme_wheels=False)["wheel_image"] == ("wheel_image", "paramotor")
  # a theme without its own wheel keeps the paramotor wheel even while testing
  assert module.picked_theme_mappings("alpha-user_created", theme_wheels=True)["wheel_image"] == ("wheel_image", "paramotor")


def test_animated_keys_use_base_colors_and_sounds(tm, tmp_path):
  module, _ = tm
  m = module.picked_theme_mappings("frog-animated", theme_wheels=False)
  assert m["icon_pack"] == ("icons", "frog-animated")
  assert m["color_scheme"] == ("colors", "frog") and m["sound_pack"] == ("sounds", "frog")


def test_pick_moves_the_cycle(tm):
  module, path = tm
  write(path, enabled=True, order=["alpha-user_created", "bravo-user_created", "charlie-user_created"], next=0)
  module.move_cycle_to("bravo-user_created", path)
  assert module.cycle_theme(advance=False, path=path) == "bravo-user_created"
  assert module.cycle_theme(advance=True, path=path) == "charlie-user_created"


def test_picked_branch_comes_before_the_cycle_and_random():
  from pathlib import Path
  source = (Path(__file__).resolve().parents[1] / "theme_manager.py").read_text(encoding="utf-8")
  picked = source.index("elif self.picked_theme is not None and not boot_run:")
  assert source.index('if self.holiday_theme != "stock":') < picked < source.index("cycle_key := cycle_theme(advance=boot_run)")


def test_process_applies_requests():
  from pathlib import Path
  source = (Path(__file__).resolve().parents[2] / "frogpilot_process.py").read_text(encoding="utf-8")
  assert "if THEME_REQUEST_PATH.exists():" in source and "theme_manager.apply_picked_theme(picked" in source


def test_ui_long_press_is_parked_only_and_keeps_the_tap():
  from pathlib import Path
  ui = (Path(__file__).resolve().parents[3] / "selfdrive/ui/qt/onroad/buttons.cc").read_text(encoding="utf-8")
  assert "if (parked) {\n      long_press_timer->start();" in ui
  assert "if (long_press_fired) {" in ui and "changeMode();" in ui
  assert '"/dev/shm/keith_theme_request"' in ui
