"""Unit tests for the Navigation Assist engine (pure Python, no device needed)."""
import pytest

from openpilot.frogpilot.navigation_assist import engine as E
from openpilot.frogpilot.navigation_assist.engine import (
  EngineInputs, Maneuver, NavSnapshot, NavigationAssistEngine, classify, format_distance, headline_for,
)

MPH = 0.44704


def nav(distance, mtype="off ramp", modifier="slight right", text="Exit 45", remaining=None, maneuvers=None, valid=True):
  if maneuvers is None:
    maneuvers = [Maneuver(distance, mtype, modifier), Maneuver(distance + 1000, "arrive", "right")]
  return NavSnapshot(valid=valid, maneuver_distance=distance, maneuver_type=mtype, maneuver_modifier=modifier,
                     primary_text=text, distance_remaining=remaining if remaining is not None else distance + 1000,
                     all_maneuvers=maneuvers)


class Driver:
  """Feeds an engine like navigation_assistd would: navd at 1 Hz, engine at 5 Hz."""
  def __init__(self, enabled=True, destination=True, metric=False):
    self.engine = NavigationAssistEngine()
    self.t = 100.0
    self.enabled = enabled
    self.destination = destination
    self.metric = metric
    self.nav = None
    self.nav_at = None
    self.position_valid = True

  def step(self, new_nav=None, v=0.0, dt=0.2):
    self.t += dt
    updated = False
    if new_nav is not None:
      self.nav, self.nav_at, updated = new_nav, self.t, True
    return self.engine.update(EngineInputs(now=self.t, enabled=self.enabled, destination_set=self.destination, v_ego=v,
                                           nav=self.nav, nav_received_at=self.nav_at, nav_updated=updated,
                                           position_valid=self.position_valid, is_metric=self.metric))

  def run(self, seconds, distance_fn, v, **kw):
    """Drive for `seconds`, publishing nav every second; distance_fn(t) gives the maneuver distance."""
    out = None
    steps = int(round(seconds / 0.2))
    for i in range(steps):
      publish = i % 5 == 0
      out = self.step(nav(distance_fn(i * 0.2), **kw) if publish else None, v=v)
    return out


# ---- classification -----------------------------------------------------

@pytest.mark.parametrize("mtype,modifier,kind,direction,headline", [
  ("off ramp", "slight right", E.KIND_EXIT, E.DIR_SLIGHT_RIGHT, "EXIT RIGHT"),
  ("off ramp", "slight left", E.KIND_EXIT, E.DIR_SLIGHT_LEFT, "EXIT LEFT"),
  ("off ramp", "right", E.KIND_EXIT, E.DIR_RIGHT, "EXIT RIGHT"),
  ("fork", "slight left", E.KIND_FORK, E.DIR_SLIGHT_LEFT, "KEEP LEFT"),
  ("fork", "slight right", E.KIND_FORK, E.DIR_SLIGHT_RIGHT, "KEEP RIGHT"),
  ("turn", "right", E.KIND_TURN, E.DIR_RIGHT, "TURN RIGHT"),
  ("turn", "left", E.KIND_TURN, E.DIR_LEFT, "TURN LEFT"),
  ("turn", "sharp left", E.KIND_TURN, E.DIR_SHARP_LEFT, "SHARP LEFT"),
  ("turn", "slight right", E.KIND_TURN, E.DIR_SLIGHT_RIGHT, "BEAR RIGHT"),
  ("turn", "uturn", E.KIND_UTURN, E.DIR_UTURN, "U-TURN"),
  ("merge", "slight left", E.KIND_MERGE, E.DIR_SLIGHT_LEFT, "MERGE LEFT"),
  ("on ramp", "right", E.KIND_ON_RAMP, E.DIR_RIGHT, "RAMP RIGHT"),
  ("roundabout", "right", E.KIND_ROUNDABOUT, E.DIR_RIGHT, "ROUNDABOUT"),
  ("arrive", "right", E.KIND_ARRIVE, E.DIR_RIGHT, "ARRIVE RIGHT"),
  ("arrive", "", E.KIND_ARRIVE, E.DIR_NONE, "ARRIVE"),
  ("continue", "left", E.KIND_TURN, E.DIR_LEFT, "TURN LEFT"),
  ("continue", "slight right", E.KIND_CONTINUE, E.DIR_SLIGHT_RIGHT, "BEAR RIGHT"),
  ("new name", "straight", E.KIND_CONTINUE, E.DIR_STRAIGHT, "CONTINUE"),
])
def test_classification_and_headline(mtype, modifier, kind, direction, headline):
  k, d = classify(mtype, modifier)
  assert (k, d) == (kind, direction)
  assert headline_for(k, d) == headline


