#!/usr/bin/env python3
"""Speed limits the driver saved by hand (tap the sign on the driving screen, or The Pond).

Kept in /data/saved_speed_limits.json, outside /data/openpilot, so installing an update never removes them, with a second
copy in /data/media/0 in case the first is ever damaged. Each entry belongs to one map road segment (OSM way) in one
direction, the same key FrogPilot's speed limit filler uses. Saved limits are never uploaded anywhere.

Both the planner (frogpilot_process) and The Pond write this file, so every change re-reads the file under a lock first.
"""
import datetime
import json
import os
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


def way_key(way_id, is_forward):
  return f"{int(way_id)}_{int(bool(is_forward))}"


def parse_way_key(key):
  way_id, _, direction = str(key).partition("_")
  if not way_id.isdigit() or direction not in ("0", "1") or int(way_id) <= 0:
    raise ValueError(f"invalid way key: {key}")
  return int(way_id), direction == "1"


def normalize_entry(entry):
  """Return a clean copy of one saved limit, or None if it isn't valid."""
  if not isinstance(entry, dict):
    return None

  way_id = entry.get("way_id")
  is_forward = entry.get("is_forward")
  speed_limit = entry.get("speed_limit")

  if isinstance(way_id, bool) or not isinstance(way_id, int) or way_id <= 0:
    return None
  if not isinstance(is_forward, bool):
    return None
  if isinstance(speed_limit, bool) or not isinstance(speed_limit, (int, float)):
    return None
  if not MIN_SPEED_LIMIT <= speed_limit <= MAX_SPEED_LIMIT:
    return None

  clean = {"is_forward": is_forward, "speed_limit": float(speed_limit), "way_id": way_id}

  road_name = entry.get("road_name")
  if isinstance(road_name, str) and road_name.strip():
    clean["road_name"] = road_name.strip()[:MAX_ROAD_NAME_LENGTH]

  saved = entry.get("saved")
  if isinstance(saved, str) and len(saved) <= 40:
    clean["saved"] = saved

  for field, bound in (("latitude", 90), ("longitude", 180)):
    value = entry.get(field)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and -bound <= value <= bound:
      clean[field] = round(float(value), 6)

  return clean


def entries_from_data(data):
  entries = {}
  if not isinstance(data, dict):
    return entries

  for entry in data.get("speed_limits", []) if isinstance(data.get("speed_limits"), list) else []:
    clean = normalize_entry(entry)
    if clean is not None:
      entries[way_key(clean["way_id"], clean["is_forward"])] = clean
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

  ordered = sorted(entries.values(), key=lambda entry: (entry["way_id"], entry["is_forward"]))
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

  def get(self, way_id, is_forward):
    entry = self.entries.get(way_key(way_id, is_forward))
    return entry["speed_limit"] if entry else 0

  def _write(self, change):
    with self.write_lock:
      try:
        modify(change, self.path, self.backup_path)
      except OSError:
        return
      self.file_stamp = None  # reload on the next check so both writers agree

  def _apply(self, change, background):
    change(self.entries)
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

  def remove(self, way_id, is_forward, background=True):
    key = way_key(way_id, is_forward)
    if key not in self.entries:
      return False

    def change(entries):
      entries.pop(key, None)

    self._apply(change, background)
    return True
