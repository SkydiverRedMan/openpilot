"""Saved speed limits: the store, the speed limit controller's priority, the planner's save request, and The Pond API.

Runs without a full openpilot build: heavy openpilot modules are replaced with small stand-ins for each test.
Needs pytest, numpy, pycapnp 2.0.0 and aiohttp.
"""
import asyncio
import importlib
import json
import os
import sys
import types

from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[4]

MPH = 0.44704


# ---------- helpers ----------

def stub_module(monkeypatch, name, **attributes):
  module = types.ModuleType(name)
  for key, value in attributes.items():
    setattr(module, key, value)
  monkeypatch.setitem(sys.modules, name, module)
  return module


def fresh_import(monkeypatch, name):
  monkeypatch.delitem(sys.modules, name, raising=False)
  return importlib.import_module(name)


@pytest.fixture
def store(tmp_path, monkeypatch):
  module = fresh_import(monkeypatch, "openpilot.frogpilot.controls.lib.saved_speed_limits")
  paths = importlib.import_module("openpilot.frogpilot.common.frogpilot_paths")
  monkeypatch.setattr(paths, "SAVED_SPEED_LIMITS_PATH", tmp_path / "saved_speed_limits.json")
  monkeypatch.setattr(paths, "SAVED_SPEED_LIMITS_BACKUP_PATH", tmp_path / "media" / "saved_speed_limits_backup.json")
  return module


class FakeClock:
  def __init__(self):
    self.now = 100.0

  def __call__(self):
    return self.now


# ---------- the store ----------

def test_paths_are_outside_the_install_folder():
  paths = importlib.import_module("openpilot.frogpilot.common.frogpilot_paths")
  for path in (paths.SAVED_SPEED_LIMITS_PATH, paths.SAVED_SPEED_LIMITS_BACKUP_PATH):
    assert not path.as_posix().startswith("/data/openpilot")
    assert path.as_posix().startswith("/data/")


def test_save_get_remove_and_persist(store, tmp_path):
  limits = store.SavedSpeedLimits()
  assert limits.get(123, True) == 0

  assert limits.save(123, True, 45 * MPH, road_name="Main Street", latitude=40.1, longitude=-75.2, background=False)
  assert limits.get(123, True) == pytest.approx(45 * MPH)
  assert limits.get(123, False) == 0  # each direction is separate

  reopened = store.SavedSpeedLimits()
  assert reopened.get(123, True) == pytest.approx(45 * MPH)
  entry = reopened.entries["123_1"]
  assert entry["road_name"] == "Main Street" and entry["saved"].endswith("Z")

  backup = json.loads((tmp_path / "media" / "saved_speed_limits_backup.json").read_text(encoding="utf-8"))
  assert backup["speed_limits"][0]["way_id"] == 123

  assert limits.remove(123, True, background=False)
  assert not limits.remove(123, True, background=False)
  assert store.SavedSpeedLimits().get(123, True) == 0


@pytest.mark.parametrize("entry", [
  {"way_id": 0, "is_forward": True, "speed_limit": 20.0},
  {"way_id": -5, "is_forward": True, "speed_limit": 20.0},
  {"way_id": True, "is_forward": True, "speed_limit": 20.0},
  {"way_id": 5, "is_forward": 1, "speed_limit": 20.0},
  {"way_id": 5, "is_forward": True, "speed_limit": 0.5},
  {"way_id": 5, "is_forward": True, "speed_limit": 60.0},
  {"way_id": 5, "is_forward": True, "speed_limit": "45"},
  "not a dict",
])
def test_invalid_entries_are_rejected(store, entry):
  assert store.normalize_entry(entry) is None


def test_background_save_reaches_the_file(store):
  limits = store.SavedSpeedLimits()
  limits.save(7, False, 30 * MPH)
  for _ in range(200):
    if store.read_entries():
      break
    asyncio.run(asyncio.sleep(0.01))
  assert store.read_entries()["7_0"]["speed_limit"] == pytest.approx(30 * MPH)


def test_damaged_file_falls_back_to_backup(store, tmp_path):
  limits = store.SavedSpeedLimits()
  limits.save(9, True, 55 * MPH, background=False)
  (tmp_path / "saved_speed_limits.json").write_text("{not json")
  assert store.SavedSpeedLimits().get(9, True) == pytest.approx(55 * MPH)


