"""Tests for navigation_assistd using fake SubMaster / PubMaster / Params.

These run without msgq or a device. test_integration.py checks the same fields
against the real cereal schema.
"""
from types import SimpleNamespace

import pytest

from openpilot.frogpilot.navigation_assist import engine as E
from openpilot.frogpilot.navigation_assist import navigation_assistd as D
from openpilot.frogpilot.navigation_assist.synthetic import SCENARIOS


class FakeParams:
  def __init__(self, values=None):
    self.values = dict(values or {})

  def get(self, key, encoding=None):
    value = self.values.get(key)
    if value is None:
      return None
    if encoding is None:
      return value.encode() if isinstance(value, str) else value
    return value.decode() if isinstance(value, bytes) else value

  def get_bool(self, key):
    return self.values.get(key) in ("1", b"1", True)

  def put(self, key, value):
    self.values[key] = value

  def put_bool(self, key, value):
    self.values[key] = "1" if value else "0"

  def remove(self, key):
    self.values.pop(key, None)


def nav_msg(distance, mtype="off ramp", modifier="slight right", text="Exit 45", remaining=None):
  maneuvers = [SimpleNamespace(distance=distance, type=mtype, modifier=modifier),
               SimpleNamespace(distance=distance + 1000, type="arrive", modifier="right")]
  return SimpleNamespace(maneuverDistance=distance, maneuverType=mtype, maneuverModifier=modifier,
                         maneuverPrimaryText=text, maneuverSecondaryText="", distanceRemaining=remaining or distance + 1000,
                         allManeuvers=maneuvers, lanes=[])


class FakeSubMaster:
  SERVICES = ("navInstruction", "frogpilotNavigation", "carState")

  def __init__(self):
    self.data = {"carState": SimpleNamespace(vEgo=0.0), "navInstruction": None, "frogpilotNavigation": SimpleNamespace()}
    self.updated = dict.fromkeys(self.SERVICES, False)
    self.seen = dict.fromkeys(self.SERVICES, False)
    self.valid = dict.fromkeys(self.SERVICES, True)
    self.pending = {}

  def publish(self, service, msg, valid=True):
    self.pending[service] = (msg, valid)

  def update(self, timeout=0):
    self.updated = dict.fromkeys(self.SERVICES, False)
    for service, (msg, valid) in self.pending.items():
      self.data[service] = msg
      self.updated[service] = True
      self.seen[service] = True
      self.valid[service] = valid
    self.pending = {}

  def __getitem__(self, key):
    return self.data[key]


class FakePubMaster:
  def __init__(self):
    self.sent = []

  def send(self, service, fields):
    self.sent.append((service, fields))


class Clock:
  def __init__(self):
    self.t = 1000.0

  def __call__(self):
    return self.t


def make(enabled=True, destination=True, synthetic=None):
  params = FakeParams({"NavigationAssist": "1" if enabled else "0", "IsMetric": "0"})
  if destination:
    params.put("NavDestination", '{"latitude": 43.0, "longitude": -75.0}')
  params_memory = FakeParams({"NavigationAssistSynthetic": synthetic} if synthetic else {})
  sm, pm, clock = FakeSubMaster(), FakePubMaster(), Clock()
  daemon = D.NavigationAssistDaemon(sm, pm, params, params_memory, clock=clock)
  return daemon, sm, pm, params, params_memory, clock


def tick(daemon, clock, dt=0.2):
  clock.t += dt
  return daemon.step()


def test_publishes_only_navigation_assist():
  daemon, sm, pm, *_ , clock = make()
  for _ in range(10):
    tick(daemon, clock)
  assert {service for service, _ in pm.sent} == {"navigationAssist"}


def test_field_map_covers_every_advisory_attribute():
  attrs = set(E.Advisory().__dict__)
  assert attrs == set(D.FIELD_MAP)


