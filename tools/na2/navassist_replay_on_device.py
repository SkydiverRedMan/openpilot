#!/usr/bin/env python3
"""Replay real drives through two Navigation Assist engines (runs ON THE COMMA; changes nothing).

Feeds the logged inputs (navInstruction, frogpilotNavigation, carState, modelV2, frogpilotPlan, frogpilotRadarState)
from each segment's rlog into the installed engine ("old") and a candidate engine file ("new") at 5 Hz, the way
navigation_assistd does, and writes one CSV row per tick with both results.

  python tools/na2/navassist_replay_on_device.py NEW_ENGINE.py ROUTE [ROUTE ...]
  -> /data/na_review/replay.csv.gz
"""
import csv
import gzip
import importlib.util
import os
import sys
from pathlib import Path

sys.path.insert(0, "/data/openpilot")
from cereal import log  # noqa: E402
from openpilot.frogpilot.navigation_assist import engine as old_engine  # noqa: E402
from openpilot.frogpilot.navigation_assist.navigation_assistd import (  # noqa: E402
  DEFAULT_MIN_LANE_SPEED, LANE_LINE_MIN_PROB, radar_alongside, snapshot_from_nav_instruction,
)

REALDATA = Path("/data/media/0/realdata")
OUT = Path("/data/na_review/replay.csv.gz")
TICK = 0.2


def read_events(path):
  data = open(path, "rb").read()
  if data[:4] == bytes.fromhex("28b52ffd"):
    import zstandard
    data = zstandard.ZstdDecompressor().decompress(data, max_output_size=1 << 31)
  elif data[:3] == b"BZh":
    import bz2
    data = bz2.decompress(data)
  return log.Event.read_multiple_bytes(data)


def load_engine(path):
  spec = importlib.util.spec_from_file_location("engine_new", path)
  module = importlib.util.module_from_spec(spec)
  sys.modules["engine_new"] = module        # dataclasses look their module up while the file runs
  spec.loader.exec_module(module)
  return module


def main():
  new_engine = load_engine(sys.argv[1])
  routes = sys.argv[2:]
  engines = {"old": (old_engine, old_engine.NavigationAssistEngine()), "new": (new_engine, new_engine.NavigationAssistEngine())}
  with gzip.open(OUT, "wt", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["segment", "t", "v_ego", "lane_valid", "width_left", "width_right", "nav_distance",
                     "old_state", "old_headline", "new_state", "new_headline", "new_detail", "new_voice", "new_voice_count"])
    for route in routes:
      segments = sorted((d for d in os.listdir(REALDATA) if d.startswith(route + "--")), key=lambda d: int(d.rsplit("--", 1)[1]))
      latest, valid = {}, {}
      nav = nav_at = None
      next_tick = None
      for name, (module, eng) in engines.items():
        eng.reset()
      for seg in segments:
        rlog = REALDATA / seg / "rlog"
        if not rlog.exists():
          continue
        try:
          events = read_events(str(rlog))
        except Exception as error:
          print(f"{seg}: {error}", flush=True)
          continue
        def safe(events):
          try:
            yield from events
          except Exception as error:   # the last segment of a drive is often cut off when the comma powers down
            print(f"{seg}: stopped early ({error})", flush=True)
        for ev in safe(events):
          which = ev.which()
          t = ev.logMonoTime / 1e9
          if which in ("navInstruction", "frogpilotNavigation", "carState", "modelV2", "frogpilotPlan", "frogpilotRadarState"):
            latest[which] = getattr(ev, which).as_builder().as_reader() if which in ("navInstruction",) else getattr(ev, which)
            valid[which] = ev.valid
            if which == "navInstruction":
              nav = snapshot_from_nav_instruction(ev.valid, ev.navInstruction)
              nav_at = t
              latest["nav_updated"] = True
          if next_tick is None:
            next_tick = t
          if t < next_tick or "carState" not in latest:
            continue
          next_tick = t + TICK
          cs = latest["carState"]
          v = float(cs.vEgo)
          lane = {"blindspot_available": False, "lane_info_expected": v >= DEFAULT_MIN_LANE_SPEED + 0.5,
                  "blindspot_left": bool(cs.leftBlindspot), "blindspot_right": bool(cs.rightBlindspot)}
          if "frogpilotRadarState" in latest:
            lane["radar_left_alongside"] = radar_alongside(latest["frogpilotRadarState"].leadLeft)
            lane["radar_right_alongside"] = radar_alongside(latest["frogpilotRadarState"].leadRight)
          if "modelV2" in latest and "frogpilotPlan" in latest and v >= DEFAULT_MIN_LANE_SPEED + 0.5 and valid.get("modelV2", True):
            probs = list(latest["modelV2"].laneLineProbs)
            if len(probs) == 4 and probs[1] >= LANE_LINE_MIN_PROB and probs[2] >= LANE_LINE_MIN_PROB:
              lane["lane_info_valid"] = True
              lane["lane_width_left"] = float(latest["frogpilotPlan"].laneWidthLeft)
              lane["lane_width_right"] = float(latest["frogpilotPlan"].laneWidthRight)
          updated = latest.pop("nav_updated", False)
          results = {}
          for name, (module, eng) in engines.items():
            extra = {"voice_enabled": True} if "voice_enabled" in module.EngineInputs.__dataclass_fields__ else {}
            out = eng.update(module.EngineInputs(
              now=t, enabled=True, destination_set=nav is not None, v_ego=v, nav=nav, nav_received_at=nav_at,
              nav_updated=updated, position_valid=valid.get("frogpilotNavigation", True), is_metric=False, **lane, **extra))
            results[name] = out
          if results["old"].state in ("disabled", "navigationInactive") and results["new"].state in ("disabled", "navigationInactive"):
            continue
          writer.writerow([seg, round(t, 1), round(v, 1), int(lane.get("lane_info_valid", False)),
                           round(lane.get("lane_width_left", 0.0), 1), round(lane.get("lane_width_right", 0.0), 1),
                           round(results["new"].maneuver_distance), results["old"].state, results["old"].headline,
                           results["new"].state, results["new"].headline, results["new"].detail,
                           getattr(results["new"], "voice_prompt", ""), getattr(results["new"], "voice_prompt_count", 0)])
        print(f"{seg} done", flush=True)
  print("replay done", flush=True)


if __name__ == "__main__":
  main()