def test_planner_copy_reloads_after_the_pond_edits(store):
  clock = FakeClock()
  limits = store.SavedSpeedLimits(clock=clock)
  limits.save(1, True, 25 * MPH, background=False)

  # The Pond changes the file
  store.modify(lambda entries: entries.update({"1_1": {**entries["1_1"], "speed_limit": 35 * MPH}}))
  limits.refresh()
  assert limits.get(1, True) == pytest.approx(25 * MPH)  # not re-checked within a second

  clock.now += 1.5
  limits.refresh()
  assert limits.get(1, True) == pytest.approx(35 * MPH)


def test_planner_save_keeps_a_pond_edit_it_has_not_seen(store):
  limits = store.SavedSpeedLimits(clock=FakeClock())
  limits.save(1, True, 25 * MPH, background=False)
  store.modify(lambda entries: entries.update({"2_0": {"way_id": 2, "is_forward": False, "speed_limit": 40 * MPH}}))

  limits.save(3, True, 50 * MPH, background=False)
  assert set(store.read_entries()) == {"1_1", "2_0", "3_1"}


def test_way_key_round_trip(store):
  assert store.parse_way_key(store.way_key(987654321, True)) == (987654321, True)
  for bad in ("", "12", "12_2", "abc_1", "0_1", "-3_1"):
    with pytest.raises(ValueError):
      store.parse_way_key(bad)


# ---------- the speed limit controller ----------

@pytest.fixture
def slc_module(monkeypatch):
  sources = {"CAMERA": "Camera", "DASHBOARD": "Dashboard", "MAPBOX": "Mapbox", "MAP_DATA": "Map Data", "NAVIGATION": "Navigation",
             "NONE": "None", "SAVED": "Saved"}

  class FakeParams:
    def __init__(self):
      self.values = {}

    def get(self, key, encoding=None):
      return self.values.get(key)

    def get_float(self, key):
      return float(self.values.get(key, 0))

    def put_float_nonblocking(self, key, value):
      self.values[key] = value

    def put_nonblocking(self, key, value):
      self.values[key] = value

    def put_bool_nonblocking(self, key, value):
      self.values[key] = value

  stub_module(monkeypatch, "requests", Session=lambda: SimpleNamespace(close=lambda: None, get=None), RequestException=Exception)
  stub_module(monkeypatch, "openpilot.common.realtime", DT_MDL=0.05)
  stub_module(monkeypatch, "openpilot.common.swaglog", cloudlog=SimpleNamespace(warning=lambda *a, **k: None))
  stub_module(monkeypatch, "openpilot.selfdrive.navd.helpers", maxspeed_to_ms=lambda maxspeed: 0)
  frogpilot_variables = stub_module(monkeypatch, "openpilot.frogpilot.common.frogpilot_variables",
                                    SPEED_LIMIT_SOURCES=sources, params=FakeParams(), MAPBOX_MONTHLY_REQUEST_LIMIT=100000)
  common = importlib.import_module("openpilot.frogpilot.common")
  monkeypatch.setattr(common, "frogpilot_variables", frogpilot_variables, raising=False)
  return fresh_import(monkeypatch, "openpilot.frogpilot.controls.lib.speed_limit_controller")


class FakeFiller:
  def get_speed_limit(self, way, map_speed_limit):
    return map_speed_limit


class FakeSaved:
  def __init__(self, limits=None):
    self.limits = limits or {}

  def get(self, way_id, is_forward):
    return self.limits.get((way_id, is_forward), 0)


class FakeSM(dict):
  def __init__(self, camera=0.0):
    super().__init__({
      "carControl": SimpleNamespace(longActive=True),
      "controlsState": SimpleNamespace(experimentalMode=False, enabled=True),
      "frogpilotCarState": SimpleNamespace(dashboardSpeedLimit=0.0),
      "frogpilotNavigation": SimpleNamespace(navigationSpeedLimit=0.0),
      "frogpilotSignReading": SimpleNamespace(speedLimit=camera),
    })
    self.alive = {"frogpilotSignReading": True}


