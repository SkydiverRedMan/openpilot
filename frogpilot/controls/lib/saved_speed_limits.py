#!/usr/bin/env python3
"""Speed limits the driver saved by hand (tap the sign on the driving screen, or The Pond).

Kept in /data/saved_speed_limits.json, outside /data/openpilot, so installing an update never removes them, with a second
copy in /data/media/0 in case the first is ever damaged. Saved limits are never uploaded anywhere.

Two kinds of entry:
* Road: one map road segment (OSM way) in one direction, the same key FrogPilot's speed limit filler uses. Needs the
  offline maps for the area.
* GPS spot ("kind": "gps"): where there's no offline map, the limit is pinned to the spot and heading where it was saved.
  Driving past the spot in that direction switches the limit on; the speed limit controller keeps it on like a posted
  sign (see SpeedLimitController.update_gps_latch).

Both the planner (frogpilot_process) and The Pond write this file, so every change re-reads the file under a lock first.
"""
import datetime
import json
import math
import os
import re
import threading
import time

from contextlib import contextmanager
from pathlib import Path

try:
  import fcntl
except ImportError:  # Windows, for unit tests only
  fcntl = None

from openpilot.frogpilot.common import frogpilot_paths

SCHEMA_VERSION = 1

# Accepted range, m/s: 5 mph to 90 mph (8 km/h to 145 km/h)
MIN_SPEED_LIMIT = 2.2
MAX_SPEED_LIMIT = 40.3

MAX_ENTRIES = 50000
MAX_ROAD_NAME_LENGTH = 100

RELOAD_INTERVAL = 1.0

GPS_KIND = "gps"
SPOT_RADIUS = 40.0             # m: passing within this distance of a spot counts as passing it
SPOT_HEADING_TOLERANCE = 35.0  # degrees: and heading the same way
SPOT_KEY_PATTERN = re.compile(r"^gps_-?\d{1,2}\.\d{5}_-?\d{1,3}\.\d{5}_\d{1,3}$")

EARTH_RADIUS = 6371000.0


def way_key(way_id, is_forward):
  return f"{int(way_id)}_{int(bool(is_forward))}"


def spot_key(latitude, longitude, bearing):
  return f"gps_{latitude:.5f}_{longitude:.5f}_{int(round(bearing)) % 360}"


def parse_way_key(key):
  way_id, _, direction = str(key).partition("_")
  if not way_id.isdigit() or direction not in ("0", "1") or int(way_id) <= 0:
    raise ValueError(f"invalid way key: {key}")
  return int(way_id), direction == "1"


def is_valid_key(key):
  """A road key ('123_1') or a GPS spot key ('gps_40.12345_-75.12345_270')."""
  if SPOT_KEY_PATTERN.match(str(key)):
    return True
  try:
    parse_way_key(key)
  except ValueError:
    return False
  return True


def entry_key(entry):
  if entry.get("kind") == GPS_KIND:
    return spot_key(entry["latitude"], entry["longitude"], entry["bearing"])
  return way_key(entry["way_id"], entry["is_forward"])


def heading_difference(a, b):
  return abs((a - b + 180) % 360 - 180)


def distance(latitude1, longitude1, latitude2, longitude2):
  """Meters between two nearby points (equirectangular, plenty for tens of km)."""
  x = math.radians(longitude2 - longitude1) * math.cos(math.radians((latitude1 + latitude2) / 2))
  y = math.radians(latitude2 - latitude1)
  return EARTH_RADIUS * math.hypot(x, y)


