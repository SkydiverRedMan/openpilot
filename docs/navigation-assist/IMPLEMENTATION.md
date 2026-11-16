# Navigation Assist: implementation

## Turning it on and off

FrogPilot settings → **Navigation** → **Navigation Assist**. Default **off**.

* Stored in the persistent `NavigationAssist` param, so it survives reboots and updates.
* Flipping the switch asks FrogPilot to refresh its toggles, which starts or stops `navigation_assistd` (it only runs
  while onroad with the switch on).
* `navigation_assistd` also re-reads the param every 0.5 s, so turning it off hides the banner within half a second
  even while driving, and the UI hides the banner as soon as the toggle is off or the message stops arriving.
* Off has no effect on openpilot, navigation, lane changes, or Conditional Experimental Mode: none of them read
  Navigation Assist's param or message.

## Data flow per cycle (5 Hz)

1. `navigation_assistd` reads `navInstruction` (when updated), `frogpilotNavigation.valid`, `carState.vEgo`, and
   (every 0.5 s) the `NavigationAssist`, `NavDestination`, `IsMetric` params.
2. It converts `navInstruction` into a `NavSnapshot` and calls `NavigationAssistEngine.update()`.
3. It publishes the resulting `Advisory` as `navigationAssist`.
4. The UI draws the banner when `enabled && displayVisible && urgency > 0`, the toggle is on, and the message is alive
   (received within ~2 s).

## Engine (`engine.py`)

**Next actionable maneuver.** `allManeuvers` holds every step of the route (passed ones have negative distance). The
engine takes the nearest maneuver at ≥ −15 m that asks the driver to do something: turns, exits (`off ramp`), forks,
merges, on-ramps, roundabouts, U-turns, arrival, and `continue` steps that bend (`slight left/right`). `new name`,
`continue straight` and `notification` steps are skipped, so "EXIT RIGHT 3.1 MI" is shown even when two "continue on
I-90" steps come first. The banner's detail line (`maneuverPrimaryText`, e.g. "Exit 45: NY-12 North") is only shown when
it belongs to that same maneuver.

**Direction.** Mapbox modifier → `left/right/slightLeft/slightRight/sharpLeft/sharpRight/straight/uturn`. The
headline says only what navigation says (e.g. "EXIT RIGHT", "KEEP LEFT"); it never claims a specific lane.

**Distance.** navd publishes at 1 Hz; between updates the engine subtracts `vEgo × elapsed` so the number counts down
smoothly. Formatting follows `IsMetric`: `1.8 MI` / `12 MI` / `500 FT`, or `2.5 KM` / `450 M`.

**Prominence (speed aware).**

| State | Entered when | Banner |
|---|---|---|
| `navigationActive` | route active, maneuver further out | white outline |
| `maneuverApproaching` | ≤ 3.2 km **or** ≤ 100 s away | green outline, green distance |
| `maneuverImminent` | ≤ 400 m **or** ≤ 15 s away | orange outline, orange distance |

Using time as well as distance gives earlier prompts at highway speed (at 88 mph "approaching" starts ~3.9 km out).
Hysteresis: a band is left only after moving 15 % back out of it. Increases in urgency show immediately; decreases
wait 1.5 s in the current state.

**Route changes.** The route identity is the sequence of (type, modifier) in `allManeuvers`, which stays fixed while
driving along a route. A different sequence, or `distanceRemaining` jumping up by more than max(300 m, 10 %), counts
as a reroute: `routeChanged` is true for 4 s, `routeChangeCount` increments, and filters reset.

**Stale / missing data.**

| Situation | State | Banner |
|---|---|---|
| No destination | `navigationInactive` | hidden |
| Destination set, no route yet (first 15 s) | `routeUnavailable` | hidden |
| Destination set, no fresh route after that, or no navInstruction for 4 s | `routeUnavailable` | grey "NAV DATA UNAVAILABLE" |
| No actionable maneuver left | `noUpcomingManeuver` | hidden |
| Confidence below 0.6 | `insufficientInformation` | grey "NAV POSITION UNCERTAIN", no distance |

**Confidence** = freshness × completeness × position × consistency:

* freshness: 1.0 up to 1.5 s since the last navInstruction, falling to 0 at 4 s;
* completeness: lower when the maneuver type or direction is missing;
* position: 0.3 when `frogpilotNavigation.valid` is false (localizer invalid or off route);
* consistency: compares each navd distance drop with odometry; repeated disagreement (GPS jumps) lowers it.

Showing again after low confidence needs 0.7 (hysteresis).

## Message (`cereal/custom.capnp` `NavigationAssist`)

`enabled, state, maneuverKind, direction, maneuverDistance (m), timeToManeuver (s), confidence, displayVisible,
urgency (0 hidden, 1 info, 2 approaching, 3 imminent, 4 data warning), headline, distanceText, detail, routeChanged,
routeChangeCount, navigationAge (s), synthetic`.

Text is formatted in Python so the UI only draws, and so formatting is unit-tested.

## UI

`paintNavigationAssist()` draws a compact banner (620 × 120-160 px) at the top right, under the Experimental Mode
button and below the screen recorder / instant replay buttons. That area holds nothing else; the set speed, current
speed, speed limit, lead and lane drawing, alerts (bottom), and driver monitoring icon (bottom left) are untouched. It
moves down if a static turn-signal image would overlap it, and it is not drawn when the big map covers the camera.
Arrows are drawn with QPainter paths (no new image assets). There is no animation. Synthetic data shows a purple
**TEST DATA** tag.

## Adding a recommendation type (Milestone 2 onward)

1. Add the state to `NavigationAssist.State` in `cereal/custom.capnp` (append only, never renumber).
2. Add the matching constant to `engine.py` (the integration test checks the names match the schema).
3. Produce it in `NavigationAssistEngine.update()`, with headline/detail text and an urgency.
4. If it needs new inputs (e.g. `modelV2`, `radarState`, `carState.leftBlindspot`), subscribe to them in
   `navigation_assistd.main()` and pass them through `EngineInputs`. Read only; never publish.
5. Add engine tests and a synthetic scenario; the UI needs no change unless it needs a new icon.
6. Rebuild and publish with `tools/na2/build_on_device.sh` (schema changes need the full build).

Rules that must stay true: never publish anything but `navigationAssist`; never subscribe controls/planner code to
it; never infer a lane is clear from an absence of detections.
