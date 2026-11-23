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
  write(path, enabled=True, order=["alpha-user_created", "bravo-user_created", "charlie-user_created"], next=0, boots_per_theme=1)
  seen = [module.cycle_theme(advance=True, path=path) for _ in range(4)]
  assert seen == ["alpha-user_created", "bravo-user_created", "charlie-user_created", "alpha-user_created"]


def test_after_a_drive_the_theme_stays(tm):
  module, path = tm
  write(path, enabled=True, order=["alpha-user_created", "bravo-user_created"], next=0, boots_per_theme=1)
  assert module.cycle_theme(advance=True, path=path) == "alpha-user_created"
  assert module.cycle_theme(advance=False, path=path) == "alpha-user_created"
  assert module.cycle_theme(advance=False, path=path) == "alpha-user_created"
  assert module.cycle_theme(advance=True, path=path) == "bravo-user_created"


def test_deleted_themes_are_skipped(tm):
  module, path = tm
  write(path, enabled=True, order=["gone-user_created", "bravo-user_created"], next=0)
  assert module.cycle_theme(advance=True, path=path) == "bravo-user_created"


@pytest.mark.parametrize("content", [None, "{not json", json.dumps({"enabled": False, "order": ["alpha-user_created"]}),
                                     json.dumps({"enabled": True, "order": "alpha-user_created"})])
def test_cycle_off(tm, content):
  module, path = tm
  if content is not None:
    path.write_text(content)
  assert module.cycle_theme(advance=True, path=path) is None


def test_each_theme_stays_three_start_ups(tm):
  module, path = tm
  write(path, enabled=True, order=["alpha-user_created", "bravo-user_created"], next=0)
  seen = [module.cycle_theme(advance=True, path=path) for _ in range(7)]
  assert seen == ["alpha-user_created"] * 3 + ["bravo-user_created"] * 3 + ["alpha-user_created"]
  # drives and settings changes in between don't count
  assert module.cycle_theme(advance=False, path=path) == "alpha-user_created"
  assert module.cycle_status(path=path) == ("alpha-user_created", 2, "bravo-user_created")


def test_start_ups_already_shown_count(tm):
  module, path = tm
  write(path, enabled=True, order=["alpha-user_created", "bravo-user_created"], current="alpha-user_created", boots=2)
  assert [module.cycle_theme(advance=True, path=path) for _ in range(2)] == ["alpha-user_created", "bravo-user_created"]


def test_without_an_order_the_categories_take_turns(tm, tmp_path):
  module, path = tm
  packs = tmp_path / "theme_packs"
  for old in ("alpha", "bravo", "charlie"):
    (packs / f"{old}-user_created").rmdir()
  for name in ("paramotor", "skydive", "glass_cockpit", "honey_badger", "sloth", "campfire", "my_new_one"):
    for part in ("colors", "sounds"):
      (packs / f"{name}-user_created" / part).mkdir(parents=True)
  (packs / "tesla").mkdir()                                   # downloaded themes never join the cycle
  write(path, enabled=True)
  seen = [module.cycle_theme(advance=True, path=path) for _ in range(3 * 8)][::3]
  categories = {key: category for category, keys in module.keith_theme_groups([p.name for p in packs.iterdir()]) for key in keys}
  assert seen[0] == "paramotor-user_created" and seen[1] == "honey_badger-user_created"
  assert "tesla" not in seen and "my_new_one-user_created" in seen and len(set(seen[:7])) == 7
  assert all(categories[a] != categories[b] for a, b in zip(seen[:7], seen[1:7]))   # never the same category twice in a row


def test_only_keiths_themes_are_grouped(tm):
  module, _ = tm
  groups = module.keith_theme_groups(["frog-animated", "duck", "tesla", "sloth-user_created", "paramotor-user_created", "zzz-user_created"])
  assert groups == [("Aviation", ["paramotor-user_created"]), ("Animals", ["sloth-user_created"]), ("More", ["zzz-user_created"])]


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
  # a theme without its own wheel gets the stock wheel, never the paramotor wheel (2026-11-23)
  assert module.picked_theme_mappings("alpha-user_created", theme_wheels=True)["wheel_image"] == ("wheel_image", "stock")