def _number(value):
  return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def normalize_entry(entry):
  """Return a clean copy of one saved limit, or None if it isn't valid."""
  if not isinstance(entry, dict):
    return None

  speed_limit = entry.get("speed_limit")
  if not _number(speed_limit) or not MIN_SPEED_LIMIT <= speed_limit <= MAX_SPEED_LIMIT:
    return None

  if entry.get("kind") == GPS_KIND:
    latitude, longitude, bearing = entry.get("latitude"), entry.get("longitude"), entry.get("bearing")
    if not (_number(latitude) and _number(longitude) and _number(bearing)):
      return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
      return None
    clean = {"bearing": round(float(bearing) % 360, 1), "kind": GPS_KIND, "latitude": round(float(latitude), 6),
             "longitude": round(float(longitude), 6), "speed_limit": float(speed_limit)}
  else:
    way_id = entry.get("way_id")
    is_forward = entry.get("is_forward")
    if isinstance(way_id, bool) or not isinstance(way_id, int) or way_id <= 0:
      return None
    if not isinstance(is_forward, bool):
      return None

    clean = {"is_forward": is_forward, "speed_limit": float(speed_limit), "way_id": way_id}

    for field, bound in (("latitude", 90), ("longitude", 180)):
      value = entry.get(field)
      if _number(value) and -bound <= value <= bound:
        clean[field] = round(float(value), 6)

  road_name = entry.get("road_name")
  if isinstance(road_name, str) and road_name.strip():
    clean["road_name"] = road_name.strip()[:MAX_ROAD_NAME_LENGTH]

  saved = entry.get("saved")
  if isinstance(saved, str) and len(saved) <= 40:
    clean["saved"] = saved

  return clean


def entries_from_data(data):
  entries = {}
  if not isinstance(data, dict):
    return entries

  for entry in data.get("speed_limits", []) if isinstance(data.get("speed_limits"), list) else []:
    clean = normalize_entry(entry)
    if clean is not None:
      entries[entry_key(clean)] = clean
  return entries


def _read_entries(path):
  """Entries in one file, or None when it's missing or unreadable."""
  try:
    with open(path) as file:
      data = json.load(file)
  except (OSError, ValueError):
    return None

  if not isinstance(data, dict) or not isinstance(data.get("speed_limits"), list):
    return None
  return entries_from_data(data)


def read_entries(path=None, backup_path=None):
  path = Path(path or frogpilot_paths.SAVED_SPEED_LIMITS_PATH)
  backup_path = Path(backup_path or frogpilot_paths.SAVED_SPEED_LIMITS_BACKUP_PATH)

  entries = _read_entries(path)
  if entries is None:
    entries = _read_entries(backup_path)
  return entries or {}


def _write_atomic(path, text):
  path = Path(path)
  path.parent.mkdir(parents=True, exist_ok=True)

  temp_path = path.with_name(f"{path.name}.tmp")
  with open(temp_path, "w") as file:
    file.write(text)
    file.flush()
    os.fsync(file.fileno())
  os.replace(temp_path, path)


def write_entries(entries, path=None, backup_path=None):
  path = Path(path or frogpilot_paths.SAVED_SPEED_LIMITS_PATH)
  backup_path = Path(backup_path or frogpilot_paths.SAVED_SPEED_LIMITS_BACKUP_PATH)

  ordered = [entries[key] for key in sorted(entries)]
  text = json.dumps({"schema_version": SCHEMA_VERSION, "speed_limits": ordered}, separators=(",", ":"))

  _write_atomic(path, text)
  try:
    _write_atomic(backup_path, text)
  except OSError:
    pass  # the main copy is what matters


