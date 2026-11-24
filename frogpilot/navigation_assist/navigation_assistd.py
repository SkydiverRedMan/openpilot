#!/usr/bin/env python3
"""navigation_assistd: publishes the advisory navigationAssist message.

Inputs (read only):  navInstruction (navd), frogpilotNavigation (navd), carState
                     (speed, blind spots), modelV2 (lane line confidence), frogpilotPlan
                     (adjacent lane widths), frogpilotRadarState (adjacent-lane radar targets),
                     NavigationAssist / NavDestination / IsMetric / CarParamsPersistent params,
                     FrogPilotToggles (minimum lane change speed).
Output:              navigationAssist, read by the onroad UI.

This process never publishes anything that steering, gas, brake, turn signals or
lane-change logic consume. If it crashes, controlsd ignores it (see
IGNORE_PROCESSES) and openpilot keeps driving normally; the UI simply hides the
Navigation Assist banner once its message goes stale.
"""
from __future__ import annotations

import json
import time

from openpilot.frogpilot.navigation_assist.engine import (
  RADAR_ALONGSIDE_DISTANCE, Advisory, EngineInputs, Maneuver, NavSnapshot, NavigationAssistEngine,
)
from openpilot.frogpilot.navigation_assist.synthetic import SCENARIOS

RATE_HZ = 5.0
PARAM_POLL_INTERVAL = 0.5        # s; how fast turning the switch off takes effect
SYNTHETIC_MAX_SPEED = 0.5        # m/s; synthetic scenarios end once the car moves
CAR_PARAMS_POLL_INTERVAL = 10.0  # s
LANE_LINE_MIN_PROB = 0.5         # both ego lane lines must be at least this confident
DEFAULT_MIN_LANE_SPEED = 20 * 0.44704  # m/s; FrogPilot only estimates lane widths above its lane change speed
SERVICES = ["navInstruction", "frogpilotNavigation", "carState", "modelV2", "frogpilotPlan", "frogpilotRadarState"]

# Advisory attribute -> navigationAssist field
FIELD_MAP = {
  "enabled": "enabled",
  "state": "state",
  "kind": "maneuverKind",
  "direction": "direction",
  "maneuver_distance": "maneuverDistance",
  "time_to_maneuver": "timeToManeuver",
  "confidence": "confidence",
  "display_visible": "displayVisible",
  "urgency": "urgency",
  "headline": "headline",
  "distance_text": "distanceText",
  "detail": "detail",
  "route_changed": "routeChanged",
  "route_change_count": "routeChangeCount",
  "navigation_age": "navigationAge",
  "lane_info_available": "laneInfoAvailable",
  "blindspot_available": "blindspotAvailable",
  "adjacent_lane_left": "adjacentLaneLeft",
  "adjacent_lane_right": "adjacentLaneRight",
  "mapbox_lane_count": "mapboxLaneCount",
  "mapbox_active_lanes": "mapboxActiveLanes",
  "voice_prompt": "voicePrompt",
  "voice_prompt_count": "voicePromptCount",
}


def advisory_fields(advisory: Advisory, synthetic: bool) -> dict:
  fields = {capnp_name: getattr(advisory, attr) for attr, capnp_name in FIELD_MAP.items()}
  fields["synthetic"] = synthetic
  return fields


def snapshot_from_nav_instruction(valid: bool, nav) -> NavSnapshot:
  """Convert a navInstruction reader into a NavSnapshot."""
  return NavSnapshot(
    valid=valid,
    maneuver_distance=float(nav.maneuverDistance),
    maneuver_type=str(nav.maneuverType),
    maneuver_modifier=str(nav.maneuverModifier),
    primary_text=str(nav.maneuverPrimaryText),
    secondary_text=str(nav.maneuverSecondaryText),
    distance_remaining=float(nav.distanceRemaining),
    all_maneuvers=[Maneuver(float(m.distance), str(m.type), str(m.modifier)) for m in nav.allManeuvers],
    lanes_active=[bool(lane.active) for lane in nav.lanes],
  )


