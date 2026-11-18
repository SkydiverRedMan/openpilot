# Navigation Assist: architecture

Navigation Assist shows the next maneuver of the active navigation route, with its side and distance, on the onroad
driving screen. It is **advisory only**: it never steers, changes lanes, signals, or changes speed.

## Branches

| Branch | What it is |
|---|---|
| `na2-src` | Source branch. FrogPilot's *October 31st, 2026 Update* source (`8d705650`) + Keith's customizations + Navigation Assist. All development happens here. |
| `na2` | Prebuilt install branch the comma tracks. Produced from `na2-src` by `tools/na2/build_on_device.sh`. Never edit by hand. |
| `na2bk` | Untouched copy of `na2` at `840d0951` (before Navigation Assist). Rollback target. Tag `na2-baseline-2026-11-16` points at the same commit. |

`na2` before this work was FrogPilot's prebuilt `Compile FrogPilot` commit (`a22c4767`) of source `8d705650`, plus two
customization commits. Every source file on `na2-src` is byte-identical to `na2`; only compiled outputs differ.

## What already existed (reused, not duplicated)

| Need | Existing source | Notes |
|---|---|---|
| Destination | `NavDestination` param (set by The Pond / navigation UI) | Cleared on offroad transition |
| Route + next maneuver | `navd` → `navInstruction` (1 Hz) | `maneuverDistance`, `maneuverType`, `maneuverModifier`, `maneuverPrimaryText`, `allManeuvers` (every step, past ones negative), `distanceRemaining`, `lanes`; `valid=False` with no route |
| Position quality | `navd` → `frogpilotNavigation.valid` | False when the localizer is invalid or the car is off route |
| Speed | `carState.vEgo` | |
| Lane-level guidance | `navInstruction.lanes` (Mapbox lane components) | Only near a maneuver and only where Mapbox has lane data; reserved for Milestone 2 |
| Lane geometry / adjacent lanes | `modelV2` lane lines, `frogpilotPlan.laneWidthLeft/Right` | Milestone 2 |
| Adjacent vehicles | `radarState`, `liveTracks`, `carState.leftBlindspot/rightBlindspot` (Highlander BSM enabled on this fork) | Milestone 2; never treated as proof a lane is clear |
| Settings storage | `common/params.cc` key list (compiled), `frogpilot_default_params`, FrogPilot toggles JSON (`FrogPilotToggles`) | |

Nothing in navd, the driving model, planners, controls, lane-change logic (`desire_helper`), or Conditional
Experimental Mode was changed.

## New pieces

```
NavDestination ─┐
navd ── navInstruction ───────┐
navd ── frogpilotNavigation ──┤
card ── carState ─────────────┼──► navigation_assistd ── navigationAssist ──► UI (onroad banner)
NavigationAssist param ───────┘        (5 Hz, isolated process)
```

| Piece | File |
|---|---|
| Engine (pure Python, no openpilot imports) | `frogpilot/navigation_assist/engine.py` |
| Process (cereal adapter, param polling, synthetic mode) | `frogpilot/navigation_assist/navigation_assistd.py` |
| Synthetic scenarios + bench CLI | `frogpilot/navigation_assist/synthetic.py` |
| Message schema | `cereal/custom.capnp` (`NavigationAssist`), `cereal/log.capnp` (`Event.navigationAssist @136`), `cereal/services.py` (5 Hz, logged every 5th) |
| Params | `common/params.cc`: `NavigationAssist` (persistent, default off), `NavigationAssistSynthetic` (memory, cleared at start) |
| Toggle | `frogpilot/common/frogpilot_variables.py`: default `("NavigationAssist", "0", 0, "0")`, `toggle.navigation_assist` |
| Process registration | `system/manager/process_config.py`: runs only when onroad **and** the toggle is on |
| Isolation | `selfdrive/controls/controlsd.py`: `navigation_assistd` added to `IGNORE_PROCESSES` so its absence or crash can never raise *processNotRunning* or block engagement |
| Settings switch | `frogpilot/ui/qt/offroad/navigation_settings.cc` (FrogPilot → Navigation → Navigation Assist) |
| Onroad banner | `frogpilot/ui/qt/onroad/frogpilot_annotated_camera.cc` (`paintNavigationAssist`), subscription in `frogpilot/ui/frogpilot_ui.cc` |