def make_slc(slc_module, saved=None, **toggles):
  planner = SimpleNamespace(speed_limit_filler=FakeFiller(), saved_speed_limits=FakeSaved(saved), accel_pressed=False, decel_pressed=False,
                            experimental_mode_pressed=False)
  slc = slc_module.SpeedLimitController(SimpleNamespace(frogpilot_planner=planner))
  slc.frogpilot_toggles = SimpleNamespace(**{
    "conditional_experimental_mode": False, "is_metric": False, "map_speed_lookahead_higher": 5, "map_speed_lookahead_lower": 5,
    "slc_fallback_experimental_mode": False, "slc_fallback_previous_speed_limit": False, "slc_mapbox_filler": False,
    "speed_limit_confirmation_higher": False, "speed_limit_confirmation_lower": False, "speed_limit_controller": True,
    "speed_limit_filler": True, "speed_limit_priority1": "Camera", "speed_limit_priority2": "Map Data",
    "speed_limit_priority3": "Navigation", "speed_limit_priority4": "None", "speed_limit_priority_highest": False,
    "speed_limit_priority_lowest": False, **toggles,
  })
  return slc


def map_match(way_id=100, is_forward=True, speed_limit=35 * MPH, next_speed_limits=()):
  return {"way_id": way_id, "is_forward": is_forward, "speed_limit": speed_limit, "next_speed_limits": list(next_speed_limits)}


def run(slc, match, camera=0.0, v_ego=20.0):
  slc.update_limits(None, match, None, False, v_ego, FakeSM(camera))


def test_saved_limit_beats_camera_and_map(slc_module):
  slc = make_slc(slc_module, saved={(100, True): 45 * MPH})
  run(slc, map_match(), camera=25 * MPH)
  assert slc.source == "Saved"
  assert slc.target == pytest.approx(45 * MPH)
  assert slc.saved_speed_limit == pytest.approx(45 * MPH)


def test_without_a_saved_limit_the_old_priorities_apply(slc_module):
  slc = make_slc(slc_module)
  run(slc, map_match(), camera=25 * MPH)
  assert slc.source == "Camera" and slc.target == pytest.approx(25 * MPH)

  run(slc, map_match(), camera=0)
  assert slc.source == "Map Data" and slc.target == pytest.approx(35 * MPH)


@pytest.mark.parametrize("mode", ["speed_limit_priority_highest", "speed_limit_priority_lowest"])
def test_saved_limit_beats_highest_and_lowest_modes(slc_module, mode):
  slc = make_slc(slc_module, saved={(100, True): 40 * MPH}, **{mode: True})
  run(slc, map_match(speed_limit=55 * MPH), camera=25 * MPH)
  assert slc.source == "Saved" and slc.target == pytest.approx(40 * MPH)


def test_saved_limit_needs_no_confirmation(slc_module):
  slc = make_slc(slc_module, saved={(100, True): 45 * MPH}, speed_limit_confirmation_higher=True, speed_limit_confirmation_lower=True)
  run(slc, map_match(way_id=99), camera=25 * MPH)  # a road with no saved limit: camera 25
  assert slc.target == pytest.approx(25 * MPH)

  run(slc, map_match(), camera=25 * MPH)  # onto the saved road
  assert slc.source == "Saved" and slc.target == pytest.approx(45 * MPH)


def test_saved_limit_ends_when_leaving_the_road(slc_module):
  slc = make_slc(slc_module, saved={(100, True): 45 * MPH})
  run(slc, map_match(), camera=25 * MPH)
  run(slc, map_match(way_id=101), camera=25 * MPH)
  assert slc.source == "Camera" and slc.saved_speed_limit == 0


def test_saved_limit_is_per_direction(slc_module):
  slc = make_slc(slc_module, saved={(100, True): 45 * MPH})
  run(slc, map_match(is_forward=False), camera=25 * MPH)
  assert slc.source == "Camera"


def test_upcoming_saved_limit_uses_the_lookahead(slc_module):
  upcoming = {"way_id": 200, "is_forward": True, "distance": 80.0, "speed_limit": 35 * MPH}
  slc = make_slc(slc_module, saved={(200, True): 25 * MPH})

  run(slc, map_match(next_speed_limits=[upcoming]), v_ego=20.0)  # 80 m < 5 s * 20 m/s
  assert slc.saved_speed_limit == pytest.approx(25 * MPH)

  far = {**upcoming, "distance": 500.0}
  run(slc, map_match(next_speed_limits=[far]), v_ego=20.0)
  assert slc.saved_speed_limit == 0


def test_no_map_match_means_no_saved_limit(slc_module):
  slc = make_slc(slc_module, saved={(100, True): 45 * MPH})
  run(slc, {}, camera=25 * MPH)
  assert slc.saved_speed_limit == 0 and slc.source == "Camera"


