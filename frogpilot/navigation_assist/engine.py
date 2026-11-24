"""Navigation Assist recommendation engine.

Pure Python with no openpilot imports, so the logic can be unit-tested anywhere.
navigation_assistd.py adapts cereal messages into NavSnapshot objects and turns
Advisory objects back into the navigationAssist message.

This module is advisory only. It never produces anything that reaches steering,
gas, brake, turn signals or lane-change logic.

Milestone 1: understand the route (active / inactive / stale / rerouted),
extract the next actionable maneuver, its side and distance, and decide how
prominently to show it.

Milestone 2: once a left/right maneuver is approaching, compare its side with
the lanes the camera model sees next to the car and say whether to move over
(PREPARE_LEFT / PREPARE_RIGHT), that the car is already on that side
(ALREADY_POSITIONED), or that a vehicle was detected on that side
(TRAFFIC_DETECTED). It never says a lane is clear: an empty blind spot only
means nothing was detected, so the driver is always told to check mirrors.
When lane data is missing it says so instead of guessing.
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
# Milestone 2 lane advice
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
URGENCY_TRAFFIC = 5  # vehicle detected on the side the driver needs to move to

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

# Milestone 2: lane position
MIN_ADJACENT_LANE_WIDTH = 2.5  # m; FrogPilot's lane width estimate reads 0 when no lane is beside the car
# Milestone 3 (2026-11-24, from Keith's real drives): the camera's "is there a lane beside me" flickers near exits
# (shoulders, an exit lane starting to open), and with a 1 s hold the advice flipped MOVE RIGHT <-> IN EXIT LANE about
# 10 times in the last 2 miles before Exit 653. So: a lane must be seen for longer before it counts, lane advice stays
# up for a minimum time, and near an exit a lane opening on that side is announced once as the exit lane opening.
LANE_APPEAR_HOLD = 3.0         # s a lane must be seen before it counts
LANE_VANISH_HOLD = 2.0         # s a lane must be gone before it stops counting
LANE_ADVICE_MIN_SHOW = 8.0     # s a piece of lane advice stays up before it can change (traffic warnings excepted)
EXIT_OPENING_DISTANCE = 800.0  # m (~1/2 mi) before an exit where a lane appearing on that side is the exit lane

# Spoken prompts (2026-11-24, off by default: NavigationAssistVoice). Short, calm phrases from
# frogpilot/assets/navigation_voice; soundd plays one only while no openpilot/FrogPilot alert is sounding. At most one
# "coming up" prompt per maneuver and one per new piece of lane advice; never anything about traffic.
VOICE_MIN_GAP = 6.0            # s between two prompts
VOICE_MIN_DISTANCE = 30.0      # m: closer than this to the maneuver nothing is said
VOICE_MIN_SECONDS = 4.0        # s: nor when the maneuver is less than this far away at the current speed
VOICE_AHEAD = {                # (kind, side) -> phrase when the maneuver starts approaching
  (KIND_EXIT, "right"): "exit_right_ahead", (KIND_EXIT, "left"): "exit_left_ahead",
  (KIND_TURN, "right"): "turn_right_ahead", (KIND_TURN, "left"): "turn_left_ahead",
  (KIND_FORK, "right"): "keep_right_ahead", (KIND_FORK, "left"): "keep_left_ahead",
  (KIND_ON_RAMP, "right"): "ramp_right_ahead", (KIND_ON_RAMP, "left"): "ramp_left_ahead",
}
VOICE_PHRASES = {"exit_right_ahead", "exit_left_ahead", "turn_right_ahead", "turn_left_ahead", "keep_right_ahead",
                 "keep_left_ahead", "ramp_right_ahead", "ramp_left_ahead", "move_right_exit", "move_left_exit",
                 "move_right_turn", "move_left_turn", "exit_lane_opening_right", "exit_lane_opening_left", "stay_in_lane",
                 "any_lane"}
RADAR_ALONGSIDE_DISTANCE = 15.0  # m; adjacent-lane radar target this close counts as alongside
LANE_ADVICE_KINDS = {KIND_EXIT, KIND_FORK, KIND_TURN, KIND_ON_RAMP}

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
  lanes_active: list[bool] = field(default_factory=list)  # Mapbox lane guidance, left to right; True = usable for the maneuver


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
  # Milestone 2 (all optional; None = unknown)
  lane_info_valid: bool = False       # camera lane estimate is meaningful right now
  lane_info_expected: bool = False    # lane estimate would normally exist (above FrogPilot's lane change speed)
  lane_width_left: float = 0.0        # m, frogpilotPlan.laneWidthLeft (0 = no lane to the left)
  lane_width_right: float = 0.0       # m, frogpilotPlan.laneWidthRight
  blindspot_available: bool = False   # the car reports blind spot monitoring (CarParams.enableBsm)
  blindspot_left: bool = False
  blindspot_right: bool = False
  radar_left_alongside: bool = False  # radar target in the left lane within RADAR_ALONGSIDE_DISTANCE
  radar_right_alongside: bool = False
  voice_enabled: bool = False         # NavigationAssistVoice param: spoken prompts


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
  voice_prompt: str = ""              # phrase id of the newest spoken prompt ("" = none yet)
  voice_prompt_count: int = 0         # goes up by one for every new prompt; soundd plays a prompt when it changes
  lane_info_available: bool = False
  blindspot_available: bool = False
  adjacent_lane_left: bool = False
  adjacent_lane_right: bool = False
  mapbox_lane_count: int = 0
  mapbox_active_lanes: int = 0


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

    # debounced camera lane estimate: side -> (current bool, candidate bool, candidate since)
    self.lane_seen = {"left": [None, None, 0.0], "right": [None, None, 0.0]}
    # the maneuver for which "EXIT LANE OPENING" was announced (kept until that maneuver is passed)
    self.exit_opening_for: tuple | None = None
    self.lane_shown: tuple = (None, URGENCY_APPROACHING, "", "")   # the lane advice currently on screen
    self.maneuver_key: tuple | None = None   # the maneuver being shown, identified by where it is on the route
    if not hasattr(self, "voice_count"):
      self.voice_count = 0                   # keeps counting across resets so soundd never misses a new prompt
      self.voice_phrase = ""
    self.voice_spoken: set = set()           # (maneuver key, phrase) already said
    self.voice_pending: str | None = None
    self.voice_last_at = -1e9
    self.voice_odometer = 0.0                # m driven, to tell a re-announced maneuver from the next one
    self.voice_odometer_at: float | None = None
    self.voice_said_for: dict = {}           # phrase -> (odometer, maneuver distance) when it was last said

  # ---- helpers ----------------------------------------------------------

  def _set_state(self, state: str, now: float, urgent: bool = False, dwell: float = MIN_STATE_DWELL) -> str:
    if state == self.state:
      return self.state
    if not urgent and (now - self.state_since) < dwell:
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

  def _debounced_lane(self, side: str, exists: bool, now: float) -> bool | None:
    """Only report a change in 'is there a lane on this side' after it held (LANE_APPEAR_HOLD / LANE_VANISH_HOLD)."""
    current, candidate, since = self.lane_seen[side]
    if current is None:
      self.lane_seen[side] = [exists, exists, now]
      return exists
    if exists == current:
      self.lane_seen[side][1] = exists
      return current
    if candidate != exists:
      self.lane_seen[side] = [current, exists, now]
      return current
    if now - since >= (LANE_APPEAR_HOLD if exists else LANE_VANISH_HOLD):
      self.lane_seen[side] = [exists, exists, now]
      return exists
    return current

  @staticmethod
  def _mapbox_lane_text(nav: NavSnapshot, side: str) -> str:
    lanes = nav.lanes_active
    active = [i for i, a in enumerate(lanes) if a]
    if not lanes or not active or len(active) == len(lanes):
      return ""
    n = len(active)
    if side == "right" and active == list(range(len(lanes) - n, len(lanes))):
      return f"right {n} lanes" if n > 1 else "right lane"
    if side == "left" and active == list(range(n)):
      return f"left {n} lanes" if n > 1 else "left lane"
    return f"{n} of {len(lanes)} lanes"

  def _lane_advice(self, inputs: EngineInputs, nav: NavSnapshot, kind: str, direction: str, out: Advisory,
                   detail: str, distance: float = 0.0, maneuver_key: tuple | None = None) -> tuple[str, int, str, str] | None:
    """Milestone 2: return (state, urgency, headline, detail) or None for no lane advice."""
    side = "left" if direction in LEFT_DIRECTIONS else "right" if direction in RIGHT_DIRECTIONS else None
    if side is None or kind not in LANE_ADVICE_KINDS:
      return None

    word = side.upper()
    lanes_text = self._mapbox_lane_text(nav, side)
    base = detail or ""

    def join(*parts):
      return " · ".join(p for p in parts if p)

    # Mapbox says every lane can take this maneuver: there is nothing to move for.
    if nav.lanes_active and all(nav.lanes_active) and len(nav.lanes_active) > 1:
      return ALREADY_POSITIONED, URGENCY_APPROACHING, "ANY LANE", join(base, "every lane can take it")

    if not inputs.lane_info_valid:
      # Only worth saying when lane data would normally exist; at city speeds FrogPilot doesn't estimate lanes.
      return None, None, None, join(base, "lane position unknown") if inputs.lane_info_expected else base

    width = inputs.lane_width_left if side == "left" else inputs.lane_width_right
    lane_on_side = self._debounced_lane(side, width >= MIN_ADJACENT_LANE_WIDTH, inputs.now)
    other = "right" if side == "left" else "left"
    other_width = inputs.lane_width_right if side == "left" else inputs.lane_width_left
    lane_on_other = self._debounced_lane(other, other_width >= MIN_ADJACENT_LANE_WIDTH, inputs.now)

    # Mapbox first: on a two-lane road, the lane on the *other* side tells which lane the car is in, which the camera's
    # view of the exit side can't (near exits a shoulder often measures as wide as a lane: 2.2-3.2 m on Keith's drives).
    lanes = nav.lanes_active
    if len(lanes) == 2 and lane_on_other is not None:
      target = lanes[-1] if side == "right" else lanes[0]     # is the lane on the maneuver side the one to use?
      if target and not all(lanes):
        lane_on_side = not lane_on_other                     # a lane on the other side: already in the exit-side lane
    out.adjacent_lane_left = bool(self.lane_seen["left"][0]) if self.lane_seen["left"][0] is not None else inputs.lane_width_left >= MIN_ADJACENT_LANE_WIDTH
    out.adjacent_lane_right = bool(self.lane_seen["right"][0]) if self.lane_seen["right"][0] is not None else inputs.lane_width_right >= MIN_ADJACENT_LANE_WIDTH

    # Near an exit, once the driver was in the outside lane, a lane appearing on that side is the exit lane opening:
    # say so once and keep it (no bouncing back to "in exit lane" when the camera loses it for a moment).
    near_exit = kind == KIND_EXIT and distance <= EXIT_OPENING_DISTANCE
    if self.exit_opening_for is not None and self.exit_opening_for != maneuver_key:
      self.exit_opening_for = None
    if near_exit and (self.exit_opening_for == maneuver_key or (lane_on_side and self.state == ALREADY_POSITIONED)):
      self.exit_opening_for = maneuver_key
      blindspot = inputs.blindspot_left if side == "left" else inputs.blindspot_right
      radar = inputs.radar_left_alongside if side == "left" else inputs.radar_right_alongside
      if lane_on_side and (blindspot or radar):
        return TRAFFIC_DETECTED, URGENCY_TRAFFIC, f"VEHICLE ON {word}", join("wait", base)
      return (PREPARE_LEFT if side == "left" else PREPARE_RIGHT), URGENCY_IMMINENT, "EXIT LANE OPENING", \
        join(base, f"move {side} when clear")

    if not lane_on_side:
      positioned = "IN EXIT LANE" if kind == KIND_EXIT else f"IN {word} LANE"
      if lanes_text and "lanes" in lanes_text and not lanes_text.startswith(side):
        positioned = f"IN {word} LANE"
      return ALREADY_POSITIONED, URGENCY_APPROACHING, positioned, join(base, "stay in lane")

    blindspot = inputs.blindspot_left if side == "left" else inputs.blindspot_right
    radar = inputs.radar_left_alongside if side == "left" else inputs.radar_right_alongside
    if blindspot or radar:
      return TRAFFIC_DETECTED, URGENCY_TRAFFIC, f"VEHICLE ON {word}", join("wait", base)

    mirrors = "check mirrors" if inputs.blindspot_available else "no blind spot data, check mirrors"
    headline = f"MOVE {word}"
    return (PREPARE_LEFT if side == "left" else PREPARE_RIGHT), \
      (URGENCY_IMMINENT if self.band >= 2 else URGENCY_APPROACHING), headline, join(lanes_text and f"use {lanes_text}", base, mirrors)

  # ---- spoken prompts ----------------------------------------------------

  def _voice_for(self, out: Advisory) -> str | None:
    """The phrase this advisory calls for, or None."""
    side = "left" if out.direction in LEFT_DIRECTIONS else "right" if out.direction in RIGHT_DIRECTIONS else None
    if side is None:
      return None
    if out.state in (PREPARE_LEFT, PREPARE_RIGHT):
      if out.headline == "EXIT LANE OPENING":
        return f"exit_lane_opening_{side}"
      return f"move_{side}_{'turn' if out.kind == KIND_TURN else 'exit'}"
    if out.state == ALREADY_POSITIONED:
      return "any_lane" if out.headline == "ANY LANE" else "stay_in_lane"
    if out.state in (MANEUVER_APPROACHING, MANEUVER_IMMINENT):
      return VOICE_AHEAD.get((out.kind, side))
    return None

  def _voice(self, inputs: EngineInputs, out: Advisory) -> None:
    out.voice_prompt, out.voice_prompt_count = self.voice_phrase, self.voice_count
    if self.voice_odometer_at is not None:
      self.voice_odometer += max(inputs.v_ego, 0.0) * min(max(inputs.now - self.voice_odometer_at, 0.0), 1.0)
    self.voice_odometer_at = inputs.now
    if not inputs.voice_enabled or not out.display_visible or self.maneuver_key is None:
      self.voice_pending = None
      return
    if out.maneuver_distance < max(VOICE_MIN_DISTANCE, inputs.v_ego * VOICE_MIN_SECONDS):
      self.voice_pending = None            # too close to the maneuver: a prompt now would only distract
      return
    for phrase, (odometer, distance) in self.voice_said_for.items():
      if self.voice_odometer - odometer < distance - VOICE_MIN_DISTANCE:
        # the maneuver this phrase was said for is still ahead: a route update renamed it, don't repeat it
        self.voice_spoken.add((self.maneuver_key, phrase))
    wanted = self._voice_for(out)
    if out.state == TRAFFIC_DETECTED:
      self.voice_pending = None            # never say "move" (or anything about lanes) while a car is alongside
    ahead = VOICE_AHEAD.get((out.kind, "left" if out.direction in LEFT_DIRECTIONS else "right"))
    if ahead and (self.maneuver_key, ahead) not in self.voice_spoken and out.state in (
        MANEUVER_APPROACHING, MANEUVER_IMMINENT, PREPARE_LEFT, PREPARE_RIGHT, ALREADY_POSITIONED, TRAFFIC_DETECTED):
      # announce the maneuver itself first, then the lane advice once the gap has passed
      self.voice_pending = wanted if wanted != ahead else None
      wanted = ahead
    elif wanted is None or (self.maneuver_key, wanted) in self.voice_spoken:
      wanted = self.voice_pending
    if out.state == TRAFFIC_DETECTED and wanted != ahead:
      wanted = None
    if wanted is None or wanted not in VOICE_PHRASES or inputs.now - self.voice_last_at < VOICE_MIN_GAP:
      if wanted is not None and wanted != self.voice_pending and (self.maneuver_key, wanted) not in self.voice_spoken:
        self.voice_pending = wanted
      return
    self.voice_spoken.add((self.maneuver_key, wanted))
    self.voice_said_for[wanted] = (self.voice_odometer, out.maneuver_distance)
    if self.voice_pending == wanted:
      self.voice_pending = None
    self.voice_last_at = inputs.now
    self.voice_count += 1
    self.voice_phrase = wanted
    out.voice_prompt, out.voice_prompt_count = self.voice_phrase, self.voice_count

  # ---- main entry -------------------------------------------------------

  def update(self, inputs: EngineInputs) -> Advisory:
    out = self._update(inputs)
    self._voice(inputs, out)
    return out

  def _update(self, inputs: EngineInputs) -> Advisory:
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
    self.maneuver_key = (kind, direction, round((nav.distance_remaining - maneuver.distance) / 200.0))
    out.lane_info_available = inputs.lane_info_valid
    out.blindspot_available = inputs.blindspot_available
    if is_current:
      out.mapbox_lane_count = len(nav.lanes_active)
      out.mapbox_active_lanes = sum(nav.lanes_active)

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

    out.display_visible = True

    # Milestone 2: lane advice once the maneuver is approaching
    if self.band >= 1:
      advice = self._lane_advice(inputs, nav, kind, direction, out, out.detail, distance,
                                 (kind, direction, round((nav.distance_remaining - maneuver.distance) / 200.0)))   # where it is on the route
      if advice is not None:
        lane_state, lane_urgency, lane_headline, lane_detail = advice
        out.detail = lane_detail
        if lane_state is not None:
          # Traffic warnings appear at once; everything else among lane states also switches at once
          # (the lane estimate is already debounced), except leaving a traffic warning, which waits.
          # Traffic warnings appear at once; a first piece of lane advice appears at once; after that, lane advice
          # changes only once the current one has been up for LANE_ADVICE_MIN_SHOW (no flip-flopping).
          lane_states = (PREPARE_LEFT, PREPARE_RIGHT, ALREADY_POSITIONED, TRAFFIC_DETECTED)
          if lane_state == TRAFFIC_DETECTED:
            urgent, dwell = True, MIN_STATE_DWELL
          elif self.state == TRAFFIC_DETECTED:
            urgent, dwell = False, MIN_STATE_DWELL
          elif self.state in lane_states:
            urgent, dwell = False, LANE_ADVICE_MIN_SHOW
          else:
            urgent, dwell = True, MIN_STATE_DWELL
          out.state = self._set_state(lane_state, now, urgent=urgent, dwell=dwell)
          if out.state == lane_state:
            out.urgency = lane_urgency
            out.headline = lane_headline
            self.lane_shown = (lane_state, lane_urgency, lane_headline, lane_detail)
            return out
          if out.state in lane_states:
            # still holding the previous lane advice during its minimum show time: keep showing *that* advice
            out.urgency = URGENCY_TRAFFIC if out.state == TRAFFIC_DETECTED else self.lane_shown[1]
            out.headline = self.lane_shown[2]
            out.detail = self.lane_shown[3]
            return out

    # Moving toward more urgency is immediate; relaxing waits for the dwell time.
    rank = {NAVIGATION_ACTIVE: 0, MANEUVER_APPROACHING: 1, MANEUVER_IMMINENT: 2}
    urgent = rank.get(state, 0) > rank.get(self.state, -1) or self.state not in rank
    out.state = self._set_state(state, now, urgent=urgent)
    out.urgency = {NAVIGATION_ACTIVE: URGENCY_INFO, MANEUVER_APPROACHING: URGENCY_APPROACHING,
                   MANEUVER_IMMINENT: URGENCY_IMMINENT}.get(out.state, urgency)
    return out
