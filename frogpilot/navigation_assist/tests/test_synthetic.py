"""Synthetic scenarios drive the engine end to end: highway exits, forks, turns, reroutes, stale data."""
import pytest

from openpilot.frogpilot.navigation_assist import engine as E
from openpilot.frogpilot.navigation_assist.engine import EngineInputs, NavigationAssistEngine
from openpilot.frogpilot.navigation_assist.synthetic import SCENARIOS


def play(name, seconds, dt=0.2):
  scenario = SCENARIOS[name]
  engine = NavigationAssistEngine()
  nav, nav_at, t0, results = None, None, 500.0, []
  for i in range(int(seconds / dt)):
    t = i * dt
    updated = False
    if i % int(1 / dt) == 0:
      snapshot = scenario.snapshot(t)
      if snapshot is not None:
        nav, nav_at, updated = snapshot, t0 + t, True
    out = engine.update(EngineInputs(now=t0 + t, enabled=True, destination_set=True, v_ego=scenario.speed,
                                     nav=nav, nav_received_at=nav_at, nav_updated=updated))
    results.append((t, out))
  return results


def states_in_order(results):
  order = []
  for _, out in results:
    if not order or order[-1] != out.state:
      order.append(out.state)
  return order


def test_highway_exit_right_full_approach():
  results = play("highway_exit_right", 130)
  order = states_in_order(results)
  assert order[:3] == [E.NAVIGATION_ACTIVE, E.MANEUVER_APPROACHING, E.MANEUVER_IMMINENT]
  first = results[2][1]
  assert first.headline == "EXIT RIGHT" and first.detail == "Exit 45: NY-12 North" and first.distance_text.endswith("MI")
  # distance strictly decreases while approaching the exit
  distances = [out.maneuver_distance for t, out in results if t < 120]
  assert all(b <= a + 1e-6 for a, b in zip(distances, distances[1:]))


def test_after_exit_next_maneuver_is_turn():
  results = play("highway_exit_right", 140)
  assert results[-1][1].headline == "TURN RIGHT"


def test_highway_exit_left():
  results = play("highway_exit_left", 5)
  assert results[-1][1].headline == "EXIT LEFT"
  assert results[-1][1].direction == E.DIR_SLIGHT_LEFT


def test_highway_fork():
  results = play("highway_fork_left", 5)
  assert results[-1][1].headline == "KEEP LEFT" and results[-1][1].kind == E.KIND_FORK


def test_city_turns_become_imminent_quickly():
  results = play("city_turn_right", 20)
  assert results[0][1].headline == "TURN RIGHT"
  assert E.MANEUVER_IMMINENT in states_in_order(results)


def test_continue_steps_skipped():
  results = play("continue_then_exit", 3)
  assert results[-1][1].headline == "EXIT RIGHT"
  assert results[-1][1].maneuver_distance == pytest.approx(6000 - 70 * 0.44704 * 2.8, abs=40)


def test_reroute_detected():
  results = play("reroute", 30)
  before = [out for t, out in results if t < 19]
  after = [out for t, out in results if t > 21]
  assert before[-1].headline == "EXIT RIGHT" and before[-1].route_change_count == 0
  assert after[0].route_changed and after[-1].route_change_count == 1
  assert after[-1].headline == "EXIT LEFT"


def test_stale_scenario_reports_unavailable():
  results = play("stale", 20)
  assert results[-1][1].state == E.ROUTE_UNAVAILABLE
  assert not any(out.state == E.ROUTE_UNAVAILABLE for t, out in results if t < 10)
