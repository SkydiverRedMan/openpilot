#!/usr/bin/env python3
"""Review Navigation Assist on real drives (runs ON THE COMMA, reads qlogs; changes nothing).

For every segment whose qlog has navigationAssist messages, writes one CSV row per navigationAssist message (1 Hz in
qlogs) with what it showed and what the car was doing at that moment. Output: /data/na_review/rows.csv.gz.

  python tools/na2/navassist_review_on_device.py [--since YYYY-MM-DD]
"""
import argparse
import csv
import datetime
import gzip
import os
import sys
from pathlib import Path

sys.path.insert(0, "/data/openpilot")
from cereal import log  # noqa: E402


def LogReader(path):
  """Raw, zstd or bz2 qlog/rlog (the install branch has no tools/lib, so this reads them with cereal directly)."""
  data = open(path, "rb").read()
  if data[:4] == bytes.fromhex("28b52ffd"):
    import zstandard
    data = zstandard.ZstdDecompressor().decompress(data, max_output_size=1 << 31)
  elif data[:3] == b"BZh":
    import bz2
    data = bz2.decompress(data)
  return log.Event.read_multiple_bytes(data)

REALDATA = Path("/data/media/0/realdata")
OUT = Path("/data/na_review")

FIELDS = ["segment", "t", "state", "kind", "direction", "distance", "time_to", "confidence", "visible", "urgency",
          "headline", "distance_text", "detail", "route_changes", "nav_age", "lane_info", "lane_left", "lane_right",
          "mapbox_lanes", "mapbox_active", "v_ego", "left_blinker", "right_blinker", "steering_pressed", "engaged",
          "lane_change_state", "lane_change_direction", "lat", "lon", "nav_remaining", "nav_text", "nav_valid"]


def segment_key(name):
  route, _, seg = name.rpartition("--")
  return (os.path.getmtime(REALDATA / name / "qlog"), route, int(seg) if seg.isdigit() else 0)


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument("--since", default=None)
  args = parser.parse_args()
  since = datetime.datetime.strptime(args.since, "%Y-%m-%d").timestamp() if args.since else 0

  segments = [d.name for d in REALDATA.iterdir() if d.is_dir() and d.name.count("--") == 2 and (d / "qlog").exists()]
  segments = [s for s in segments if os.path.getmtime(REALDATA / s / "qlog") >= since]
  segments.sort(key=segment_key)
  OUT.mkdir(exist_ok=True)
  rows = 0
  with gzip.open(OUT / "rows.csv.gz.tmp", "wt", newline="") as out:
    writer = csv.writer(out)
    writer.writerow(FIELDS)
    for i, seg in enumerate(segments):
      latest = {}
      try:
        for msg in LogReader(str(REALDATA / seg / "qlog")):
          which = msg.which()
          if which in ("carState", "controlsState", "selfdriveState", "modelV2", "navInstruction", "gpsLocationExternal",
                       "gpsLocation"):
            latest[which] = getattr(msg, which)
            latest[which + "_valid"] = msg.valid
            continue
          if which != "navigationAssist":
            continue
          na = msg.navigationAssist
          if na.state in ("disabled", "navigationInactive") and not na.displayVisible:
            continue
          cs = latest.get("carState")
          ctl = latest.get("selfdriveState") or latest.get("controlsState")
          meta = latest.get("modelV2").meta if latest.get("modelV2") is not None else None
          gps = latest.get("gpsLocationExternal") or latest.get("gpsLocation")
          nav = latest.get("navInstruction")
          writer.writerow([
            seg, msg.logMonoTime / 1e9, na.state, na.maneuverKind, na.direction, round(na.maneuverDistance, 1),
            round(na.timeToManeuver, 1), round(na.confidence, 2), int(na.displayVisible), na.urgency, na.headline,
            na.distanceText, na.detail, na.routeChangeCount, round(na.navigationAge, 1), int(na.laneInfoAvailable),
            int(na.adjacentLaneLeft), int(na.adjacentLaneRight), na.mapboxLaneCount, na.mapboxActiveLanes,
            round(cs.vEgo, 2) if cs else "", int(cs.leftBlinker) if cs else "", int(cs.rightBlinker) if cs else "",
            int(cs.steeringPressed) if cs else "", int(ctl.enabled) if ctl else "",
            meta.laneChangeState if meta else "", meta.laneChangeDirection if meta else "",
            round(gps.latitude, 6) if gps else "", round(gps.longitude, 6) if gps else "",
            round(nav.distanceRemaining, 0) if nav else "", nav.maneuverPrimaryText if nav else "", int(latest.get("navInstruction_valid", False)) if nav else "",
          ])
          rows += 1
      except Exception as error:   # a damaged segment must not stop the review
        print(f"{seg}: {error}", flush=True)
      if i % 20 == 0:
        print(f"{i + 1}/{len(segments)} segments, {rows} rows", flush=True)
  (OUT / "rows.csv.gz.tmp").rename(OUT / "rows.csv.gz")
  print(f"done: {len(segments)} segments, {rows} rows -> {OUT / 'rows.csv.gz'}", flush=True)


if __name__ == "__main__":
  main()
