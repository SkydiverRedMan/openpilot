# FrogPilot fork (SkydiverRedMan/openpilot): working notes for Claude Code

Personal FrogPilot fork for Keith's comma 3X in a Toyota Highlander. Never push to FrogAi/FrogPilot.

## Branches

| Branch | Role |
|---|---|
| `na2-src` | **Work here.** Source branch: FrogPilot "October 31st, 2026 Update" (`8d705650`) + Keith's customizations + Navigation Assist. |
| `na2` | Prebuilt branch the comma installs from (Settings → Software → Update). Only ever updated by `tools/na2/publish_from_pc.sh`. Never edit or force-push. |
| `na2bk` | Untouched na2 at `840d0951` (2026-11-16, before Navigation Assist). Rollback target; tag `na2-baseline-2026-11-16`. |
| others (`bsm`, `na`, `my-frogpilot*`) | Older experiments; leave alone. |

## Rules

* The comma runs a **prebuilt** branch: Update installs the newest `na2` commit as-is and compiles nothing.
  Any change to C++/Qt, `cereal/*.capnp`, or `common/params.cc` keys needs a full rebuild on the comma
  (`tools/na2/build_on_device.sh`). Never replace a single binary, and never add a param key in Python only.
* Keep Keith's customizations: paramotor boot logo and steering wheel, custom startup/engage sounds, Highlander BSM
  (`selfdrive/car/toyota/interface.py`, `opendbc/toyota_tnga_k_pt_generated.dbc`), his default settings, and saved speed
  limits (`docs/saved-speed-limits.md`; data in `/data/saved_speed_limits.json`, never delete it).
* Theme test cycle (2026-11-22): `/data/themes/keith_theme_cycle.json` with `"enabled": true` makes each boot show the next
  theme in its `order` (Keith's 16 themes from SkydiverRedMan/frogpilot-themes), own wheel included; set `enabled` false
  to go back to Random Themes + paramotor wheel lock (no release needed). Holiday Themes was turned off for the test.
* Navigation Assist is advisory only: it must never publish anything controls, planners, models or lane-change code
  read, never steer/signal/change speed. See `docs/navigation-assist/`.
* Install branches stay lean: tests and notes are kept out of `na2` by `release/prepare_release.py`.
* The comma's Software → Target Branch list shows every branch. Only prebuilt branches are safe to select there
  (`na2`, `na2bk`, a future experimental `na2x`); never a `*-src`/`*-source` branch, which would compile on the comma.

## Workflow

1. Edit on `na2-src`, run `pytest frogpilot/navigation_assist/tests frogpilot/controls/lib/tests` (or the Docker / venv
   commands in `docs/navigation-assist/TESTING.md` and `docs/saved-speed-limits.md`), commit, `git push origin na2-src`.
2. Car parked (or the comma on house power), comma on Wi-Fi. Pick one:
   * **Only Python / JS / HTML / CSS / images / sounds changed:** `tools/na2/quick_release_on_device.sh` on the comma.
     Takes a minute or two, no compile, no reboot. It refuses if anything compiled changed.
   * **Anything compiled changed** (C/C++/Qt, `cereal/*.capnp`, params, SConscripts, panda, models):
     `tools/na2/build_on_device.sh`, 15-40 min, comma reboots at the end. Don't tap the comma screen during it.
   Copy the script to the comma and run it detached; exact commands in DEPLOYMENT.md.
3. `tools/na2/publish_from_pc.sh <comma-ip>` (add `--dry-run` to only check). Keith prefers no separate dry run when
   the publish itself runs the same checks; just publish and he presses Update.
4. On the comma: Settings → Software → Update. Roll back with `tools/na2/rollback.sh`.

## Lessons learned (2026-11-18)

* **Large copies from the comma stall** on this network: scp and `ssh cat` hung or were reset after ~100-300 KB, while
  short SSH commands always worked. `publish_from_pc.sh` now copies the release in 32 KB pieces with retries and
  checks the SHA-256. Use the same trick for any file over ~100 KB.
* **The comma's address changes.** 2026-11-18 it was `192.168.68.105`. If `.142`/`.105` time out, scan for it:
  PowerShell port scan of `192.168.68.2-254` for port 22, then `ssh comma@<ip> hostname` (it answers
  `comma-521986ac`). `192.168.68.114` is the Mac.
* **No compile needed ≠ no release needed.** The comma only installs prebuilt `na2` commits. A Python-only change
  still needs a release, but the quick script makes it without recompiling (first done by hand: `33e5b3f`).
* **Quick release, first scripted run (2026-11-22, `fe96284`):** the comma's git (2.25) can't stop lazy fetches in the
  blobless clone, so `read-tree`/`write-tree` fetched every file and hit "Too many open files". The script now rebuilds
  only the changed folders with `git mktree --missing`; it then took under a minute. Large copies didn't stall that day.
* **Offline maps decide where saved limits work by road.** Only NY/PA/NJ/MA/TX (+CA) are downloaded; elsewhere saves
  are GPS spots (since 2026-11-22). Comma address that day: `192.168.68.59`.
* **This PC has no Docker.** Tests ran in a venv instead (`pytest numpy pycapnp==2.0.0 aiohttp`) with a directory
  junction named `openpilot` pointing at the repo on `PYTHONPATH`; see `docs/saved-speed-limits.md`.

Details: `docs/navigation-assist/DEPLOYMENT.md`. Status of milestones: `docs/navigation-assist/ARCHITECTURE.md`.

## Setting up another PC

* **Commit email:** this repo is public, so every PC must commit as GitHub's no-reply address, never a personal or work email:
  `git config user.email 110471467+SkydiverRedMan@users.noreply.github.com` (run inside the clone). History was rewritten
  on 2026-11-18 to remove earlier emails (all commit IDs changed then); any older clone must be re-cloned, not pushed.
* `git clone https://github.com/SkydiverRedMan/openpilot.git FrogPilot && cd FrogPilot && git switch na2-src`
  (no `--recurse-submodules` needed; this tree vendors its dependencies).
* On Windows set `git config core.autocrlf true` for the clone (default for Git for Windows). When passing files to
  Linux (Docker, the comma), export with `git -c core.autocrlf=false archive ...` so shell scripts keep LF endings.
* SSH to the comma: create a key on that PC (`ssh-keygen -t ed25519`), add the public key to the SkydiverRedMan GitHub
  account, then on the comma re-add the GitHub username under SSH Keys so it fetches the new key.
* Docker Desktop is only needed for the PC build/render checks (`Dockerfile.openpilot_base`); unit tests also run in
  `python:3.11-slim` with `pytest` and `pycapnp==2.0.0`.
* Last known comma address: `192.168.68.59` (2026-11-22; it changes) (check FrogPilot → Navigation → "Manage Your Settings At").
