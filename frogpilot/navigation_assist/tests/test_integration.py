"""Checks that Navigation Assist is wired consistently across Python, the schema,
compiled param keys, services, the process list and the UI sources.

The schema test needs pycapnp; the process test needs the full openpilot Python
environment. Each skips cleanly when its dependency is missing.
"""
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from openpilot.frogpilot.navigation_assist import engine as E
from openpilot.frogpilot.navigation_assist import navigation_assistd as D

ROOT = Path(__file__).resolve().parents[3]


def read(relative):
  return (ROOT / relative).read_text(encoding="utf-8")


def capnp_enum(struct_text, enum_name):
  block = re.search(rf"enum {enum_name} @0x[0-9a-f]+ \{{(.*?)\}}", struct_text, re.S).group(1)
  return [m.group(1) for m in re.finditer(r"^\s*(\w+) @\d+;", block, re.M)]


def navigation_assist_struct():
  text = read("cereal/custom.capnp")
  start = text.index("struct NavigationAssist ")
  return text[start:]


def test_engine_names_match_schema_enums():
  struct = navigation_assist_struct()
  states = capnp_enum(struct, "State")
  kinds = capnp_enum(struct, "ManeuverKind")
  directions = capnp_enum(struct, "Direction")

  engine_states = {v for k, v in vars(E).items() if k.isupper() and isinstance(v, str) and v in states}
  for name in ("DISABLED", "NAVIGATION_INACTIVE", "NAVIGATION_ACTIVE", "NO_UPCOMING_MANEUVER", "MANEUVER_APPROACHING",
               "MANEUVER_IMMINENT", "ROUTE_UNAVAILABLE", "INSUFFICIENT_INFORMATION", "PREPARE_LEFT", "PREPARE_RIGHT",
               "ALREADY_POSITIONED", "TRAFFIC_DETECTED"):
    assert getattr(E, name) in states, name
  assert engine_states == set(states)

  assert {v for k, v in vars(E).items() if k.startswith("KIND_")} == set(kinds)
  assert {v for k, v in vars(E).items() if k.startswith("DIR_")} == set(directions)


def test_field_map_matches_schema_fields():
  struct = navigation_assist_struct()
  body = struct[:struct.index("enum State")]
  fields = set(re.findall(r"^\s*(\w+) @\d+ :", body, re.M))
  assert set(D.FIELD_MAP.values()) | {"synthetic"} == fields


def test_event_and_service_registered():
  assert re.search(r"navigationAssist @\d+ :Custom\.NavigationAssist;", read("cereal/log.capnp"))
  assert '"navigationAssist": (' in read("cereal/services.py")


def test_params_registered_in_compiled_key_list():
  params_cc = read("common/params.cc")
  assert '{"NavigationAssist", PERSISTENT}' in params_cc
  assert '"NavigationAssistSynthetic", CLEAR_ON_MANAGER_START' in params_cc


def test_default_is_off():
  text = read("frogpilot/common/frogpilot_variables.py")
  assert '("NavigationAssist", "0", 0, "0")' in text
  assert "toggle.navigation_assist = self.get_value(\"NavigationAssist\")" in text


def test_process_isolated_from_controls():
  assert '"navigation_assistd"' in re.search(r"IGNORE_PROCESSES = \{[^}]*\}", read("selfdrive/controls/controlsd.py")).group(0)
  assert 'PythonProcess("navigation_assistd", "frogpilot.navigation_assist.navigation_assistd", run_navigation_assist)' in \
    read("system/manager/process_config.py")


def test_navigation_assist_publishes_nothing_drivers_read():
  """The daemon may only publish navigationAssist; nothing in the control path may subscribe to it."""
  source = read("frogpilot/navigation_assist/navigation_assistd.py")
  assert re.findall(r"PubMaster\(\[(.*?)\]\)", source) == ['"navigationAssist"']
  for path in ("selfdrive/controls", "selfdrive/car", "frogpilot/controls", "selfdrive/modeld", "frogpilot/selfdrive/modeld"):
    for file in (ROOT / path).rglob("*.py"):
      assert "navigationAssist" not in file.read_text(encoding="utf-8", errors="ignore"), file


def test_ui_reads_message_and_toggle():
  ui = read("frogpilot/ui/frogpilot_ui.cc")
  assert '"navigationAssist"' in ui
  camera = read("frogpilot/ui/qt/onroad/frogpilot_annotated_camera.cc")
  assert 'frogpilot_toggles.value(QLatin1String("navigation_assist"))' in camera
  assert 'fpsm.alive("navigationAssist")' in camera
  settings = read("frogpilot/ui/qt/offroad/navigation_settings.cc")
  assert 'new ParamControl("NavigationAssist"' in settings


def test_schema_builds_message():
  capnp = pytest.importorskip("capnp")
  capnp.remove_import_hook()
  log = capnp.load(str(ROOT / "cereal/log.capnp"), imports=[str(ROOT / "cereal")])

  advisory = E.Advisory(enabled=True, state=E.MANEUVER_APPROACHING, kind=E.KIND_EXIT, direction=E.DIR_SLIGHT_RIGHT,
                        maneuver_distance=2896.8, time_to_maneuver=73.6, confidence=0.95, display_visible=True,
                        urgency=E.URGENCY_APPROACHING, headline="EXIT RIGHT", distance_text="1.8 MI", detail="Exit 45",
                        route_change_count=2, navigation_age=0.4)
  event = log.Event.new_message()
  msg = event.init("navigationAssist")
  for key, value in D.advisory_fields(advisory, synthetic=True).items():
    setattr(msg, key, value)

  with log.Event.from_bytes(event.to_bytes()) as decoded:
    round_trip = decoded.navigationAssist
    check_round_trip(round_trip)


def check_round_trip(round_trip):
  assert round_trip.state == "maneuverApproaching"
  assert round_trip.maneuverKind == "offRamp" and round_trip.direction == "slightRight"
  assert round_trip.headline == "EXIT RIGHT" and round_trip.distanceText == "1.8 MI"
  assert round_trip.synthetic and round_trip.urgency == 2 and round_trip.routeChangeCount == 2


def test_manager_runs_process_only_when_enabled_and_started():
  pytest.importorskip("cereal.messaging")
  from cereal import car
  from openpilot.system.manager.process_config import managed_processes
  proc = managed_processes["navigation_assistd"]
  CP = car.CarParams.new_message()
  for started in (False, True):
    for enabled in (False, True):
      toggles = SimpleNamespace(navigation_assist=enabled)
      assert proc.should_run(started, None, CP, toggles) == (started and enabled)