def test_paramotor_wheel_is_never_used_while_theme_wheels_is_on():
  from pathlib import Path
  source = (Path(__file__).resolve().parents[1] / "theme_manager.py").read_text(encoding="utf-8")
  assert "KEITH_THEME_WHEELS = True" in source
  assert source.count('"wheel_image", KEITH_WHEEL)') == 0          # every KEITH_WHEEL use sits behind KEITH_THEME_WHEELS


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
  # the picked theme gets its own three start-ups, then the cycle goes on after it
  assert [module.cycle_theme(advance=True, path=path) for _ in range(4)] == ["bravo-user_created"] * 3 + ["charlie-user_created"]


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


def test_pond_allows_the_theme_picker_while_driving():
  from pathlib import Path
  root = Path(__file__).resolve().parents[2] / "system/the_pond"
  server = (root / "the_pond.py").read_text(encoding="utf-8")
  assert 'THEME_PICKER_API_PATH = "/api/theme_picker"' in server
  assert "for path in (NAVIGATION_API_PATH, THEME_PICKER_API_PATH)" in server
  page = (root / "assets/js/core.js").read_text(encoding="utf-8")
  assert 'viewFromPath() !== "theme_picker"' in page and '"open-theme-picker"' in page


def test_pond_picker_offers_only_keiths_themes():
  from pathlib import Path
  source = (Path(__file__).resolve().parents[2] / "system/the_pond/theme_picker.py").read_text(encoding="utf-8")
  assert "keith_theme_groups(ThemeManager.get_full_themes())" in source
  assert source.count("installed()") >= 3                     # icons, wheels and switching all use the filtered list


def test_real_categories_alternate(tm):
  module, _ = tm
  keys = [name + "-user_created" for names in module.KEITH_THEME_CATEGORIES.values() for name in names]
  groups = module.keith_theme_groups(keys)
  order = module.spread_order(groups)
  category = {key: name for name, members in groups for key in members}
  assert sorted(order) == sorted(keys) and order[0] == "paramotor-user_created"
  assert all(category[a] != category[b] for a, b in zip(order, order[1:]))


# ---------- themes bundled in the release ----------

def test_bundled_theme_installs_once_and_becomes_current(tm, tmp_path):
  module, path = tm
  bundle = tmp_path / "bundle"
  (bundle / "theme_packs" / "redman-user_created" / "colors").mkdir(parents=True)
  (bundle / "theme_packs" / "redman-user_created" / "colors" / "colors.json").write_text("{}")
  (bundle / "theme_packs" / "redman-user_created" / "sounds").mkdir()
  (bundle / "theme_packs" / "redman-user_created" / "sounds" / "engage.wav").write_bytes(b"RIFF")
  (bundle / "steering_wheels").mkdir()
  (bundle / "steering_wheels" / "redman-user_created.gif").write_bytes(b"GIF")
  wheels = tmp_path / "steering_wheels"
  wheels.mkdir(exist_ok=True)
  (wheels / "redman-user_created.png").write_bytes(b"old")
  write(path, enabled=True, current="alpha-user_created", boots=2)
  kwargs = dict(bundle=bundle, packs=tmp_path / "theme_packs", wheels=wheels, cycle_path=path)
  assert module.install_bundled_themes(**kwargs) == ["redman-user_created"]
  assert (tmp_path / "theme_packs" / "redman-user_created" / "colors" / "colors.json").is_file()
  assert [p.name for p in wheels.glob("redman-user_created.*")] == ["redman-user_created.gif"]
  saved = json.loads(path.read_text())
  assert saved["current"] == "redman-user_created" and saved["boots"] == 0
  # the next start-ups show it three times
  assert [module.cycle_theme(advance=True, path=path) for _ in range(3)] == ["redman-user_created"] * 3
  # nothing changes on the next start-up, and an updated bundle is copied again without taking over the cycle
  assert module.install_bundled_themes(**kwargs) == []
  (bundle / "theme_packs" / "redman-user_created" / "colors" / "colors.json").write_text('{"x": 1}')
  assert module.install_bundled_themes(**kwargs) == []
  assert "x" in (tmp_path / "theme_packs" / "redman-user_created" / "colors" / "colors.json").read_text()


def test_process_installs_bundled_themes_at_start():
  from pathlib import Path
  source = (Path(__file__).resolve().parents[2] / "frogpilot_process.py").read_text(encoding="utf-8")
  assert source.index("theme_manager = ThemeManager(") < source.index("install_bundled_themes()")


