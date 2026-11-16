# Navigation Assist: testing

Never use a moving car as the first test. Order: unit tests → PC build and UI render → bench test on the parked
comma with synthetic data → a real route while parked → a drive.

## 1. Unit and integration tests (any PC)

Tests live in `frogpilot/navigation_assist/tests/` (excluded from the prebuilt release by `prepare_release.py`).

| File | Covers |
|---|---|
| `test_engine.py` | maneuver classification and headlines, distance formatting (imperial/metric), master switch off/on, active/inactive transitions, destination without route, stale data, left/right exits, dead-reckoned distance, skipping non-actionable steps, speed-aware approach timing, hysteresis and dwell, route changes vs. step advances, confidence (position invalid, GPS jumps, recovery margin), Milestone 2 states never emitted |
| `test_navigation_assistd.py` | process behaviour with fake SubMaster/Params: publishes only `navigationAssist`, switch-off within 0.5 s, invalid position, stale navd, every synthetic scenario, synthetic stops when the car moves, restart reads the persisted switch |
| `test_synthetic.py` | full scenarios through the engine: highway exit right (88 mph) and left, fork, city turns, continue-then-exit, reroute, navd going silent |
| `test_integration.py` | engine names = schema enums, message fields = schema fields, Event/service registration, compiled param keys, default off, controlsd ignore list, no control/model code references the message, UI subscribes and gates on the toggle, real capnp round trip, manager runs the process only when onroad and enabled |

On a PC with Docker (Windows PowerShell or Git Bash):

```bash
docker run --rm -v "C:/Dev/Projects/PDev/FrogPilot:/src:ro" python:3.11-slim bash -c "pip install -q pytest pycapnp==2.0.0 && mkdir -p /work && ln -s /src /work/openpilot && cd /tmp && PYTHONPATH=/work python -m pytest -c /dev/null --noconftest -q /work/openpilot/frogpilot/navigation_assist/tests"
```

(In Git Bash prefix with `MSYS_NO_PATHCONV=1`.) Inside a full openpilot environment simply run
`pytest frogpilot/navigation_assist/tests`.

Result on 2026-11-16: 90 passed, 1 skipped (the manager test needs `cereal.messaging`; it runs in the PC build below).

## 2. PC build and UI render

`Dockerfile.openpilot_base` from this source builds the openpilot PC environment. A full `scons` build there checks
that the schema, params and Qt code compile together; the UI snapshot tool
(`selfdrive/ui/tests/test_ui/run.py`) renders the onroad screen offscreen. See the results section at the end of this
file for what was actually run.

## 3. Bench test on the comma (parked, synthetic data)

1. Install the build (see `DEPLOYMENT.md`), reboot, keep the car in park or off.
2. FrogPilot → Navigation → turn **Navigation Assist** on.
3. Make the UI go onroad without driving: FrogPilot developer settings → **Force Onroad** (or turn the car to ON
   without starting to drive).
4. SSH in and start a scenario:

   ```bash
   cd /data/openpilot
   python -m frogpilot.navigation_assist.synthetic --list
   python -m frogpilot.navigation_assist.synthetic highway_exit_right
   ```

5. The banner shows **EXIT RIGHT** with a counting-down distance and a purple **TEST DATA** tag, turning green
   (approaching) and orange (imminent). Try `highway_exit_left`, `highway_fork_left`, `city_turn_right`, `reroute`,
   `stale`.
6. Turn the switch off: the banner disappears within half a second.
7. Stop: `python -m frogpilot.navigation_assist.synthetic --stop`, then turn Force Onroad off.

Safety of the synthetic mode: it only feeds Navigation Assist's own engine (nothing publishes `navInstruction` or any
control message), it is cleared at every manager start, and it switches itself off the moment `carState` reports the
car moving faster than 0.5 m/s.

## 4. Real route, parked

Set a destination in The Pond (http://<comma-ip>:8082 → Navigation) with the car on in park. Expect the banner within
a few seconds (route calculation), showing the first maneuver. Clear the destination: banner disappears.

## 5. Drive

On a known route with a highway exit: check the banner appears early enough at 85-90 mph, that the distance matches
the map, that it hides in tunnels or when navigation stops, and that disabling it mid-drive changes nothing else.
`navigationAssist` is logged (1 Hz) in rlogs, so drives can be reviewed afterwards.

## Results log

| Date | What | Result |
|---|---|---|
| 2026-11-16 | Unit/integration tests (python:3.11 + pycapnp 2.0.0) | 90 passed, 1 skipped |
| 2026-11-16 | Full PC build of na2-src in `Dockerfile.openpilot_base` image (`scons -k`) | UI, params_pyx, cereal and all other targets compiled; only the two tinygrad model `.pkl` targets failed (need LLVM on PC; built differently on the comma) |
| 2026-11-16 | All Navigation Assist tests + `frogpilot/tests/test_process_config.py` in that build | 95 passed |
| 2026-11-16 | Offscreen UI render of the banner (Xvfb) | **Not completed**: render script hung before the first screenshot; UI process stayed up. Retry, or check on the comma with synthetic mode |
| 2026-11-16 | First release `d4bba4b5` on the comma | Built on the comma, published, installed via Update. Settings switch works and persists; `navigation_assistd` ran and published "EXIT RIGHT 2.5 MI" in the synthetic scenario. **Banner not drawn with the car off**: the UI only drew FrogPilot widgets after modelV2/uiPlan, which don't exist without a car. Fixed in the next build (banner drawn independently). |
| 2026-11-16 | Offscreen render (Xvfb, `--shm-size=2g`) | UI ran through all 10 cases without crashing, but screenshots were black (capture doesn't see the UI's OpenGL output). Not a valid visual check. |
| 2026-11-16 | Release `c241dabb` on the comma, car off, Force Onroad + `highway_exit_right` | **Banner visible on the comma screen** (confirmed by Keith); daemon publishing "EXIT RIGHT 2.9 MI". Milestone 1 bench-verified; real-drive check still to do. |
