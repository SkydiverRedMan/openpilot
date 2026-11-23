"""The Pond: Keith's "Pick a Theme" page. Lists Keith's own installed themes by category (never downloaded ones) and
switches everything to one right away.

Switching is done by frogpilot_process (theme_manager.apply_picked_theme) when it sees the request file, the same path
the parked long-press on the driving screen's wheel button uses.
"""
import json

from aiohttp import web

from openpilot.frogpilot.assets.theme_manager import (FAVORITES, KEITH_THEME_CATEGORIES, KEITH_WHEEL, ThemeManager, cycle_status,
                                                      keith_theme_groups, peek_next_theme, request_theme, theme_settings,
                                                      update_theme_settings)
from openpilot.frogpilot.common import frogpilot_paths
from openpilot.frogpilot.system.the_pond import utilities

IMAGE_EXTENSIONS = (".gif", ".png", ".svg")

routes = web.RouteTableDef()


def display_name(key):
  base = key.removesuffix("-user_created")
  animated = base.endswith("-animated")
  base = base.removesuffix("-animated")
  base, _, creator = base.partition("~")
  special = {"redman": "RedMan", "hud": "HUD", "1984": "1984"}
  small = {"and", "of", "the"}
  words = base.replace("_", " ").split()
  name = " ".join(special.get(w, w if (i and w in small) else w.capitalize()) for i, w in enumerate(words))
  if animated:
    name += " (animated)"
  if creator:
    name += f" by {creator}"
  return name


def active_theme():
  """The theme whose icons are active right now."""
  try:
    return (frogpilot_paths.ACTIVE_THEME_PATH / "icons").resolve().parent.name
  except OSError:
    return None


def installed():
  """Keith's own full themes only; downloaded themes stay on the comma but aren't offered."""
  return [key for group in keith_theme_groups(ThemeManager.get_full_themes()) for key in group[1]]


def get_key(request):
  key = request.match_info["key"]
  if key not in installed():
    raise web.HTTPNotFound(text="not_found")
  return key


def first_image(folder, stem):
  for extension in IMAGE_EXTENSIONS:
    path = folder / f"{stem}{extension}"
    if path.is_file():
      return path
  return None


def colors_of(key):
  try:
    colors = json.loads((frogpilot_paths.THEME_PACKS_PATH / key.removesuffix("-animated") / "colors" / "colors.json").read_text())
  except (OSError, ValueError):
    return []
  out = []
  for name in ("Path", "PathEdge", "LaneLines", "LeadMarker"):
    value = colors.get(name)
    if isinstance(value, dict):
      out.append(f"rgb({value.get('red', 0)},{value.get('green', 0)},{value.get('blue', 0)})")
  return out


@routes.get("/api/theme_picker")
async def list_themes(request):
  current = active_theme()
  settings = theme_settings()
  favorites = set(settings["favorites"])
  groups = [{"name": category, "themes": [{"colors": colors_of(key), "current": key == current, "favorite": key in favorites, "key": key,
                                           "name": display_name(key)} for key in keys]}
            for category, keys in keith_theme_groups(ThemeManager.get_full_themes())]
  status = cycle_status()
  cycle = {"enabled": status is not None}
  if status is not None:
    cycle_current, boots_left, following = status
    cycle.update({"current": display_name(cycle_current) if cycle_current else None, "boots_left": boots_left,
                  "next": display_name(following) if following else None})
  categories = [name for name in KEITH_THEME_CATEGORIES if any(group["name"] == name for group in groups)] + [FAVORITES]
  return web.json_response({"categories": categories, "current": current, "cycle": cycle, "groups": groups, "settings": settings})


@routes.post("/api/theme_picker/settings")
async def save_settings(request):
  """How themes change: mode, start-ups per theme, categories, and starring a favorite."""
  changes = await utilities.read_json(request)
  if not isinstance(changes, dict):
    raise web.HTTPBadRequest(text="bad_settings")
  if changes.get("favorite") is not None and changes["favorite"] not in installed():
    raise web.HTTPBadRequest(text="unknown_theme")
  return web.json_response(update_theme_settings(changes))


@routes.post("/api/theme_picker/next")
async def next_now(request):
  """Switch to the theme that would come next, right away."""
  key = peek_next_theme()
  if key is None or key not in installed():
    raise web.HTTPBadRequest(text="no_next_theme")
  request_theme(key)
  return web.json_response({"name": display_name(key)})


@routes.get("/api/theme_picker/{key}/home")
async def theme_icon(request):
  key = get_key(request)
  path = first_image(frogpilot_paths.THEME_PACKS_PATH / key / "icons", "button_home")
  if path is None:
    raise web.HTTPNotFound(text="not_found")
  return web.FileResponse(path, headers={"Cache-Control": "max-age=300"})


@routes.get("/api/theme_picker/{key}/wheel")
async def theme_wheel(request):
  key = get_key(request)
  path = first_image(frogpilot_paths.STEERING_WHEELS_PATH, key) or \
         first_image(frogpilot_paths.STEERING_WHEELS_PATH, key.removesuffix("-animated")) or \
         first_image(frogpilot_paths.STEERING_WHEELS_PATH, KEITH_WHEEL)
  if path is None:
    raise web.HTTPNotFound(text="not_found")
  return web.FileResponse(path, headers={"Cache-Control": "max-age=300"})


@routes.post("/api/theme_picker/apply")
async def apply_theme(request):
  key = (await utilities.read_json(request)).get("key")
  if not isinstance(key, str) or key not in installed():
    raise web.HTTPBadRequest(text="unknown_theme")
  request_theme(key)
  return web.json_response({"name": display_name(key)})