def test_non_actionable_steps():
  assert not E.is_actionable(*classify("new name", "straight"))
  assert not E.is_actionable(*classify("continue", "straight"))
  assert not E.is_actionable(*classify("notification", ""))
  assert E.is_actionable(*classify("off ramp", "slight right"))


@pytest.mark.parametrize("meters,metric,text", [
  (1.8 * 1609.344, False, "1.8 MI"),
  (12 * 1609.344, False, "12 MI"),
  (0.25 * 1609.344, False, "0.2 MI"),
  (150, False, "500 FT"),
  (0, False, "0 FT"),
  (-50, False, "0 FT"),
  (2500, True, "2.5 KM"),
  (15000, True, "15 KM"),
  (430, True, "450 M"),
  (42, True, "40 M"),
])
def test_format_distance(meters, metric, text):
  assert format_distance(meters, metric) == text


# ---- master switch -----------------------------------------------------

def test_disabled_suppresses_everything():
  d = Driver(enabled=False)
  out = d.run(5, lambda t: 2000, v=30)
  assert out.state == E.DISABLED
  assert not out.display_visible and out.urgency == E.URGENCY_HIDDEN and out.headline == ""


def test_disable_is_immediate_and_reenable_is_clean():
  d = Driver()
  out = d.run(3, lambda t: 2000, v=30)
  assert out.display_visible

  d.enabled = False
  out = d.step(v=30)
  assert out.state == E.DISABLED and not out.display_visible

  d.enabled = True
  out = d.run(2, lambda t: 1900, v=30)
  assert out.display_visible and out.route_change_count == 0


# ---- navigation active / inactive ----------------------------------------

def test_no_destination_is_inactive_and_hidden():
  d = Driver(destination=False)
  out = d.step(v=20)
  assert out.state == E.NAVIGATION_INACTIVE and not out.display_visible


def test_invalid_nav_without_destination_is_inactive():
  d = Driver(destination=False)
  out = d.step(nav(0, valid=False))
  assert out.state == E.NAVIGATION_INACTIVE and not out.display_visible


def test_active_to_inactive_when_destination_cleared():
  d = Driver()
  out = d.run(3, lambda t: 6000, v=30)
  assert out.state == E.NAVIGATION_ACTIVE and out.display_visible
  d.destination = False
  d.nav = nav(0, valid=False)
  out = d.step(nav(0, valid=False))
  assert out.state == E.NAVIGATION_INACTIVE and not out.display_visible


def test_destination_without_route_waits_then_reports_unavailable():
  d = Driver()
  out = d.step(v=0)
  assert out.state == E.ROUTE_UNAVAILABLE and not out.display_visible  # route still calculating
  for _ in range(int(E.DESTINATION_GRACE / 0.2) + 2):
    out = d.step(v=0)
  assert out.state == E.ROUTE_UNAVAILABLE and out.display_visible
  assert out.urgency == E.URGENCY_WARNING and out.headline == "NAV DATA UNAVAILABLE"


# ---- stale data ------------------------------------------------------------

def test_stale_navigation_hides_maneuver():
  d = Driver()
  out = d.run(3, lambda t: 3000 - 30 * t, v=30)
  assert out.display_visible and out.headline == "EXIT RIGHT"
  # navd stops publishing
  for _ in range(int(E.STALE_AFTER / 0.2) + 2):
    out = d.step(v=30)
  assert out.state == E.ROUTE_UNAVAILABLE
  assert out.headline == "NAV DATA UNAVAILABLE" and out.distance_text == ""