def test_photo_themes_have_their_own_category(tm):
  module, _ = tm
  assert module.KEITH_THEME_CATEGORIES["Photos"][:6] == ["redman", "camping", "travel", "liz", "liz_and_keith", "pets"]
  assert {"cruises", "alaska", "lennox", "family", "croatia", "lakes_and_mountains"} <= set(module.KEITH_THEME_CATEGORIES["Photos"])
  assert "redman" not in module.KEITH_THEME_CATEGORIES["Aviation"]
  assert list(module.KEITH_THEME_CATEGORIES)[0] == "Photos"                     # listed first in Pick a Theme


def test_redman_shows_first_when_several_bundled_themes_arrive(tm, tmp_path):
  module, path = tm
  bundle = tmp_path / "bundle"
  for key in ("camping-user_created", "pets-user_created", "redman-user_created"):
    (bundle / "theme_packs" / key).mkdir(parents=True)
    (bundle / "theme_packs" / key / "x.txt").write_text(key)
  write(path, enabled=True, current="alpha-user_created", boots=1)
  new = module.install_bundled_themes(bundle=bundle, packs=tmp_path / "theme_packs", wheels=tmp_path / "wheels", cycle_path=path)
  assert new[0] == "redman-user_created" and json.loads(path.read_text())["current"] == "redman-user_created"


# ---------- how themes change (The Pond settings) ----------

def make_packs(tmp_path, names):
  packs = tmp_path / "theme_packs"
  for old in ("alpha", "bravo", "charlie"):
    (packs / f"{old}-user_created").rmdir()
  for name in names:
    for part in ("colors", "sounds"):
      (packs / f"{name}-user_created" / part).mkdir(parents=True, exist_ok=True)
  return packs


def test_only_the_chosen_category(tm, tmp_path):
  module, path = tm
  make_packs(tmp_path, ["redman", "camping", "pets", "paramotor", "skydive", "sloth"])
  write(path, enabled=True, categories=["Photos"], boots_per_theme=1)
  seen = [module.cycle_theme(advance=True, path=path) for _ in range(6)]
  assert set(seen) == {"redman-user_created", "camping-user_created", "pets-user_created"}


def test_favorites_as_a_category(tm, tmp_path):
  module, path = tm
  make_packs(tmp_path, ["redman", "paramotor", "sloth"])
  write(path, enabled=True, categories=["Favorites"], favorites=["sloth-user_created", "paramotor-user_created"], boots_per_theme=1)
  assert {module.cycle_theme(advance=True, path=path) for _ in range(4)} == {"sloth-user_created", "paramotor-user_created"}


def test_random_never_repeats_back_to_back(tm, tmp_path):
  module, path = tm
  make_packs(tmp_path, ["redman", "camping", "pets", "paramotor", "skydive", "sloth"])
  write(path, enabled=True, mode="random", boots_per_theme=1)
  seen = [module.cycle_theme(advance=True, path=path) for _ in range(30)]
  assert all(a != b for a, b in zip(seen, seen[1:])) and len(set(seen)) >= 4


def test_keep_one_theme(tm, tmp_path):
  module, path = tm
  make_packs(tmp_path, ["redman", "camping"])
  write(path, enabled=True, mode="keep", current="camping-user_created", boots=9)
  assert [module.cycle_theme(advance=True, path=path) for _ in range(5)] == ["camping-user_created"] * 5
  assert module.peek_next_theme(path=path) == "redman-user_created"        # "Next theme now" still moves on


def test_a_pick_outside_the_categories_gets_its_turn(tm, tmp_path):
  module, path = tm
  make_packs(tmp_path, ["redman", "camping", "sloth"])
  write(path, enabled=True, categories=["Photos"], boots_per_theme=2)
  module.move_cycle_to("sloth-user_created", path)
  assert [module.cycle_theme(advance=True, path=path) for _ in range(3)][:2] == ["sloth-user_created"] * 2


