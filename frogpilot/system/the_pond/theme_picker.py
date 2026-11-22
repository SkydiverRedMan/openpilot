"""The Pond: Keith's "Pick a Theme" page. Lists every installed full theme and switches everything to one right away.

Switching is done by frogpilot_process (theme_manager.apply_picked_theme) when it sees the request file, the same path
the parked long-press on the driving screen's wheel button uses.
"""
import json

from aiohttp import web

from openpilot.frogpilot.assets.theme_manager import KEITH_WHEEL, ThemeManager, load_theme_cycle, request_theme
from openpilot.frogpilot.common import frogpilot_paths
from openpilot.frogpilot.system.the_pond import utilities

IMAGE_EXTENSIONS = (".gif", ".png", ".svg")

routes = web.RouteTableDef()


def display_name(key):
  base = key.removesuffix("-user_created")
  animated = base.endswith("-animated")
  base = base.removesuffix("-animated")
  base, _, creator = base.partition("~")
  name = " ".join(word.capitalize() for word in base.replace("_", " ").split())
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
  return ThemeManager.get_full_themes()


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
  cycle = load_theme_cycle()
  themes = [{"colors": colors_of(key), "current": key == current, "key": key, "name": display_name(key)} for key in installed()]
  themes.sort(key=lambda theme: (not theme["key"].endswith("-user_created"), theme["name"].lower()))
  return web.json_response({
    "cycle": {"enabled": cycle is not None, "next": display_name(cycle["order"][cycle.get("next", 0) % len(cycle["order"])])
              if cycle and cycle["order"] else None},
    "current": current,
    "themes": themes,
  })


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