def read_enable_bsm(params) -> bool:
  data = params.get("CarParamsPersistent")
  if not data:
    return False
  try:
    from cereal import car
    with car.CarParams.from_bytes(data) as CP:
      return bool(CP.enableBsm)
  except Exception:
    return False


def radar_alongside(lead) -> bool:
  return bool(lead.status) and 0.0 <= float(lead.dRel) <= RADAR_ALONGSIDE_DISTANCE


class NavigationAssistDaemon:
  def __init__(self, sm, pm, params, params_memory, clock=time.monotonic):
    self.sm = sm
    self.pm = pm
    self.params = params
    self.params_memory = params_memory
    self.clock = clock

    self.engine = NavigationAssistEngine()

    self.enabled = False
    self.destination_set = False
    self.is_metric = False
    self.voice_enabled = False
    self.last_param_poll = -1e9
    self.enable_bsm = False
    self.last_car_params_poll = -1e9
    self.min_lane_speed = DEFAULT_MIN_LANE_SPEED

    self.nav: NavSnapshot | None = None
    self.nav_received_at: float | None = None

    self.synthetic_name: str | None = None
    self.synthetic_started: float = 0.0
    self.last_state: str | None = None

  def poll_params(self, now: float) -> None:
    if now - self.last_param_poll < PARAM_POLL_INTERVAL:
      return
    self.last_param_poll = now
    self.enabled = self.params.get_bool("NavigationAssist")
    self.destination_set = bool(self.params.get("NavDestination"))
    self.is_metric = self.params.get_bool("IsMetric")
    self.voice_enabled = self.params.get_bool("NavigationAssistVoice")

    if now - self.last_car_params_poll >= CAR_PARAMS_POLL_INTERVAL:
      self.last_car_params_poll = now
      self.enable_bsm = read_enable_bsm(self.params)
      try:
        toggles = json.loads(self.params_memory.get("FrogPilotToggles", encoding="utf-8") or "{}")
        self.min_lane_speed = float(toggles.get("minimum_lane_change_speed", DEFAULT_MIN_LANE_SPEED))
      except Exception:
        self.min_lane_speed = DEFAULT_MIN_LANE_SPEED

    name = self.params_memory.get("NavigationAssistSynthetic", encoding="utf-8") or None
    if name not in SCENARIOS:
      name = None
    if name != self.synthetic_name:
      self.synthetic_name = name
      self.synthetic_started = now
      self.engine.reset()
      self.nav = None
      self.nav_received_at = None

  def lane_inputs(self, v_ego: float) -> dict:
    """Read-only lane and traffic context for Milestone 2."""
    sm = self.sm
    out = {"blindspot_available": self.enable_bsm, "lane_info_expected": v_ego >= self.min_lane_speed + 0.5}
    if sm.seen["carState"]:
      out["blindspot_left"] = bool(sm["carState"].leftBlindspot)
      out["blindspot_right"] = bool(sm["carState"].rightBlindspot)
    if sm.seen["frogpilotRadarState"] and sm.alive["frogpilotRadarState"]:
      out["radar_left_alongside"] = radar_alongside(sm["frogpilotRadarState"].leadLeft)
      out["radar_right_alongside"] = radar_alongside(sm["frogpilotRadarState"].leadRight)

    model_ok = sm.seen["modelV2"] and sm.alive["modelV2"] and sm.valid["modelV2"]
    plan_ok = sm.seen["frogpilotPlan"] and sm.alive["frogpilotPlan"]
    if model_ok and plan_ok and v_ego >= self.min_lane_speed + 0.5:
      probs = list(sm["modelV2"].laneLineProbs)
      if len(probs) == 4 and probs[1] >= LANE_LINE_MIN_PROB and probs[2] >= LANE_LINE_MIN_PROB:
        out["lane_info_valid"] = True
        out["lane_width_left"] = float(sm["frogpilotPlan"].laneWidthLeft)
        out["lane_width_right"] = float(sm["frogpilotPlan"].laneWidthRight)
    return out

  def vehicle_moving(self) -> bool:
    return self.sm.seen["carState"] and self.sm["carState"].vEgo > SYNTHETIC_MAX_SPEED

  def step(self) -> dict:
    self.sm.update(0)
    now = self.clock()
    self.poll_params(now)

    nav_updated = False
    position_valid = True
    v_ego = self.sm["carState"].vEgo if self.sm.seen["carState"] else 0.0
    destination_set = self.destination_set

    if self.synthetic_name is not None and self.vehicle_moving():
      # Safety: synthetic data is for a parked car only.
      self.params_memory.remove("NavigationAssistSynthetic")
      self.synthetic_name = None
      self.engine.reset()
      self.nav = None
      self.nav_received_at = None

    lane = {}
    if self.synthetic_name is not None:
      scenario = SCENARIOS[self.synthetic_name]
      t = now - self.synthetic_started
      snapshot = scenario.snapshot(t)
      v_ego = scenario.speed
      destination_set = True
      lane = scenario.lane_context(t)
      if snapshot is not None and (self.nav_received_at is None or now - self.nav_received_at >= 1.0):
        self.nav = snapshot
        self.nav_received_at = now
        nav_updated = True
    else:
      if self.sm.updated["navInstruction"]:
        self.nav = snapshot_from_nav_instruction(self.sm.valid["navInstruction"], self.sm["navInstruction"])
        self.nav_received_at = now
        nav_updated = True
      if self.sm.seen["frogpilotNavigation"]:
        position_valid = self.sm.valid["frogpilotNavigation"]
      lane = self.lane_inputs(v_ego)

    advisory = self.engine.update(EngineInputs(
      now=now,
      enabled=self.enabled,
      destination_set=destination_set,
      v_ego=v_ego,
      nav=self.nav,
      nav_received_at=self.nav_received_at,
      nav_updated=nav_updated,
      position_valid=position_valid,
      is_metric=self.is_metric,
      voice_enabled=self.voice_enabled,
      **lane,
    ))

    if advisory.state != self.last_state:
      self.log_transition(advisory)
      self.last_state = advisory.state

    fields = advisory_fields(advisory, self.synthetic_name is not None)
    self.pm.send("navigationAssist", fields)
    return fields

  def log_transition(self, advisory: Advisory) -> None:
    try:
      from openpilot.common.swaglog import cloudlog
      cloudlog.event("navigation_assist.state", state=advisory.state, kind=advisory.kind, direction=advisory.direction,
                     distance=round(advisory.maneuver_distance), confidence=round(advisory.confidence, 2),
                     lane_info=advisory.lane_info_available, lane_left=advisory.adjacent_lane_left,
                     lane_right=advisory.adjacent_lane_right, synthetic=self.synthetic_name is not None)
    except Exception:
      pass


class _PubMaster:
  """Adapter so the daemon can hand plain dicts to cereal's PubMaster."""
  def __init__(self, messaging):
    self.messaging = messaging
    self.pm = messaging.PubMaster(["navigationAssist"])

  def send(self, service: str, fields: dict) -> None:
    msg = self.messaging.new_message(service, valid=True)
    out = getattr(msg, service)
    for key, value in fields.items():
      setattr(out, key, value)
    self.pm.send(service, msg)


def main():
  import cereal.messaging as messaging
  from openpilot.common.params import Params
  from openpilot.common.realtime import Ratekeeper

  sm = messaging.SubMaster(SERVICES)
  daemon = NavigationAssistDaemon(sm, _PubMaster(messaging), Params(), Params("/dev/shm/params"))

  rk = Ratekeeper(RATE_HZ, print_delay_threshold=None)
  while True:
    daemon.step()
    rk.keep_time()


if __name__ == "__main__":
  main()