@contextmanager
def file_lock(path=None):
  path = Path(path or frogpilot_paths.SAVED_SPEED_LIMITS_PATH)
  if fcntl is None:
    yield
    return

  path.parent.mkdir(parents=True, exist_ok=True)
  with open(path.with_name(f"{path.name}.lock"), "a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
      yield
    finally:
      fcntl.flock(lock, fcntl.LOCK_UN)


def modify(change, path=None, backup_path=None):
  """Re-read the file, apply change(entries) in place, and write it back. Returns the new entries."""
  with file_lock(path):
    entries = read_entries(path, backup_path)
    change(entries)
    if len(entries) > MAX_ENTRIES:
      for key in sorted(entries, key=lambda key: entries[key].get("saved", ""))[:len(entries) - MAX_ENTRIES]:
        del entries[key]
    write_entries(entries, path, backup_path)
  return entries


def now_stamp():
  return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def spots_near(entries, latitude, longitude, bearing, radius=SPOT_RADIUS, tolerance=SPOT_HEADING_TOLERANCE):
  """Keys of GPS spots within radius of the point, facing within tolerance of the bearing, nearest first."""
  found = []
  for key, entry in entries.items():
    if entry.get("kind") != GPS_KIND or abs(entry["latitude"] - latitude) > 0.01:
      continue
    if heading_difference(entry["bearing"], bearing) > tolerance:
      continue
    meters = distance(latitude, longitude, entry["latitude"], entry["longitude"])
    if meters <= radius:
      found.append((meters, key))
  return [key for _, key in sorted(found)]


class SavedSpeedLimits:
  """In-memory view for the planner. Reloads when The Pond changes the file; saves on a background thread."""

  def __init__(self, path=None, backup_path=None, clock=time.monotonic):
    self.path = Path(path or frogpilot_paths.SAVED_SPEED_LIMITS_PATH)
    self.backup_path = Path(backup_path or frogpilot_paths.SAVED_SPEED_LIMITS_BACKUP_PATH)
    self.clock = clock

    self.entries = read_entries(self.path, self.backup_path)
    self.file_stamp = self._stamp()
    self.last_check = clock()

    self.write_lock = threading.Lock()

    self._spot_version = None
    self._spot_cells = {}
    self.version = 0

  def _stamp(self):
    try:
      stat = self.path.stat()
      return (stat.st_mtime_ns, stat.st_size)
    except OSError:
      return None

  def refresh(self):
    now = self.clock()
    if now - self.last_check < RELOAD_INTERVAL:
      return
    self.last_check = now

    stamp = self._stamp()
    if stamp != self.file_stamp:
      self.file_stamp = stamp
      self.entries = read_entries(self.path, self.backup_path)
      self.version += 1

  def get(self, way_id, is_forward):
    entry = self.entries.get(way_key(way_id, is_forward))
    return entry["speed_limit"] if entry else 0

  def _cells(self):
    """GPS spots grouped by ~1 km cell, rebuilt only when the entries change (this runs 20 times a second)."""
    if self._spot_version != self.version:
      cells = {}
      for key, entry in self.entries.items():
        if entry.get("kind") == GPS_KIND:
          cells.setdefault((round(entry["latitude"] * 100), round(entry["longitude"] * 100)), {})[key] = entry
      self._spot_cells = cells
      self._spot_version = self.version
    return self._spot_cells

  def find_spot(self, latitude, longitude, bearing):
    """(key, entry) of the nearest saved GPS spot being passed in the same direction, or None."""
    cells = self._cells()
    if not cells:
      return None

    row, column = round(latitude * 100), round(longitude * 100)
    nearby = {}
    for d_row in (-1, 0, 1):
      for d_column in (-1, 0, 1):
        nearby.update(cells.get((row + d_row, column + d_column), {}))

    keys = spots_near(nearby, latitude, longitude, bearing)
    return (keys[0], nearby[keys[0]]) if keys else None

  def _write(self, change):
    with self.write_lock:
      try:
        modify(change, self.path, self.backup_path)
      except OSError:
        return
      self.file_stamp = None  # reload on the next check so both writers agree

  def _apply(self, change, background):
    change(self.entries)
    self.version += 1
    if background:
      threading.Thread(target=self._write, args=(change,), daemon=True).start()
    else:
      self._write(change)

  def save(self, way_id, is_forward, speed_limit, road_name="", latitude=None, longitude=None, background=True):
    entry = normalize_entry({
      "is_forward": is_forward,
      "latitude": latitude,
      "longitude": longitude,
      "road_name": road_name,
      "saved": now_stamp(),
      "speed_limit": speed_limit,
      "way_id": way_id,
    })
    if entry is None:
      return False

    key = way_key(way_id, is_forward)

    def change(entries):
      entries[key] = entry

    self._apply(change, background)
    return True

  def save_spot(self, latitude, longitude, bearing, speed_limit, road_name="", background=True):
    """Pin a limit to a GPS spot and heading. Replaces any spot already saved there for the same direction.

    Returns the new spot's key, or None if the values aren't valid.
    """
    entry = normalize_entry({
      "bearing": bearing,
      "kind": GPS_KIND,
      "latitude": latitude,
      "longitude": longitude,
      "road_name": road_name,
      "saved": now_stamp(),
      "speed_limit": speed_limit,
    })
    if entry is None:
      return None

    key = entry_key(entry)

    def change(entries):
      for old in spots_near(entries, entry["latitude"], entry["longitude"], entry["bearing"]):
        entries.pop(old, None)
      entries[key] = entry

    self._apply(change, background)
    return key

  def remove(self, way_id, is_forward, background=True):
    return self.remove_key(way_key(way_id, is_forward), background)

  def remove_key(self, key, background=True):
    if key not in self.entries:
      return False

    def change(entries):
      entries.pop(key, None)

    self._apply(change, background)
    return True
