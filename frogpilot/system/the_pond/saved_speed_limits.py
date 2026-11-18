"""The Pond: list, edit, remove, back up and restore Keith's saved speed limits.

The backup file also carries FrogPilot's learned limits (/data/speed_limit_filler.json), so a reset or a new device can get
both back. Restoring learned limits only adds roads the device doesn't already know, and needs a reboot before driving,
because the planner keeps its own copy in memory and would write over the file at the end of the next drive.
"""
import datetime
import json

from aiohttp import web

from openpilot.common.conversions import Conversions as CV

from openpilot.frogpilot.common import frogpilot_paths, frogpilot_utilities
from openpilot.frogpilot.controls.lib import saved_speed_limits as store
from openpilot.frogpilot.system.the_pond import utilities

BACKUP_KIND = "frogpilot-speed-limits-backup"
BACKUP_VERSION = 1

routes = web.RouteTableDef()


def conversion(params):
  return CV.MS_TO_KPH if params.get_bool("IsMetric") else CV.MS_TO_MPH


def get_key(request):
  key = request.match_info["key"]
  try:
    store.parse_way_key(key)
  except ValueError:
    raise web.HTTPNotFound(text="not_found") from None
  return key


def learned_entries():
  data = frogpilot_utilities.load_json_file(frogpilot_paths.SPEED_LIMIT_FILLER_PATH)
  speed_limits = data.get("speed_limits") if isinstance(data.get("speed_limits"), list) else []
  confirmations = data.get("confirmations") if isinstance(data.get("confirmations"), list) else []
  return data, speed_limits, confirmations


def learned_key(entry):
  if not isinstance(entry, dict):
    return None
  way_id, is_forward = entry.get("way_id"), entry.get("is_forward")
  if isinstance(way_id, bool) or not isinstance(way_id, int) or not isinstance(is_forward, bool):
    return None
  if isinstance(entry.get("speed_limit"), bool) or not isinstance(entry.get("speed_limit"), (int, float)):
    return None
  return (way_id, is_forward)


def merge_learned(imported):
  """Add learned limits and confirmations for roads the device doesn't know yet. Returns how many were added."""
  if not isinstance(imported, dict):
    return 0

  data, speed_limits, confirmations = learned_entries()
  added = 0

  merged = {}
  for name, current in (("speed_limits", speed_limits), ("confirmations", confirmations)):
    known = {learned_key(entry) for entry in current} - {None}
    incoming = imported.get(name) if isinstance(imported.get(name), list) else []

    result = list(current)
    for entry in incoming:
      key = learned_key(entry)
      if key is None or key in known:
        continue
      known.add(key)
      result.append(entry)
      if name == "speed_limits":
        added += 1
    merged[name] = result

  if merged["speed_limits"] != speed_limits or merged["confirmations"] != confirmations:
    frogpilot_utilities.update_json_file(frogpilot_paths.SPEED_LIMIT_FILLER_PATH, {**data, **merged})
  return added


@routes.get("/api/saved_speed_limits")
async def list_saved_speed_limits(request):
  the_pond = request.app[utilities.THE_POND]
  factor = conversion(the_pond.params)

  rows = []
  for key, entry in store.read_entries().items():
    rows.append({
      "key": key,
      "latitude": entry.get("latitude"),
      "longitude": entry.get("longitude"),
      "road_name": entry.get("road_name", ""),
      "saved": entry.get("saved", ""),
      "speed_limit": round(entry["speed_limit"] * factor),
    })
  rows.sort(key=lambda row: (row["road_name"].lower() or "~", row["saved"]))

  _, learned, _ = learned_entries()
  return web.json_response({
    "learned_count": len(learned),
    "metric": the_pond.params.get_bool("IsMetric"),
    "speed_limits": rows,
  })


@routes.put("/api/saved_speed_limits/{key}")
async def edit_saved_speed_limit(request):
  the_pond = request.app[utilities.THE_POND]
  key = get_key(request)

  value = (await utilities.read_json(request)).get("speed_limit")
  if isinstance(value, bool) or not isinstance(value, (int, float)):
    raise web.HTTPBadRequest(text="invalid_speed_limit")
  speed_limit = value / conversion(the_pond.params)
  if not store.MIN_SPEED_LIMIT <= speed_limit <= store.MAX_SPEED_LIMIT:
    raise web.HTTPBadRequest(text="invalid_speed_limit")

  found = False

  def change(entries):
    nonlocal found
    if key in entries:
      found = True
      entries[key] = {**entries[key], "saved": store.now_stamp(), "speed_limit": float(speed_limit)}

  store.modify(change)
  if not found:
    raise web.HTTPNotFound(text="not_found")
  return web.json_response({"ok": True})


@routes.delete("/api/saved_speed_limits/{key}")
async def remove_saved_speed_limit(request):
  key = get_key(request)
  store.modify(lambda entries: entries.pop(key, None))
  return web.Response(status=204)


@routes.get("/api/saved_speed_limits/export")
async def export_speed_limits(request):
  learned, _, _ = learned_entries()
  backup = {
    "exported": store.now_stamp(),
    "kind": BACKUP_KIND,
    "learned": learned,
    "saved": {"schema_version": store.SCHEMA_VERSION, "speed_limits": list(store.read_entries().values())},
    "version": BACKUP_VERSION,
  }
  name = f"speed-limits-{datetime.date.today().isoformat()}.json"
  return web.Response(body=json.dumps(backup, indent=1).encode(), content_type="application/json",
                      headers={"Content-Disposition": f'attachment; filename="{name}"'})


@routes.post("/api/saved_speed_limits/import")
async def import_speed_limits(request):
  the_pond = request.app[utilities.THE_POND]
  backup = await utilities.read_json(request)
  if backup.get("kind") != BACKUP_KIND or not isinstance(backup.get("saved"), dict):
    raise web.HTTPBadRequest(text="not_a_backup")

  incoming = store.entries_from_data(backup["saved"])
  store.modify(lambda entries: entries.update(incoming))

  learned_added = 0
  learned_skipped = False
  if isinstance(backup.get("learned"), dict) and backup["learned"]:
    if the_pond.params.get_bool("IsOnroad"):
      learned_skipped = True
    else:
      learned_added = merge_learned(backup["learned"])

  return web.json_response({
    "learned_added": learned_added,
    "learned_skipped": learned_skipped,
    "reboot_required": learned_added > 0,
    "saved_restored": len(incoming),
  })
