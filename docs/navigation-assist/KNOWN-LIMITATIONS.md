# Navigation Assist: known limitations

## Milestone 1 scope

* Shows the next maneuver, side and distance only. It does **not** say which lane to be in, whether you are already in
  the right lane, or anything about traffic. Those are Milestone 2.
* No sound. An optional sound (off by default) is planned for Milestone 3.
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