### Why a separate process

* A bug or crash in Navigation Assist cannot affect `frogpilot_process`, planners or controls.
* It publishes exactly one service, `navigationAssist`, which only the UI reads. A test fails if any controls, car, or
  model code ever references it.
* Synthetic test data enters only inside this process; `navInstruction` (which the navigation driving models read) is
  never faked.

### Why the build has to be a full release

`na2` is prebuilt (`prebuilt` marker, compiled `selfdrive/ui/ui`, `params_pyx.so`, generated cereal code). The new
param key is compiled into `params_pyx.so` and the UI, and the new schema into the UI. A Python-only change would crash
on the unknown key (this happened before with `NavigationAssistedDecisions`), and replacing just the UI binary caused
instability before. So `na2` is rebuilt as one complete, internally consistent release from one source commit. See
`DEPLOYMENT.md`.

## Milestones

1. **Navigation awareness (this version).** Active/inactive, next actionable maneuver, side, distance (dead-reckoned
   between 1 Hz navd updates), route-change detection, stale handling, confidence gate, master switch, onroad banner,
   synthetic bench mode.
2. **Lane recommendations (implemented 2026-11-16, not yet driven).** Once a left/right exit, fork, turn or on-ramp
   is approaching: if the camera model sees a lane on that side (`frogpilotPlan.laneWidthLeft/Right` ≥ 2.5 m with
   both ego lane lines ≥ 0.5 confidence, above FrogPilot's lane change speed), show **MOVE RIGHT/LEFT** ("check
   mirrors"); if there is no lane on that side, **IN EXIT LANE / IN RIGHT LANE**; if `carState` blind spot or an
   adjacent-lane radar target within 15 m is on that side, red **VEHICLE ON RIGHT** ("wait"). Mapbox lane guidance,
   when present, adds "use right 2 lanes". The lane estimate must hold for 1 s before the advice changes; leaving a
   traffic warning waits 1.5 s. It never says a lane is clear. Without lane data above lane change speed it shows the
   maneuver with "lane position unknown". Limits: the camera only knows whether *a* lane exists beside the car, not
   how many; BSM on this Highlander is unverified (see KNOWN-LIMITATIONS.md).
3. **Timing.** Tune the time-based thresholds for 85-90 mph, progressive prompts, optional sound (off by default),
   and an event log reviewed after drives (`navigationAssist` is already logged at 1 Hz in rlogs).
4. **Navigation-guided steering (future; not advisory).** openpilot should *know* the route's next maneuver and lean
   the driving toward it, with the driver still doing what the car can't (for example most of a full right turn at an
   intersection). This deliberately changes the "advisory only" rule, so it is its own milestone, built only after
   Milestones 1-3 have proven accurate on real drives. Approach:
   * Steer **through the driving model**, never by commanding angles: give the model navigation-derived *desires*
     (keep left/right, lane change left/right, turn left/right), the inputs it already understands. FrogPilot already
     sends turn desires with the blinker at low speed; this fork also keeps comma's navigation-aware models
     (`navmodeld`), which take the route as input; try those on real routes first.
   * Steps, in order of payoff and risk: (1) navigation-driven speed (slow for exits, ramps and turns; FrogPilot's
     Conditional Experimental Mode and curve speed control already partly do this); (2) driver-confirmed lane changes
     toward the exit (Navigation Assist says move right, the driver taps the signal, openpilot's existing lane change
     with its blind-spot check does it); (3) keep-left/keep-right desires at confirmed forks and exits; (4) turn assist
     at intersections when the blinker and the route agree, limited by Toyota's steering torque and openpilot's limits.
   * Guardrails: separate on/off switch; every maneuver starts with a driver action (signal, button or tap), never
     the accelerator alone; any driver steering cancels it; only with fresh, confident route data; panda safety
     limits and driver monitoring unchanged.