# ---------- the planner's save request ----------

def load_planner_handler(monkeypatch):
  """Load FrogPilotPlanner.handle_saved_speed_limit_request without importing the whole planner."""
  source = (REPO / "frogpilot/controls/frogpilot_planner.py").read_text(encoding="utf-8")
  start = source.index("  def handle_saved_speed_limit_request")
  end = source.index("  def is_lead_relevant")
  namespace = {"frogpilot_variables": SimpleNamespace(params_memory=SimpleNamespace(get=lambda key, encoding=None: "Main Street"))}
  exec("class Planner:\n" + source[start:end], namespace)
  return namespace["Planner"]


def test_planner_saves_clears_and_fails(monkeypatch, store):
  Planner = load_planner_handler(monkeypatch)
  planner = Planner()
  planner.saved_speed_limits = store.SavedSpeedLimits()
  gps = {"latitude": 40.0, "longitude": -75.0}

  planner.saved_speed_limit_request = 45 * MPH
  planner.handle_saved_speed_limit_request(gps, map_match())
  assert planner.saved_speed_limit_event == "saved"
  assert planner.saved_speed_limit_request is None
  assert planner.saved_speed_limits.get(100, True) == pytest.approx(45 * MPH)
  assert planner.saved_speed_limits.entries["100_1"]["road_name"] == "Main Street"

  planner.saved_speed_limit_request = 0.0
  planner.handle_saved_speed_limit_request(gps, map_match())
  assert planner.saved_speed_limit_event == "cleared"
  assert planner.saved_speed_limits.get(100, True) == 0

  planner.saved_speed_limit_request = 45 * MPH
  planner.handle_saved_speed_limit_request(None, {})
  assert planner.saved_speed_limit_event == "failed"


# ---------- schema and wiring ----------

def test_schema_has_the_new_fields():
  capnp = pytest.importorskip("capnp")
  try:
    from cereal import custom  # full openpilot environment: schema already loaded (loading it again is a duplicate ID)
  except ImportError:
    capnp.remove_import_hook()
    custom = capnp.load(str(REPO / "cereal/custom.capnp"), imports=[str(REPO / "cereal"), str(REPO / "cereal/include")])

  event = custom.FrogPilotUIEvent.new_message()
  event.saveSpeedLimit = 20.1
  assert event.which() == "saveSpeedLimit"

  plan = custom.FrogPilotPlan.new_message(slcSavedSpeedLimit=20.1)
  assert plan.slcSavedSpeedLimit == pytest.approx(20.1)

  names = custom.FrogPilotCarEvent.EventName.schema.enumerants
  for name in ("speedLimitSaved", "speedLimitCleared", "speedLimitSaveFailed"):
    assert name in names
    assert names[name] > names["youveGotMail"]  # outside the random-event range


def test_every_new_event_has_an_alert():
  events_source = (REPO / "selfdrive/controls/lib/events.py").read_text(encoding="utf-8")
  for name in ("speedLimitSaved", "speedLimitCleared", "speedLimitSaveFailed"):
    assert f"FrogPilotEventName.{name}: {{" in events_source


def test_ui_sends_and_reads_the_new_fields():
  ui = (REPO / "frogpilot/ui/frogpilot_ui.cc").read_text(encoding="utf-8")
  assert "setSaveSpeedLimit(speedLimit)" in ui
  camera = (REPO / "frogpilot/ui/qt/onroad/frogpilot_annotated_camera.cc").read_text(encoding="utf-8")
  assert "getSlcSavedSpeedLimit()" in camera
  onroad = (REPO / "selfdrive/ui/qt/onroad/onroad_home.cc").read_text(encoding="utf-8")
  assert onroad.index("speedLimitAccepted()") < onroad.index("frogpilot_nvg->openSpeedLimitPicker();")  # FrogPilot's pending sign keeps priority


