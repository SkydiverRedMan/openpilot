# Saved speed limits

Keith's fix for wrong or missing speed limits: tell the comma the real limit once, and it uses it on that road from
then on, ahead of the camera, map, navigation and every priority setting.

## Using it

* **While driving:** tap the speed limit sign on the driving screen. A panel opens next to it with seven limits
  (the one shown, and 5, 10 and 15 mph either side; 10 km/h steps in metric). Tap the real one. You'll see
  "Speed limit saved: 45 mph" with a chime. If the road already has a saved limit, the eighth button is **Clear**;
  otherwise it's **Cancel**. The panel closes after 8 seconds or on any other tap.
* **Why not "save my cruise speed":** Keith's speed limit offsets (+5 up to 44 mph, +8 to 64, +11 above) mean the
  set speed is never the actual limit.
* **Afterwards, from a phone:** The Pond → Settings → **Saved Speed Limits** lists every saved road, with Change and
  Remove, plus **Download backup** and **Restore from backup**. The Pond is locked while driving.
* The speed limit sources panel shows a **Saved** row in place of **Map Data** when a saved limit applies.

## How it works

* A saved limit belongs to one map road segment (OSM way) in one direction, the same key FrogPilot's learned limits
  use. Long roads are split into several segments in the map, so a road may need saving in a few places, and each
  direction separately. Saving needs a GPS fix and downloaded offline maps for the area; otherwise the alert says
  "Couldn't save the speed limit".
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
| Sign tap and picker | `selfdrive/ui/qt/onroad/onroad_home.cc`, `frogpilot/ui/qt/onroad/frogpilot_annotated_camera.cc` |
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
| 2026-11-18 | Unit tests on Windows (Python 3.12, pycapnp 2.0.0) | 34 passed. Navigation Assist tests still 115 passed, 1 skipped |
| 2026-11-18 | C++ / Qt | **Not compiled yet**: needs the on-device build |