def test_confidence_drops_as_data_ages():
  d = Driver()
  d.run(2, lambda t: 5000, v=30)
  fresh = d.step(v=30).confidence
  for _ in range(14):  # ~3 s without an update
    aging = d.step(v=30)
  assert aging.confidence < fresh


# ---- maneuvers, direction, distance -----------------------------------------

def test_right_exit_display():
  d = Driver()
  out = d.run(2, lambda t: 1.8 * 1609.344, v=0)
  assert out.kind == E.KIND_EXIT and out.direction == E.DIR_SLIGHT_RIGHT
  assert out.headline == "EXIT RIGHT" and out.distance_text == "1.8 MI"
  assert out.detail == "Exit 45"


def test_left_exit_display():
  d = Driver()
  out = d.run(2, lambda t: 2500, v=0, mtype="off ramp", modifier="slight left", text="Exit 12A")
  assert out.headline == "EXIT LEFT" and out.direction == E.DIR_SLIGHT_LEFT


def test_distance_counts_down_between_navd_updates():
  d = Driver()
  d.step(nav(3000), v=40)
  a = d.step(v=40)
  b = d.step(v=40)
  assert 3000 > a.maneuver_distance > b.maneuver_distance
  assert b.maneuver_distance == pytest.approx(3000 - 40 * 0.4, abs=0.5)


def test_distance_updates_track_navd():
  d = Driver()
  out = d.run(10, lambda t: 5000 - 38 * t, v=38)
  assert out.maneuver_distance == pytest.approx(5000 - 38 * 10, abs=60)


def test_skips_non_actionable_maneuvers():
  maneuvers = [Maneuver(800, "new name", "straight"), Maneuver(1500, "continue", "straight"), Maneuver(2600, "off ramp", "slight right")]
  d = Driver()
  out = d.step(nav(800, "new name", "straight", text="I-90 E", maneuvers=maneuvers), v=30)
  assert out.headline == "EXIT RIGHT"
  assert out.maneuver_distance == pytest.approx(2600, abs=1)
  assert out.detail == ""  # banner text belongs to the current (non-actionable) step


def test_no_actionable_maneuver():
  maneuvers = [Maneuver(800, "new name", "straight")]
  d = Driver()
  out = d.step(nav(800, "new name", "straight", maneuvers=maneuvers), v=30)
  assert out.state == E.NO_UPCOMING_MANEUVER and not out.display_visible


def test_passed_maneuvers_are_ignored():
  maneuvers = [Maneuver(-400, "turn", "left"), Maneuver(900, "turn", "right")]
  d = Driver()
  out = d.step(nav(900, "turn", "right", maneuvers=maneuvers), v=15)
  assert out.headline == "TURN RIGHT"


# ---- state transitions, speed awareness and hysteresis -------------------------

def test_highway_exit_progression():
  """88 mph toward a right exit 5 km away: active -> approaching -> imminent."""
  v = 88 * MPH
  d = Driver()
  states = []
  for i in range(int(130 / 0.2)):
    t = i * 0.2
    out = d.step(nav(max(0.0, 5000 - v * t)) if i % 5 == 0 else None, v=v)
    states.append(out.state)
  order = [s for i, s in enumerate(states) if i == 0 or s != states[i - 1]]
  assert order == [E.NAVIGATION_ACTIVE, E.MANEUVER_APPROACHING, E.MANEUVER_IMMINENT]


def test_higher_speed_gives_earlier_warning():
  def first_approach_distance(v):
    d = Driver()
    for i in range(int(400 / 0.2)):
      dist = 8000 - v * i * 0.2
      out = d.step(nav(dist) if i % 5 == 0 else None, v=v)
      if out.state == E.MANEUVER_APPROACHING:
        return out.maneuver_distance
    return None
  assert first_approach_distance(40) > first_approach_distance(20)


def test_hysteresis_prevents_flicker_at_threshold():
  d = Driver()
  d.run(3, lambda t: E.APPROACH_DISTANCE - 50, v=0)
  assert d.engine.state == E.MANEUVER_APPROACHING
  # GPS jitter pushes the distance just above the entry threshold
  states = set()
  for i in range(30):
    dist = E.APPROACH_DISTANCE + (60 if i % 2 else -40)
    states.add(d.step(nav(dist), v=0, dt=1.0).state)
  assert states == {E.MANEUVER_APPROACHING}