def test_cruise_choice_only_up_to_85_mph():
  camera = (REPO / "frogpilot/ui/qt/onroad/frogpilot_annotated_camera.cc").read_text(encoding="utf-8")
  body = camera[camera.index("float FrogPilotAnnotatedCameraWidget::cruiseSpeedAsLimit()"):]
  body = body[:body.index("\n}\n")]
  assert "metric ? 140 : 85" in body and "cruise > highest" in body and "!isCruiseSet" in body

  # The picker adds the cruise setting as its own blue choice, only when cruiseSpeedAsLimit() allows it
  opener = camera[camera.index("void FrogPilotAnnotatedCameraWidget::openSpeedLimitPicker()"):]
  opener = opener[:opener.index("\n}\n")]
  assert "cruiseSpeedAsLimit()" in opener and "if (cruiseLimit > 0.0f)" in opener and "QRect(), true}" in opener
  painter = camera[camera.index("void FrogPilotAnnotatedCameraWidget::paintSpeedLimitPicker"):]
  painter = painter[:painter.index("\n}\n")]
  assert "MY CRUISE" in painter and "cruiseColor" in painter and "cruiseRight" in painter and "cruiseBelow" in painter


def test_touching_the_sign_opens_the_picker_without_hold_timing():
  onroad = (REPO / "selfdrive/ui/qt/onroad/onroad_home.cc").read_text(encoding="utf-8")
  press = onroad[onroad.index("void OnroadWindow::mousePressEvent"):]
  press = press[:press.index("\n}\n")]
  assert "frogpilot_nvg->openSpeedLimitPicker();" in press
  for gone in ("signHoldTimer", "signHeld", "mouseReleaseEvent", "setInterval(800)"):
    assert gone not in onroad
  header = (REPO / "selfdrive/ui/qt/onroad/onroad_home.h").read_text(encoding="utf-8")
  assert "signHoldTimer" not in header and "mouseReleaseEvent" not in header

  wiring = (REPO / "selfdrive/ui/qt/onroad/annotated_camera.cc").read_text(encoding="utf-8")
  assert "frogpilot_nvg->cruiseSetSpeed = setSpeed;" in wiring


# ---------- The Pond ----------

@pytest.fixture
def pond(tmp_path, monkeypatch, store):
  aiohttp = pytest.importorskip("aiohttp")
  from aiohttp import web
  from aiohttp.test_utils import TestClient, TestServer

  filler_path = tmp_path / "speed_limit_filler.json"
  paths = importlib.import_module("openpilot.frogpilot.common.frogpilot_paths")
  monkeypatch.setattr(paths, "SPEED_LIMIT_FILLER_PATH", filler_path)

  def load_json_file(path):
    try:
      return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
      return {}

  def update_json_file(path, data):
    Path(path).write_text(json.dumps(data))

  utilities_module = importlib.import_module("openpilot.frogpilot.common")
  frogpilot_utilities = stub_module(monkeypatch, "openpilot.frogpilot.common.frogpilot_utilities",
                                    load_json_file=load_json_file, update_json_file=update_json_file)
  monkeypatch.setattr(utilities_module, "frogpilot_utilities", frogpilot_utilities, raising=False)

  async def read_json(request):
    body = await request.json()
    if not isinstance(body, dict):
      raise web.HTTPBadRequest(text="invalid_json")
    return body

  pond_key = web.AppKey("the_pond", object)
  stub_module(monkeypatch, "openpilot.frogpilot.system.the_pond.utilities", THE_POND=pond_key, read_json=read_json)
  module = fresh_import(monkeypatch, "openpilot.frogpilot.system.the_pond.saved_speed_limits")

  class Params:
    def __init__(self):
      self.values = {"IsMetric": False, "IsOnroad": False}

    def get_bool(self, key):
      return self.values[key]

  the_pond = SimpleNamespace(params=Params())

  def call(method, path, body=None):
    async def go():
      app = web.Application()
      app[pond_key] = the_pond
      app.add_routes(module.routes)
      async with TestClient(TestServer(app)) as client:
        response = await client.request(method, path, json=body)
        text = await response.text()
        return response.status, (json.loads(text) if text and response.content_type == "application/json" else text), response.headers
    return asyncio.run(go())

  return SimpleNamespace(call=call, the_pond=the_pond, filler_path=filler_path, store=store)


