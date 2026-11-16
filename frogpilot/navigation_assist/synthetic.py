#!/usr/bin/env python3
"""Synthetic navigation scenarios for Navigation Assist.

Scenarios produce NavSnapshot objects (what navd would publish as navInstruction)
for a car driving along a made-up route. They feed only the Navigation Assist
engine: nothing here publishes navInstruction, carState, carControl or any other
message that driving code reads.

Bench use on the device (car parked or off, openpilot running with Force Onroad):

  python -m frogpilot.navigation_assist.synthetic highway_exit_right
  python -m frogpilot.navigation_assist.synthetic --stop

navigation_assistd picks the scenario up from the NavigationAssistSynthetic memory
param and drops it the moment carState reports the car moving.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass

from openpilot.frogpilot.navigation_assist.engine import Maneuver, NavSnapshot

MPH = 0.44704


@dataclass
class Step:
  length: float          # metres from the previous maneuver to this one
  type: str
  modifier: str
  text: str = ""


@dataclass
class Scenario:
  name: str
  speed: float           # m/s the simulated car drives at
  steps: list[Step]
  description: str = ""
  stale_after: float | None = None   # seconds after which messages stop (navd died)
  reroute_at: float | None = None    # seconds after which the route changes
  reroute_steps: list[Step] | None = None

  def total(self, steps: list[Step] | None = None) -> float:
    return sum(s.length for s in (steps or self.steps))

  def snapshot(self, t: float) -> NavSnapshot | None:
    """Return what navd would publish t seconds into the scenario, or None if silent."""
    if self.stale_after is not None and t >= self.stale_after:
      return None

    steps = self.steps
    traveled = self.speed * t
    if self.reroute_at is not None and self.reroute_steps and t >= self.reroute_at:
      steps = self.reroute_steps
      traveled = self.speed * (t - self.reroute_at)

    total = sum(s.length for s in steps)
    traveled = min(traveled, total)

    maneuvers = []
    position = 0.0
    current = None
    for step in steps:
      position += step.length
      distance = position - traveled
      maneuvers.append(Maneuver(distance=distance, type=step.type, modifier=step.modifier))
      if current is None and distance > -5.0:
        current = (step, distance)
    if current is None:
      current = (steps[-1], maneuvers[-1].distance)

    step, distance = current
    return NavSnapshot(
      valid=True,
      maneuver_distance=distance,
      maneuver_type=step.type,
      maneuver_modifier=step.modifier,
      primary_text=step.text,
      distance_remaining=max(0.0, total - traveled),
      all_maneuvers=maneuvers,
    )


SCENARIOS: dict[str, Scenario] = {s.name: s for s in [
  Scenario("highway_exit_right", 88 * MPH, [
    Step(5000, "off ramp", "slight right", "Exit 45: NY-12 North"),
    Step(800, "turn", "right", "NY-12 N"),
    Step(1200, "arrive", "right", "Destination"),
  ], "Interstate at 88 mph, right-side exit ~3.1 mi ahead"),
  Scenario("highway_exit_left", 85 * MPH, [
    Step(4200, "off ramp", "slight left", "Exit 12A: I-81 South"),
    Step(2000, "merge", "slight right", "I-81 S"),
    Step(3000, "arrive", "left", "Destination"),
  ], "Left-side exit, then a merge"),
  Scenario("highway_fork_left", 75 * MPH, [
    Step(3500, "fork", "slight left", "I-90 West"),
    Step(6000, "off ramp", "slight right", "Exit 31"),
    Step(1000, "arrive", "straight", "Destination"),
  ], "Highway split, keep left"),
  Scenario("city_turn_right", 35 * MPH, [
    Step(600, "turn", "right", "Main St"),
    Step(400, "turn", "left", "Oak Ave"),
    Step(250, "arrive", "right", "Destination"),
  ], "City streets, close turns"),
  Scenario("continue_then_exit", 70 * MPH, [
    Step(2000, "new name", "straight", "I-90 E"),
    Step(2500, "continue", "straight", "I-90 E"),
    Step(1500, "off ramp", "slight right", "Exit 9"),
  ], "Non-actionable steps are skipped"),
  Scenario("reroute", 65 * MPH, [
    Step(4000, "off ramp", "slight right", "Exit 20"),
    Step(1000, "arrive", "right", "Destination"),
  ], "Route changes 20 s in", reroute_at=20.0, reroute_steps=[
    Step(6000, "off ramp", "slight left", "Exit 21"),
    Step(1500, "arrive", "left", "Destination"),
  ]),
  Scenario("stale", 65 * MPH, [
    Step(4000, "off ramp", "slight right", "Exit 20"),
  ], "navd stops publishing after 10 s", stale_after=10.0),
]}


def main(argv: list[str] | None = None) -> int:
  parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
  parser.add_argument("scenario", nargs="?", choices=sorted(SCENARIOS))
  parser.add_argument("--stop", action="store_true", help="end the running synthetic scenario")
  parser.add_argument("--list", action="store_true", help="list scenarios")
  args = parser.parse_args(argv)

  if args.list or (not args.scenario and not args.stop):
    for name, scenario in sorted(SCENARIOS.items()):
      print(f"{name:22s} {scenario.description}")
    return 0

  from openpilot.common.params import Params
  params_memory = Params("/dev/shm/params")
  if args.stop:
    params_memory.remove("NavigationAssistSynthetic")
    print("Synthetic navigation stopped")
  else:
    params_memory.put("NavigationAssistSynthetic", args.scenario)
    print(f"Synthetic scenario '{args.scenario}' started. Only Navigation Assist sees it; it stops if the car moves.")
  return 0


if __name__ == "__main__":
  sys.exit(main())