def test_relaxing_waits_for_dwell_time():
  d = Driver()
  d.run(2, lambda t: 9000, v=0)
  assert d.step(nav(300), v=0).state == E.MANEUVER_IMMINENT
  out = d.step(nav(9000), v=0)
  assert out.state == E.MANEUVER_IMMINENT  # too soon to relax
  for _ in range(int(E.MIN_STATE_DWELL / 0.2) + 1):
    out = d.step(v=0)
  assert out.state == E.NAVIGATION_ACTIVE


# ---- route changes -------------------------------------------------------------

def test_route_change_detected_on_new_maneuvers():
  d = Driver()
  d.run(3, lambda t: 4000, v=0)
  new_route = [Maneuver(6000, "off ramp", "slight left"), Maneuver(7000, "arrive", "left")]
  out = d.step(nav(6000, "off ramp", "slight left", maneuvers=new_route), v=0)
  assert out.route_changed and out.route_change_count == 1
  assert out.headline == "EXIT LEFT"
  for _ in range(int(E.ROUTE_CHANGE_HOLD / 0.2) + 2):
    out = d.step(v=0)
  assert not out.route_changed and out.route_change_count == 1


def test_route_change_detected_on_remaining_distance_jump():
  d = Driver()
  d.run(3, lambda t: 4000, v=0)
  out = d.step(nav(4000, remaining=9000), v=0)
  assert out.route_changed


def test_step_advance_is_not_a_route_change():
  maneuvers_a = [Maneuver(50, "off ramp", "slight right"), Maneuver(850, "turn", "right")]
  maneuvers_b = [Maneuver(-30, "off ramp", "slight right"), Maneuver(770, "turn", "right")]
  d = Driver()
  d.step(nav(50, maneuvers=maneuvers_a, remaining=1850), v=20)
  out = d.step(nav(770, "turn", "right", maneuvers=maneuvers_b, remaining=1770), v=20, dt=1.0)
  assert not out.route_changed and out.route_change_count == 0
  assert out.headline == "TURN RIGHT"


# ---- confidence ---------------------------------------------------------------

def test_position_invalid_hides_maneuver():
  d = Driver()
  d.run(2, lambda t: 3000, v=30)
  d.position_valid = False
  out = d.step(nav(3000), v=30)
  assert out.state == E.INSUFFICIENT_INFORMATION
  assert out.urgency == E.URGENCY_WARNING and out.distance_text == ""


def test_gps_jumps_reduce_confidence():
  d = Driver()
  d.run(3, lambda t: 5000 - 30 * t, v=30)
  steady = d.step(v=30).confidence
  # navd distance jumps around by hundreds of metres while the car drives steadily
  # (remaining distance held steady so this is not mistaken for a reroute)
  dist = 4900
  for i in range(8):
    dist += 600 if i % 2 else -600
    out = d.step(nav(dist, remaining=6000), v=30, dt=1.0)
  assert out.confidence < steady
  assert out.route_change_count == 0


def test_confidence_recovery_needs_margin():
  d = Driver()
  d.run(2, lambda t: 3000, v=0)
  d.position_valid = False
  assert d.step(nav(3000), v=0).state == E.INSUFFICIENT_INFORMATION
  d.position_valid = True
  out = d.step(nav(3000), v=0)
  assert out.state != E.INSUFFICIENT_INFORMATION and out.confidence >= E.CONFIDENCE_THRESHOLD + 0.1


def test_milestone_two_states_are_never_emitted():
  d = Driver()
  seen = set()
  for i in range(600):
    seen.add(d.step(nav(max(0.0, 6000 - 35 * i * 0.2)) if i % 5 == 0 else None, v=35).state)
  assert not seen & {E.PREPARE_LEFT, E.PREPARE_RIGHT, E.ALREADY_POSITIONED, E.TRAFFIC_DETECTED}