def test_pond_list_edit_remove(pond):
  limits = pond.store.SavedSpeedLimits()
  limits.save(100, True, 45 * MPH, road_name="Main Street", background=False)

  status, data, _ = pond.call("GET", "/api/saved_speed_limits")
  assert status == 200 and data["metric"] is False
  assert data["speed_limits"] == [{"key": "100_1", "latitude": None, "longitude": None, "road_name": "Main Street",
                                   "saved": data["speed_limits"][0]["saved"], "speed_limit": 45}]

  status, _, _ = pond.call("PUT", "/api/saved_speed_limits/100_1", {"speed_limit": 40})
  assert status == 200
  assert pond.store.read_entries()["100_1"]["speed_limit"] == pytest.approx(40 * MPH)

  assert pond.call("PUT", "/api/saved_speed_limits/100_1", {"speed_limit": 300})[0] == 400
  assert pond.call("PUT", "/api/saved_speed_limits/100_1", {"speed_limit": "40"})[0] == 400
  assert pond.call("PUT", "/api/saved_speed_limits/555_1", {"speed_limit": 40})[0] == 404
  assert pond.call("PUT", "/api/saved_speed_limits/bad", {"speed_limit": 40})[0] == 404

  assert pond.call("DELETE", "/api/saved_speed_limits/100_1")[0] == 204
  assert pond.store.read_entries() == {}


def test_pond_metric_units(pond):
  pond.the_pond.params.values["IsMetric"] = True
  pond.store.SavedSpeedLimits().save(5, False, 50 / 3.6, background=False)
  assert pond.call("GET", "/api/saved_speed_limits")[1]["speed_limits"][0]["speed_limit"] == 50


def test_pond_backup_and_restore(pond):
  pond.store.SavedSpeedLimits().save(100, True, 45 * MPH, road_name="Main Street", background=False)
  pond.filler_path.write_text(json.dumps({"confirmations": [{"way_id": 1, "is_forward": True, "speed_limit": 11.2, "month": "2026-11"}],
                                          "speed_limits": [{"way_id": 2, "is_forward": True, "speed_limit": 13.4, "distance": 50}]}))

  status, backup, headers = pond.call("GET", "/api/saved_speed_limits/export")
  assert status == 200 and "attachment" in headers["Content-Disposition"]
  assert backup["kind"] == "frogpilot-speed-limits-backup"
  assert len(backup["learned"]["speed_limits"]) == 1 and len(backup["saved"]["speed_limits"]) == 1

  # A fresh device: nothing saved, nothing learned
  pond.store.modify(lambda entries: entries.clear())
  pond.filler_path.unlink()

  status, result, _ = pond.call("POST", "/api/saved_speed_limits/import", backup)
  assert status == 200
  assert result == {"learned_added": 1, "learned_skipped": False, "reboot_required": True, "saved_restored": 1}
  assert pond.store.read_entries()["100_1"]["road_name"] == "Main Street"
  learned = json.loads(pond.filler_path.read_text(encoding="utf-8"))
  assert len(learned["speed_limits"]) == 1 and len(learned["confirmations"]) == 1

  # Restoring again adds nothing new to the learned file
  status, result, _ = pond.call("POST", "/api/saved_speed_limits/import", backup)
  assert result["learned_added"] == 0 and result["reboot_required"] is False


def test_pond_restore_keeps_learned_roads_the_device_knows(pond):
  pond.filler_path.write_text(json.dumps({"speed_limits": [{"way_id": 2, "is_forward": True, "speed_limit": 20.0}]}))
  backup = {"kind": "frogpilot-speed-limits-backup", "saved": {"speed_limits": []},
            "learned": {"speed_limits": [{"way_id": 2, "is_forward": True, "speed_limit": 11.0}, {"way_id": 3, "is_forward": False, "speed_limit": 15.0}]}}
  result = pond.call("POST", "/api/saved_speed_limits/import", backup)[1]
  assert result["learned_added"] == 1
  learned = {(e["way_id"], e["is_forward"]): e["speed_limit"] for e in json.loads(pond.filler_path.read_text(encoding="utf-8"))["speed_limits"]}
  assert learned == {(2, True): 20.0, (3, False): 15.0}


def test_pond_restore_skips_learned_while_driving(pond):
  pond.the_pond.params.values["IsOnroad"] = True
  backup = {"kind": "frogpilot-speed-limits-backup", "saved": {"speed_limits": []},
            "learned": {"speed_limits": [{"way_id": 3, "is_forward": False, "speed_limit": 15.0}]}}
  result = pond.call("POST", "/api/saved_speed_limits/import", backup)[1]
  assert result["learned_skipped"] is True and not pond.filler_path.exists()


def test_pond_rejects_other_files(pond):
  assert pond.call("POST", "/api/saved_speed_limits/import", {"hello": 1})[0] == 400
