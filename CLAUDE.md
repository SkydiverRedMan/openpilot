# FrogPilot fork (SkydiverRedMan/openpilot): working notes for Claude Code

Personal FrogPilot fork for Keith's comma 3X in a Toyota Highlander. Never push to FrogAi/FrogPilot.

## Branches

| Branch | Role |
|---|---|
| `na2-src` | **Work here.** Source branch: FrogPilot "October 31st, 2026 Update" (`8d705650`) + Keith's customizations + Navigation Assist. |
| `na2` | Prebuilt branch the comma installs from (Settings → Software → Update). Only ever updated by `tools/na2/publish_from_pc.sh`. Never edit or force-push. |
| `na2bk` | Untouched na2 at `3fe4ed25` (2026-11-16, before Navigation Assist). Rollback target; tag `na2-baseline-2026-11-16`. |
| others (`bsm`, `na`, `my-frogpilot*`) | Older experiments; leave alone. |

## Rules

* The comma runs a **prebuilt** branch: Update installs the newest `na2` commit as-is and compiles nothing.
  Any change to C++/Qt, `cereal/*.capnp`, or `common/params.cc` keys needs a full rebuild on the comma
  (`tools/na2/build_on_device.sh`). Never replace a single binary, and never add a param key in Python only.
* Keep Keith's customizations: paramotor boot logo and steering wheel, custom startup/engage sounds, Highlander BSM
  (`selfdrive/car/toyota/interface.py`, `opendbc/toyota_tnga_k_pt_generated.dbc`), his default settings.
* Navigation Assist is advisory only: it must never publish anything controls, planners, models or lane-change code
  read, never steer/signal/change speed. See `docs/navigation-assist/`.
* Install branches stay lean: tests and notes are kept out of `na2` by `release/prepare_release.py`.
* The comma's Software → Target Branch list shows every branch. Only prebuilt branches are safe to select there
  (`na2`, `na2bk`, a future experimental `na2x`); never a `*-src`/`*-source` branch, which would compile on the comma.

## Workflow

1. Edit on `na2-src`, run `pytest frogpilot/navigation_assist/tests` (or the Docker command in
   `docs/navigation-assist/TESTING.md`), commit, `git push origin na2-src`.
2. Car parked, comma on Wi-Fi: copy `tools/na2/build_on_device.sh` to the comma and run it detached (exact commands in DEPLOYMENT.md). Don't tap the comma screen during the build.
3. `tools/na2/publish_from_pc.sh <comma-ip> --dry-run`, then without `--dry-run`.
4. On the comma: Settings → Software → Update. Roll back with `tools/na2/rollback.sh`.

Details: `docs/navigation-assist/DEPLOYMENT.md`. Status of milestones: `docs/navigation-assist/ARCHITECTURE.md`.

## Setting up another PC

* `git clone https://github.com/SkydiverRedMan/openpilot.git FrogPilot && cd FrogPilot && git switch na2-src`
  (no `--recurse-submodules` needed; this tree vendors its dependencies).
* On Windows set `git config core.autocrlf true` for the clone (default for Git for Windows). When passing files to
  Linux (Docker, the comma), export with `git -c core.autocrlf=false archive ...` so shell scripts keep LF endings.
* SSH to the comma: create a key on that PC (`ssh-keygen -t ed25519`), add the public key to the SkydiverRedMan GitHub
  account, then on the comma re-add the GitHub username under SSH Keys so it fetches the new key.
* Docker Desktop is only needed for the PC build/render checks (`Dockerfile.openpilot_base`); unit tests also run in
  `python:3.11-slim` with `pytest` and `pycapnp==2.0.0`.
* Last known comma address: `192.168.68.142` (2026-11-16; it changes) (check FrogPilot → Navigation → "Manage Your Settings At").
