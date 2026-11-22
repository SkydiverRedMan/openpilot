# Saved speed limits

Keith's fix for wrong or missing speed limits: tell the comma the real limit once, and it uses it on that road from
then on, ahead of the camera, map, navigation and every priority setting.

## Using it

* **While driving:** touch the speed limit sign on the driving screen. A panel opens next to it at once with seven limits
  (the one shown, and 5, 10 and 15 mph either side; 10 km/h steps in metric). Tap the real one. You'll see
  "Speed limit saved: 45 mph" with a chime. If the road already has a saved limit, the eighth button is **Clear**;
  otherwise it's **Cancel**. The panel closes after 8 seconds or on any other tap.
* **To save your cruise setting:** set cruise to exactly the posted limit with the wheel buttons, tap the sign, and tap
  the blue **MY CRUISE** button on the right of the panel (it shows your cruise number). Then set cruise back up (e.g.
  95). The blue button only appears when cruise is on and set to 85 mph (140 km/h) or less, so the usual 95 can't be
  saved as a limit. When the map is open and the camera view is narrow, the blue button sits in a row under the others.
  (Until 2026-11-19 this was "hold the sign 0.8 s"; on the road taps were often read as holds and saved the cruise
  setting by mistake, so touching the sign now always opens the panel, right away.)
* **Afterwards, from a phone:** The Pond → Settings → **Saved Speed Limits** lists every saved road, with Change and
  Remove, plus **Download backup** and **Restore from backup**. The Pond is locked while driving.
* The speed limit sources panel shows a **Saved** row in place of **Map Data** when a saved limit applies.

## How it works

* With offline maps for the area, a saved limit belongs to one map road segment (OSM way) in one direction, the same
  key FrogPilot's learned limits use. Long roads are split into several segments in the map, so a road may need saving
  in a few places, and each direction separately.
* **Without offline maps (added 2026-11-22):** the limit is pinned to the GPS spot and heading where it was saved
  ("GPS spot" in The Pond). It takes effect at once, and again whenever the car passes within 40 m of the spot heading
  the same way (within 35°). Like a posted sign it then stays on until the car passes another saved spot, turns more
  than 60° off that heading, or has gone 8 km (5 mi). A road-based saved limit wins over a spot where both apply.
  Saving at the same place and direction replaces the old spot. **Clear** removes the spot in effect.
  Found on the NY→TX trip: offline maps were only downloaded for NY/PA/NJ/MA/TX (+CA), so saving failed in Indiana.
* Saving now only fails with no GPS fix; the alert then says "Couldn't save the speed limit — No GPS fix right now".
* A saved limit on the next segment takes over early, using the same lookahead as map limits.
* Offsets still apply on top of a saved limit, and it needs no confirmation even with confirmation turned on.
* Files: `/data/saved_speed_limits.json` with a copy at `/data/media/0/saved_speed_limits_backup.json`. Both are outside
  `/data/openpilot`, so updates never remove them. FrogPilot's learned limits are in `/data/speed_limit_filler.json`,
  also outside the install. Saved limits are never uploaded.
* The backup file holds both saved and learned limits. Restoring replaces saved limits for the same road, only adds
  learned roads the device doesn't know, and needs a reboot before driving when it added learned roads.

## Code

| Piece | File |
|---|---|
| Store (file, lock, reload) | `frogpilot/controls/lib/saved_speed_limits.py` |
| Priority over other sources | `frogpilot/controls/lib/speed_limit_controller.py` (`update_saved_speed_limit`) |
| Save request from the screen | `frogpilot/controls/frogpilot_planner.py` (`handle_saved_speed_limit_request`) |
| Alerts | `selfdrive/controls/lib/events.py`, `frogpilot/controls/lib/frogpilot_events.py` |
| Schema | `cereal/custom.capnp`: `FrogPilotUIEvent.saveSpeedLimit`, `FrogPilotPlan.slcSavedSpeedLimit`, 3 events |
| Sign touch and picker | `selfdrive/ui/qt/onroad/onroad_home.cc`, `frogpilot/ui/qt/onroad/frogpilot_annotated_camera.cc` |
| The Pond | `frogpilot/system/the_pond/saved_speed_limits.py`, `assets/js/pages/speed_limits.js` |

The schema and Qt changes need a full rebuild on the comma (`tools/na2/build_on_device.sh`).

## Testing

```bash
pytest frogpilot/controls/lib/tests/test_saved_speed_limits.py
```

Without an openpilot environment, use a venv with `pytest numpy pycapnp==2.0.0 aiohttp` and a folder named
`openpilot` linking to the repo on `PYTHONPATH` (same idea as the Docker command in
`docs/navigation-assist/TESTING.md`).

| Date | What | Result |
|---|---|---|
| 2026-11-18 | Unit tests on Windows (Python 3.12, pycapnp 2.0.0) | 35 passed. Navigation Assist tests still 115 passed, 1 skipped |
| 2026-11-18 | C++ / Qt | Built on the comma (`na2` `beef7bfc`) and driven |
| 2026-11-19 | Drive log, route `00000028` | Three unintended 65 mph saves at 13:32 were holds (cruise 65); UI drew every frame in under 100 ms, so the hold timing itself misfired. Replaced by the blue MY CRUISE choice |
