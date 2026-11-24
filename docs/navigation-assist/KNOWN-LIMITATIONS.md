# Navigation Assist: known limitations

## Milestone 1 scope

* Milestone 2 lane advice only knows whether the camera sees *a* lane beside the car, not how many lanes there are or
  which exact lane the exit uses. "IN EXIT LANE" means "no lane to your right", which is usually but not always the
  exit lane (two-lane exits, lane drops). Mapbox lane guidance helps only where Mapbox has it.
* **The Highlander's blind spot state does not reach openpilot** (checked 2026-11-16 against all 22 stored drives,
  about 6 hours above 10 mph): `carState.leftBlindspot/rightBlindspot` were never true. The CAN message openpilot
  reads, 0x3F6 "BSM", is present on this TSS-P Highlander but is a static 1 Hz status frame (`80ca020000000000`
  every time: the "enabled" bits set, the adjacent/approaching bits always 0). On TSS2 Toyotas that message carries
  the live mirror-light state; on this car it doesn't. Consequences: openpilot's lane-change blind-spot check never
  blocks (what Keith observed), and Navigation Assist's traffic warning can only come from the front radar's
  adjacent-lane targets. Likely fix (separate project): poll the blind spot module over diagnostic CAN, as some
  community forks do for TSS-P Toyotas, which needs care with panda safety; verify first with a recorded drive.
* Spoken prompts are optional (off by default) and English only. They're short fixed phrases (no distances), and
  they never mention traffic: with no blind spot data, nothing may sound like "it's clear".
* The camera can't tell a wide shoulder from a lane. Mapbox lane guidance settles it only on two-lane roads; elsewhere
  the advice holds steady (3 s / 8 s) instead of flip-flopping, but can still be wrong near exits.
* Thresholds (3.2 km / 100 s approaching, 400 m / 15 s imminent) are first guesses. They need tuning from real drives
  at 85-90 mph.

## Data

* **Mapbox navigation is required.** Navigation Assist reads FrogPilot's existing navd route, which needs both Mapbox
  keys and a destination set from The Pond or the map. Without a route it stays hidden.
* navd publishes once per second and only while onroad. Distances in between are dead-reckoned from vehicle speed.
* "EXIT RIGHT" means the navigation maneuver is on the right. It is not a lane assignment: some exits leave from a
  lane that is not the rightmost, and lane drops and multi-lane exits are not modelled.
* Mapbox banner text (`maneuverPrimaryText`) can be generic ("I-90 East") or missing.
* A GPS jump that also changes the remaining route distance by more than 300 m is treated as a reroute (the banner
  shows the new data; only the reroute counter is affected).
* In tunnels or with poor GPS, navd marks the position invalid and the banner switches to "NAV POSITION UNCERTAIN".

## UI

* The banner sits top right under the Experimental Mode button. With the big map open (map covering the camera view)
  it is not drawn; the map's own instructions are shown instead.
* Verified by build and offscreen render tests where noted in `TESTING.md`; it has **not** been seen on the comma 3X
  screen until the first device install. Check placement on the first drive while parked (synthetic mode).

## Deployment

* Building needs the comma itself (AGNOS toolchain), parked, on Wi-Fi, with SSH from the PC. About 15-40 minutes,
  with openpilot stopped meanwhile.
* The PC needs an SSH key that the comma accepts (the comma trusts the keys on the `SkydiverRedMan` GitHub account).
  See `DEPLOYMENT.md`.
* After rolling back to a version without Navigation Assist, do not restore a FrogPilot settings backup made on the
  newer version: it contains the `NavigationAssist` key, which the older build does not know. Remove that key from the
  backup file first.
