"""Navigation Assist recommendation engine.

Pure Python with no openpilot imports, so the logic can be unit-tested anywhere.
navigation_assistd.py adapts cereal messages into NavSnapshot objects and turns
Advisory objects back into the navigationAssist message.

This module is advisory only. It never produces anything that reaches steering,
gas, brake, turn signals or lane-change logic.

Milestone 1 scope: understand the route (active / inactive / stale / rerouted),
extract the next actionable maneuver, its side and distance, and decide how
prominently to show it. Lane-level advice (PREPARE_LEFT / PREPARE_RIGHT /
ALREADY_POSITIONED / TRAFFIC_DETECTED) is reserved in the state list for
Milestone 2 and is never emitted yet.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# States, kinds and directions. The names match the enums in cereal/custom.capnp
# (NavigationAssist.State / ManeuverKind / Direction) so the daemon can pass them
# straight through.
# ---------------------------------------------------------------------------

DISABLED = "disabled"
NAVIGATION_INACTIVE = "navigationInactive"
NAVIGATION_ACTIVE = "navigationActive"
NO_UPCOMING_MANEUVER = "noUpcomingManeuver"
MANEUVER_APPROACHING = "maneuverApproaching"
MANEUVER_IMMINENT = "maneuverImminent"
ROUTE_UNAVAILABLE = "routeUnavailable"
INSUFFICIENT_INFORMATION = "insufficientInformation"
# Reserved for Milestone 2. Never produced by this version.
PREPARE_LEFT = "prepareLeft"
PREPARE_RIGHT = "prepareRight"
ALREADY_POSITIONED = "alreadyPositioned"
TRAFFIC_DETECTED = "trafficDetected"

KIND_NONE = "none"
KIND_TURN = "turn"
KIND_EXIT = "offRamp"
KIND_FORK = "fork"
KIND_MERGE = "merge"
KIND_ON_RAMP = "onRamp"
KIND_ROUNDABOUT = "roundabout"
KIND_CONTINUE = "continueRoute"
KIND_ARRIVE = "arrive"
KIND_UTURN = "uturn"
KIND_OTHER = "other"

DIR_NONE = "none"
DIR_LEFT = "left"
DIR_RIGHT = "right"
DIR_STRAIGHT = "straight"
DIR_SLIGHT_LEFT = "slightLeft"
DIR_SLIGHT_RIGHT = "slightRight"
DIR_SHARP_LEFT = "sharpLeft"
DIR_SHARP_RIGHT = "sharpRight"
DIR_UTURN = "uturn"

LEFT_DIRECTIONS = {DIR_LEFT, DIR_SLIGHT_LEFT, DIR_SHARP_LEFT}
RIGHT_DIRECTIONS = {DIR_RIGHT, DIR_SLIGHT_RIGHT, DIR_SHARP_RIGHT}

# Urgency levels for the UI (0 = hidden). Kept as plain ints so the UI only
# needs a colour lookup.
URGENCY_HIDDEN = 0
URGENCY_INFO = 1
URGENCY_APPROACHING = 2
URGENCY_IMMINENT = 3
URGENCY_WARNING = 4  # data problem (stale / uncertain)

# ---------------------------------------------------------------------------
# Tuning. Distances in metres, times in seconds.
# ---------------------------------------------------------------------------

STALE_AFTER = 4.0              # navd publishes at 1 Hz; 3+ missed messages is stale
DESTINATION_GRACE = 15.0       # time allowed for navd to calculate a route
ROUTE_CHANGE_HOLD = 4.0        # how long the "route updated" flag stays up
MIN_STATE_DWELL = 1.5          # minimum time in a display state before a non-urgent change
ACTIONABLE_LOOKBACK = -15.0    # maneuvers this far behind still count while passing them

# Approaching / imminent thresholds. Both a distance and a time-to-maneuver are
# used so that 85-90 mph highway driving gets earlier prompts than city driving.
APPROACH_DISTANCE = 3200.0     # ~2 mi
APPROACH_TIME = 100.0          # ~2.6 mi at 90 mph
IMMINENT_DISTANCE = 400.0      # ~1/4 mi
IMMINENT_TIME = 15.0           # ~0.6 mi at 90 mph
EXIT_HYSTERESIS = 1.15         # leave a band only after moving 15% back out of it

MIN_SPEED_FOR_TIME = 5.0       # m/s floor so a stopped car does not divide by zero

CONFIDENCE_THRESHOLD = 0.6     # below this the maneuver is not shown
CONSISTENCY_SLACK = 60.0       # m of disagreement between navd and odometry tolerated per update

METERS_PER_MILE = 1609.344
METERS_PER_FOOT = 0.3048

MANEUVER_TYPE_TO_KIND = {
  "turn": KIND_TURN,
  "end of road": KIND_TURN,
  "off ramp": KIND_EXIT,
  "fork": KIND_FORK,
  "merge": KIND_MERGE,
  "on ramp": KIND_ON_RAMP,
  "roundabout": KIND_ROUNDABOUT,
  "rotary": KIND_ROUNDABOUT,
  "roundabout turn": KIND_ROUNDABOUT,
  "exit roundabout": KIND_ROUNDABOUT,
  "exit rotary": KIND_ROUNDABOUT,
  "continue": KIND_CONTINUE,
  "new name": KIND_CONTINUE,
  "notification": KIND_CONTINUE,
  "arrive": KIND_ARRIVE,
  "depart": KIND_OTHER,
}

MODIFIER_TO_DIRECTION = {
  "left": DIR_LEFT,
  "right": DIR_RIGHT,
  "straight": DIR_STRAIGHT,
  "slight left": DIR_SLIGHT_LEFT,
  "slight right": DIR_SLIGHT_RIGHT,
  "sharp left": DIR_SHARP_LEFT,
  "sharp right": DIR_SHARP_RIGHT,
  "uturn": DIR_UTURN,
}


@dataclass
class Maneuver:
  distance: float
  type: str = ""
  modifier: str = ""


@dataclass
class NavSnapshot:
  """One navInstruction message, reduced to what the engine needs."""
  valid: bool
  maneuver_distance: float = 0.0
  maneuver_type: str = ""
  maneuver_modifier: str = ""
  primary_text: str = ""
  secondary_text: str = ""
  distance_remaining: float = 0.0
  all_maneuvers: list[Maneuver] = field(default_factory=list)
  lane_count: int = 0          # informational for Milestone 2


@dataclass
class EngineInputs:
  now: float                          # monotonic seconds
  enabled: bool                       # NavigationAssist param
  destination_set: bool               # NavDestination param is non-empty
  v_ego: float = 0.0                  # m/s, for dead reckoning and time-to-maneuver
  nav: NavSnapshot | None = None      # newest navInstruction, None if never received
  nav_received_at: float | None = None
  nav_updated: bool = False           # nav is a new message this cycle
  position_valid: bool = True         # frogpilotNavigation.valid (localizer ok and on route)
  is_metric: bool = False


@dataclass
class Advisory:
  enabled: bool = False
  state: str = DISABLED
  kind: str = KIND_NONE
  direction: str = DIR_NONE
  maneuver_distance: float = 0.0
  time_to_maneuver: float = 0.0
  confidence: float = 0.0
  display_visible: bool = False
  urgency: int = URGENCY_HIDDEN
  headline: str = ""
  distance_text: str = ""
  detail: str = ""
  route_changed: bool = False
  route_change_count: int = 0
  navigation_age: float = -1.0


def classify(maneuver_type: str, modifier: str) -> tuple[str, str]:
  """Turn Mapbox maneuver type/modifier strings into (kind, direction)."""
  maneuver_type = (maneuver_type or "").strip().lower()
  modifier = (modifier or "").strip().lower()

  kind = MANEUVER_TYPE_TO_KIND.get(maneuver_type, KIND_OTHER if maneuver_type else KIND_NONE)
  direction = MODIFIER_TO_DIRECTION.get(modifier, DIR_NONE)

  if direction == DIR_UTURN and kind in (KIND_TURN, KIND_CONTINUE, KIND_OTHER):
    kind = KIND_UTURN

  # "continue" with a real turn modifier is a bend the driver has to take
  if kind == KIND_CONTINUE and direction not in (DIR_NONE, DIR_STRAIGHT):
    kind = KIND_TURN if direction in (DIR_LEFT, DIR_RIGHT, DIR_SHARP_LEFT, DIR_SHARP_RIGHT) else KIND_CONTINUE

  return kind, direction


def is_actionable(kind: str, direction: str) -> bool:
  """True when the maneuver asks the driver to do something."""
  if kind in (KIND_NONE, KIND_OTHER):
    return direction not in (DIR_NONE, DIR_STRAIGHT)
  if kind == KIND_CONTINUE:
    return direction in (DIR_SLIGHT_LEFT, DIR_SLIGHT_RIGHT)
  return True


def side_word(direction: str) -> str:
  if direction in LEFT_DIRECTIONS:
    return "LEFT"
  if direction in RIGHT_DIRECTIONS:
    return "RIGHT"
  return ""


def headline_for(kind: str, direction: str) -> str:
  side = side_word(direction)
  if kind == KIND_EXIT:
    return f"EXIT {side}".strip() if side else "EXIT"
  if kind == KIND_FORK:
    return f"KEEP {side}".strip() if side else "FORK AHEAD"
  if kind == KIND_MERGE:
    return f"MERGE {side}".strip() if side else "MERGE"
  if kind == KIND_ON_RAMP:
    return f"RAMP {side}".strip() if side else "TAKE RAMP"
  if kind == KIND_ROUNDABOUT:
    return "ROUNDABOUT"
  if kind == KIND_ARRIVE:
    return f"ARRIVE {side}".strip() if side else "ARRIVE"
  if kind == KIND_UTURN or direction == DIR_UTURN:
    return "U-TURN"
  if kind == KIND_CONTINUE:
    return f"BEAR {side}".strip() if side else "CONTINUE"
  if direction in (DIR_SLIGHT_LEFT, DIR_SLIGHT_RIGHT):
    return f"BEAR {side}"
  if direction in (DIR_SHARP_LEFT, DIR_SHARP_RIGHT):
    return f"SHARP {side}"
  if side:
    return f"TURN {side}"
  return "CONTINUE"


def format_distance(meters: float, is_metric: bool) -> str:
  meters = max(0.0, meters)
  if is_metric:
    if meters >= 1000.0:
      km = meters / 1000.0
      return f"{km:.0f} KM" if km >= 10 else f"{km:.1f} KM"
    return f"{int(round(meters / 50.0) * 50)} M" if meters >= 100 else f"{int(round(meters / 10.0) * 10)} M"

  miles = meters / METERS_PER_MILE
  if miles >= 0.2:
    return f"{miles:.0f} MI" if miles >= 10 else f"{miles:.1f} MI"
  feet = meters / METERS_PER_FOOT
  return f"{int(round(feet / 50.0) * 50)} FT"


def route_signature(nav: NavSnapshot) -> tuple:
  """Identity of a route that stays fixed while driving along it.

  navd keeps every maneuver of the route in allManeuvers, including ones already
  passed, so the type/modifier sequence only changes when the route itself
  changes (new destination or reroute).
  """
  return tuple((m.type, m.modifier) for m in nav.all_maneuvers)


class NavigationAssistEngine:
  def __init__(self):
    self.reset()

  def reset(self):
    self.signature: tuple | None = None
    self.last_distance_remaining: float | None = None
    self.route_change_count = 0
    self.route_changed_at: float | None = None
    self.destination_set_at: float | None = None

    self.last_nav_time: float | None = None
    self.last_nav_distance: float | None = None
    self.last_nav_key: tuple | None = None
    self.inconsistency = 0.0

    self.state = DISABLED
    self.state_since = 0.0
    self.band = 0  # 0 = far, 1 = approaching, 2 = imminent

  # ---- helpers ----------------------------------------------------------

  def _set_state(self, state: str, now: float, urgent: bool = False) -> str:
    if state == self.state:
      return self.state
    if not urgent and (now - self.state_since) < MIN_STATE_DWELL:
      return self.state
    self.state = state
    self.state_since = now
    return self.state

  def _next_actionable(self, nav: NavSnapshot) -> tuple[Maneuver, str, str, bool] | None:
    """Pick the next maneuver the driver has to act on.

    Returns (maneuver, kind, direction, is_current_step). Falls back to the
    current step's banner when allManeuvers is empty.
    """
    for m in sorted(nav.all_maneuvers, key=lambda m: m.distance):
      if m.distance < ACTIONABLE_LOOKBACK:
        continue
      kind, direction = classify(m.type, m.modifier)
      if is_actionable(kind, direction):
        current = abs(m.distance - nav.maneuver_distance) < 5.0
        return m, kind, direction, current

    if not nav.all_maneuvers and (nav.maneuver_type or nav.maneuver_modifier):
      kind, direction = classify(nav.maneuver_type, nav.maneuver_modifier)
      m = Maneuver(nav.maneuver_distance, nav.maneuver_type, nav.maneuver_modifier)
      return m, kind, direction, True
    return None

  def _update_route_identity(self, nav: NavSnapshot, now: float) -> None:
    signature = route_signature(nav)
    changed = False
    if self.signature is not None and signature != self.signature:
      changed = True
    if (self.last_distance_remaining is not None and
        nav.distance_remaining > self.last_distance_remaining + max(300.0, 0.1 * self.last_distance_remaining)):
      changed = True  # remaining distance jumped up: reroute

    if changed:
      self.route_change_count += 1
      self.route_changed_at = now
      self.inconsistency = 0.0
      self.last_nav_distance = None
      self.last_nav_key = None
      self.band = 0

    self.signature = signature
    self.last_distance_remaining = nav.distance_remaining

  def _update_consistency(self, inputs: EngineInputs, key: tuple, distance: float) -> None:
    """Compare navd's distance drop with odometry to catch GPS jumps."""
    now = inputs.now
    if self.last_nav_time is not None and self.last_nav_distance is not None and key == self.last_nav_key:
      dt = max(0.0, now - self.last_nav_time)
      expected = inputs.v_ego * dt
      actual = self.last_nav_distance - distance
      error = abs(actual - expected)
      score = min(1.0, max(0.0, (error - CONSISTENCY_SLACK) / (CONSISTENCY_SLACK + 0.5 * expected)))
      self.inconsistency = 0.6 * self.inconsistency + 0.4 * score
    else:
      self.inconsistency *= 0.6
    self.last_nav_time = now
    self.last_nav_distance = distance
    self.last_nav_key = key

  def _band_for(self, distance: float, time_to: float) -> int:
    approach_d = APPROACH_DISTANCE
    approach_t = APPROACH_TIME
    imminent_d = IMMINENT_DISTANCE
    imminent_t = IMMINENT_TIME
    if self.band >= 2:
      imminent_d *= EXIT_HYSTERESIS
      imminent_t *= EXIT_HYSTERESIS
    if self.band >= 1:
      approach_d *= EXIT_HYSTERESIS
      approach_t *= EXIT_HYSTERESIS

    if distance <= imminent_d or time_to <= imminent_t:
      return 2
    if distance <= approach_d or time_to <= approach_t:
      return 1
    return 0

  # ---- main entry -------------------------------------------------------

  def update(self, inputs: EngineInputs) -> Advisory:
    now = inputs.now
    out = Advisory(enabled=inputs.enabled, route_change_count=self.route_change_count)

    if not inputs.enabled:
      # Master switch off: forget everything so re-enabling starts clean.
      self.reset()
      self.state = DISABLED
      self.state_since = now
      out.state = DISABLED
      return out

    if inputs.destination_set:
      if self.destination_set_at is None:
        self.destination_set_at = now
    else:
      self.destination_set_at = None

    nav = inputs.nav
    age = (now - inputs.nav_received_at) if inputs.nav_received_at is not None else math.inf
    out.navigation_age = age if math.isfinite(age) else -1.0

    # --- No destination: nothing to show -------------------------------
    if not inputs.destination_set and (nav is None or not nav.valid or age > STALE_AFTER):
      self.signature = None
      self.last_distance_remaining = None
      self.band = 0
      out.state = self._set_state(NAVIGATION_INACTIVE, now, urgent=True)
      return out

    # --- Destination set but no usable route ---------------------------
    if nav is None or age > STALE_AFTER or not nav.valid:
      waiting = self.destination_set_at is not None and (now - self.destination_set_at) < DESTINATION_GRACE
      out.state = self._set_state(ROUTE_UNAVAILABLE, now, urgent=True)
      out.display_visible = not waiting
      out.urgency = URGENCY_WARNING if out.display_visible else URGENCY_HIDDEN
      out.headline = "NAV DATA UNAVAILABLE"
      out.detail = "Navigation route is stale or missing"
      self.band = 0
      return out

    # --- Fresh route ----------------------------------------------------
    if inputs.nav_updated:
      self._update_route_identity(nav, now)
    out.route_change_count = self.route_change_count
    out.route_changed = self.route_changed_at is not None and (now - self.route_changed_at) < ROUTE_CHANGE_HOLD

    picked = self._next_actionable(nav)
    if picked is None:
      out.state = self._set_state(NO_UPCOMING_MANEUVER, now)
      out.confidence = 1.0
      out.headline = "NO UPCOMING MANEUVER"
      return out

    maneuver, kind, direction, is_current = picked

    # Dead-reckon between 1 Hz navd updates so the distance counts down smoothly.
    since = max(0.0, now - inputs.nav_received_at) if inputs.nav_received_at is not None else 0.0
    distance = max(0.0, maneuver.distance - inputs.v_ego * since)
    time_to = distance / max(inputs.v_ego, MIN_SPEED_FOR_TIME)

    if inputs.nav_updated:
      self._update_consistency(inputs, (maneuver.type, maneuver.modifier), maneuver.distance)

    # --- Confidence ----------------------------------------------------
    freshness = 1.0 if age <= 1.5 else max(0.0, 1.0 - (age - 1.5) / (STALE_AFTER - 1.5))
    completeness = 1.0 if (maneuver.type and kind not in (KIND_NONE, KIND_OTHER)) else 0.7
    if direction == DIR_NONE and kind not in (KIND_ROUNDABOUT, KIND_ARRIVE):
      completeness *= 0.8
    position = 1.0 if inputs.position_valid else 0.3
    consistency = 1.0 - 0.6 * self.inconsistency
    confidence = max(0.0, min(1.0, freshness * completeness * position * consistency))

    out.kind = kind
    out.direction = direction
    out.maneuver_distance = distance
    out.time_to_maneuver = time_to
    out.confidence = confidence
    out.headline = headline_for(kind, direction)
    out.distance_text = format_distance(distance, inputs.is_metric)
    if is_current:
      out.detail = (nav.primary_text or "").strip()

    # Hysteresis: once hidden for low confidence, require a margin before showing again.
    threshold = CONFIDENCE_THRESHOLD + (0.1 if self.state == INSUFFICIENT_INFORMATION else 0.0)
    if confidence < threshold:
      out.state = self._set_state(INSUFFICIENT_INFORMATION, now, urgent=True)
      out.display_visible = True
      out.urgency = URGENCY_WARNING
      out.headline = "NAV POSITION UNCERTAIN"
      out.distance_text = ""
      out.detail = "Maneuver hidden until navigation data is reliable"
      return out

    self.band = self._band_for(distance, time_to)
    if self.band == 2:
      state, urgency = MANEUVER_IMMINENT, URGENCY_IMMINENT
    elif self.band == 1:
      state, urgency = MANEUVER_APPROACHING, URGENCY_APPROACHING
    else:
      state, urgency = NAVIGATION_ACTIVE, URGENCY_INFO

    # Moving toward more urgency is immediate; relaxing waits for the dwell time.
    urgent = {NAVIGATION_ACTIVE: 0, MANEUVER_APPROACHING: 1, MANEUVER_IMMINENT: 2}.get(state, 0) > \
             {NAVIGATION_ACTIVE: 0, MANEUVER_APPROACHING: 1, MANEUVER_IMMINENT: 2}.get(self.state, -1)
    out.state = self._set_state(state, now, urgent=urgent)
    out.urgency = {NAVIGATION_ACTIVE: URGENCY_INFO, MANEUVER_APPROACHING: URGENCY_APPROACHING,
                   MANEUVER_IMMINENT: URGENCY_IMMINENT}.get(out.state, urgency)
    out.display_visible = True
    return out