def test_settings_round_trip(tm, tmp_path):
  module, path = tm
  write(path, enabled=True, order=["alpha-user_created"])
  s = module.update_theme_settings({"mode": "random", "boots_per_theme": 5, "categories": ["Photos", "Nope"], "enabled": True}, path)
  assert s["mode"] == "random" and s["boots_per_theme"] == 5 and s["categories"] == ["Photos"]
  assert "order" not in json.loads(path.read_text())                   # the category order takes over
  s = module.update_theme_settings({"favorite": "sloth-user_created"}, path)
  assert s["favorites"] == ["sloth-user_created"]
  s = module.update_theme_settings({"favorite": "sloth-user_created", "starred": False, "boots_per_theme": 99, "mode": "bogus"}, path)
  assert s["favorites"] == [] and s["boots_per_theme"] == 5 and s["mode"] == "random"


def test_pond_has_the_theme_settings():
  from pathlib import Path
  root = Path(__file__).resolve().parents[2] / "system/the_pond"
  server = (root / "theme_picker.py").read_text(encoding="utf-8")
  assert '@routes.post("/api/theme_picker/settings")' in server and '@routes.post("/api/theme_picker/next")' in server
  page = (root / "assets/js/pages/theme_picker.js").read_text(encoding="utf-8")
  for act in ("theme-mode", "theme-boots", "theme-category", "theme-star", "theme-next", "theme-enabled"):
    assert f'"{act}"' in page


def _bundle(tmp_path, key="redman-user_created"):
  bundle = tmp_path / "bundle"
  for part in ("colors", "sounds"):
    (bundle / "theme_packs" / key / part).mkdir(parents=True, exist_ok=True)
    (bundle / "theme_packs" / key / part / "x").write_text(part)
  (bundle / "steering_wheels").mkdir(exist_ok=True)
  (bundle / "steering_wheels" / f"{key}.gif").write_bytes(b"GIF1")
  return bundle


def test_a_wheel_only_change_is_installed(tm, tmp_path):
  module, path = tm
  bundle = _bundle(tmp_path)
  kwargs = dict(bundle=bundle, packs=tmp_path / "theme_packs", wheels=tmp_path / "wheels", cycle_path=path)
  module.install_bundled_themes(**kwargs)
  (bundle / "steering_wheels" / "redman-user_created.gif").write_bytes(b"GIF2")
  module.install_bundled_themes(**kwargs)
  assert (tmp_path / "wheels" / "redman-user_created.gif").read_bytes() == b"GIF2"


def test_a_deleted_bundled_theme_stays_deleted(tm, tmp_path):
  import shutil
  module, path = tm
  bundle = _bundle(tmp_path)
  packs = tmp_path / "theme_packs"
  kwargs = dict(bundle=bundle, packs=packs, wheels=tmp_path / "wheels", cycle_path=path)
  assert module.install_bundled_themes(**kwargs) == ["redman-user_created"]
  # deleting the whole theme (only the marker left) keeps it deleted, with no blank leftover
  for part in ("colors", "sounds"):
    shutil.rmtree(packs / "redman-user_created" / part)
  assert module.install_bundled_themes(**kwargs) == [] and not (packs / "redman-user_created").exists()
  assert module.install_bundled_themes(**kwargs) == [] and not (packs / "redman-user_created").exists()


def test_deleting_one_part_leaves_the_rest_alone(tm, tmp_path):
  import shutil
  module, path = tm
  bundle = _bundle(tmp_path)
  packs = tmp_path / "theme_packs"
  kwargs = dict(bundle=bundle, packs=packs, wheels=tmp_path / "wheels", cycle_path=path)
  module.install_bundled_themes(**kwargs)
  shutil.rmtree(packs / "redman-user_created" / "sounds")
  module.install_bundled_themes(**kwargs)
  assert (packs / "redman-user_created" / "colors").is_dir() and not (packs / "redman-user_created" / "sounds").exists()
  assert "redman-user_created" not in module.installed_keith_themes(packs)     # half a theme never joins the cycle


def test_an_interrupted_update_finishes_next_boot(tm, tmp_path):
  import shutil
  module, path = tm
  bundle = _bundle(tmp_path)
  packs = tmp_path / "theme_packs"
  kwargs = dict(bundle=bundle, packs=packs, wheels=tmp_path / "wheels", cycle_path=path)
  module.install_bundled_themes(**kwargs)
  shutil.copytree(packs / "redman-user_created", packs / ".redman-user_created.new")
  shutil.rmtree(packs / "redman-user_created")                 # power lost between removing the old copy and the rename
  module.install_bundled_themes(**kwargs)
  assert (packs / "redman-user_created" / "colors").is_dir()