def test_shows_next_maneuver_from_nav_instruction():
  daemon, sm, pm, params, _, clock = make()
  sm.data["carState"] = SimpleNamespace(vEgo=30.0)
  sm.seen["carState"] = True
  sm.publish("navInstruction", nav_msg(2900))
  out = tick(daemon, clock)
  assert out["enabled"] and out["displayVisible"]
  assert out["headline"] == "EXIT RIGHT" and out["distanceText"] == "1.8 MI"
  assert out["maneuverKind"] == E.KIND_EXIT and out["direction"] == E.DIR_SLIGHT_RIGHT
  assert out["synthetic"] is False


def test_switch_off_takes_effect_within_poll_interval():
  daemon, sm, pm, params, _, clock = make()
  sm.publish("navInstruction", nav_msg(2900))
  assert tick(daemon, clock)["displayVisible"]

  params.put_bool("NavigationAssist", False)
  out = tick(daemon, clock, dt=D.PARAM_POLL_INTERVAL)
  assert out["state"] == E.DISABLED and not out["displayVisible"] and not out["enabled"]


def test_invalid_frogpilot_navigation_lowers_confidence():
  daemon, sm, pm, params, _, clock = make()
  sm.publish("navInstruction", nav_msg(2900))
  sm.publish("frogpilotNavigation", SimpleNamespace(), valid=False)
  out = tick(daemon, clock)
  assert out["state"] == E.INSUFFICIENT_INFORMATION


def test_invalid_nav_instruction_without_destination_is_inactive():
  daemon, sm, pm, params, _, clock = make(destination=False)
  sm.publish("navInstruction", nav_msg(0), valid=False)
  out = tick(daemon, clock, dt=D.PARAM_POLL_INTERVAL)
  assert out["state"] == E.NAVIGATION_INACTIVE and not out["displayVisible"]


def test_stale_when_navd_stops():
  daemon, sm, pm, params, _, clock = make()
  sm.publish("navInstruction", nav_msg(2900))
  tick(daemon, clock)
  out = None
  for _ in range(int(E.STALE_AFTER / 0.2) + 2):
    out = tick(daemon, clock)
  assert out["state"] == E.ROUTE_UNAVAILABLE and out["headline"] == "NAV DATA UNAVAILABLE"


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_synthetic_scenarios_run_when_parked(name):
  daemon, sm, pm, params, params_memory, clock = make(destination=False, synthetic=name)
  sm.publish("carState", SimpleNamespace(vEgo=0.0))
  out = tick(daemon, clock)
  assert out["synthetic"] is True
  states = set()
  for _ in range(int(60 / 0.2)):
    out = tick(daemon, clock)
    states.add(out["state"])
  assert E.DISABLED not in states and E.NAVIGATION_INACTIVE not in states


def test_synthetic_highway_exit_shows_right_exit():
  daemon, sm, pm, params, params_memory, clock = make(destination=False, synthetic="highway_exit_right")
  out = None
  for _ in range(5):
    out = tick(daemon, clock)
  assert out["headline"] == "EXIT RIGHT" and out["displayVisible"] and out["synthetic"]


def test_synthetic_stops_when_vehicle_moves():
  daemon, sm, pm, params, params_memory, clock = make(destination=False, synthetic="highway_exit_right")
  for _ in range(5):
    assert tick(daemon, clock)["synthetic"]
  sm.publish("carState", SimpleNamespace(vEgo=3.0))
  out = tick(daemon, clock)
  assert out["synthetic"] is False
  assert "NavigationAssistSynthetic" not in params_memory.values
  assert out["state"] == E.NAVIGATION_INACTIVE and not out["displayVisible"]


def test_unknown_synthetic_scenario_is_ignored():
  daemon, sm, pm, params, params_memory, clock = make(destination=False, synthetic="does_not_exist")
  out = tick(daemon, clock)
  assert out["synthetic"] is False


def test_daemon_restart_reads_persisted_switch():
  """Simulates a device restart: a fresh daemon reads the persisted NavigationAssist param."""
  params = FakeParams({"NavigationAssist": "1"})
  for _ in range(2):
    sm, pm, clock = FakeSubMaster(), FakePubMaster(), Clock()
    daemon = D.NavigationAssistDaemon(sm, pm, params, FakeParams(), clock=clock)
    assert tick(daemon, clock)["enabled"] is True
