# FrogPilot Personal Handoff

Last updated: 2026-05-26

## Current Branches

- `my-frogpilot`: compiled/install branch that was originally checked out locally. The comma device was running commit `63b1beb44e729c023b0b7068d1ca91607fcf78b0` from branch `FrogPilot`.
- `my-frogpilot-source`: source branch. Before the BSM work, latest useful source commit was `bdb5e53 Add navigation assist mode toggle scaffold`.
- `bsm-highlander-source`: source branch with the Toyota Highlander BSM fix. BSM fix commit: `9d15fcc Enable BSM for Toyota Highlander`.
- `bsm-highlander-install`: compiled/install test branch with the same BSM fix applied to the install tree. BSM fix commit: `ae53fb2 Enable BSM for Toyota Highlander`.

## Device

- Device IP found on Wi-Fi: `192.168.68.134`.
- The Pond web UI is reachable at `http://192.168.68.134:8082`.
- On 2026-05-26, SSH was enabled on the comma and the GitHub username `SkydiverRedMan` was added for SSH keys.
- `ssh comma@192.168.68.134` works from Keith's laptop after removing a stale `known_hosts` entry for that IP.
- The Pond web UI served a blank dark page in Chrome, but the backend API still worked. A direct `POST /api/toggles/backup` succeeded.

## Install Address

Use this full installer URL on the comma:

`https://installer.comma.ai/SkydiverRedMan/bsm-highlander-install`

The short installer entry should also work:

`SkydiverRedMan/bsm-highlander-install`

This installs the compiled/install branch with the backed-up defaults, Toyota Highlander BSM enablement, the Navigation Assist placeholder toggle, and Keith's custom startup sound.

Install note from 2026-05-26:

- Keith started installing this branch on the comma and saw the installer at about 26%.
- This can be slower than the prior FrogPilot install because the setup installer clones the custom branch from GitHub with submodules unless it can use a local cache.
- Keep the device powered and on reliable Wi-Fi. Do not interrupt unless it errors or sits with no progress for a long time.

## Backups

A The Pond toggle backup was saved locally at:

`C:\Users\keith\My Drive\Projects\FrogPilot\device_backups\comma_192.168.68.134_20260526_171855`

A fresh SSH/settings backup was saved locally at:

`C:\Users\keith\My Drive\Projects\FrogPilot\device_backups\comma_192.168.68.134_ssh_20260526_181543`

That folder is intentionally ignored by git because it may contain settings, tokens, keys, or vehicle-specific params. Do not commit `device_backups/`.

The first backup folder contains:

- `toggle-backup.json` from `POST /api/toggles/backup`
- `pond-stats.json`
- `diagnostic-params.json`
- `CarParamsPersistent.param`
- `FrogPilotCarParamsPersistent.param`
- small text snapshots like `CarModel.param`, `GitBranch.param`, and `IsMetric.txt`

The SSH backup folder contains:

- `params/` copied from `/data/params`
- `toggle_backups/` copied from `/data/toggle_backups`
- `themes/` copied from `/data/themes`
- `openpilot_frogpilot_assets/active_theme/` copied from `/data/openpilot/frogpilot/assets/active_theme`
- `toggle-backup-from-pond.json` from direct The Pond backup API
- `device_snapshot.txt` with hostname, branch, commit, git status, and selected `/data` folder sizes

Large folders intentionally not copied unless needed:

- `/data/backups` was about 5.1 GB
- `/data/models` was about 2.1 GB
- `/data/openpilot` was about 1.3 GB

## Defaults From Backup

On 2026-05-26, the Pond toggle backup was decoded locally and used to update code defaults for the user's preferred FrogPilot driving/UI behavior.

Updated files:

- Install branch: `frogpilot/common/frogpilot_variables.py`
- Source branch: `common/params_keys.h`

Only the active/default value was changed for each setting. Stock defaults were left unchanged.

Intentionally not committed as defaults:

- account, token, key, username, dongle, and network fields
- vehicle identity/runtime params such as `CarMake`, `CarModel`, and car params blobs
- location/search/map selections such as favorites, last search, and selected map regions
- cache/update/runtime state such as downloaded theme/model metadata

## Navigation Assist Placeholder

On 2026-05-26, a `NavigationAssistedDecisions` feature flag was added as a future expansion point.

- Install branch: the Navigation panel has a `Navigation Assist Mode` toggle, the param exists in defaults/params, and the planner has a no-op route-context scaffold.
- Source branch: the same scaffold exists; the toggle now also plays the prompt sound when flipped.
- Current behavior is intentionally safe: flipping the toggle refreshes FrogPilot settings and plays a sound, but it does not change steering, braking, acceleration, or lane changes.

## Custom Startup Sound

On 2026-05-26, `Keith-WooHoo.m4a` was converted to `frogpilot/assets/random_events/sounds/startup.wav`.

- Format: mono, 16-bit PCM WAV, 48 kHz.
- This path is loaded by `selfdrive/ui/soundd.py` before active theme sounds, so it overrides the default FrogPilot startup sound.

## Future RedManPilot Branding

Keith wants to consider changing user-facing FrogPilot branding to `RedManPilot` and customizing graphics after the current install is verified.

Recommended approach:

- Do a cosmetic/user-facing rebrand only: labels, splash/boot graphics, offroad UI graphics, theme name, sounds, steering wheel assets, and other visible theme assets.
- Keep internal `frogpilot` folders, modules, params, and scripts named as-is to reduce merge conflicts and avoid breaking update/install assumptions.
- Treat personal photos carefully because committed assets may be public on GitHub. If using a photo of Keith's wife, get clear permission first or keep those assets private/local.
- Avoid using a face/photo for safety-critical onroad icons if it makes state recognition slower or less clear.
- Make this a separate pass after verifying the BSM fix, settings defaults, startup sound, and install behavior.

## Lane Change / BSM Issue

Observed behavior: FrogPilot starts a nudgeless lane change after the signal delay even when the vehicle mirror blind spot indicator is lit.

Device diagnostic params showed:

- `CarMake = Toyota`
- `CarModel = TOYOTA_HIGHLANDER`
- `LaneChanges = 1`
- `NudgelessLaneChange = 1`
- `LaneChangeTime = 0.500000`
- `MinimumLaneChangeSpeed = 20.000000`
- `LaneDetectionWidth = 0.000000`
- `OneLaneChange = 1`
- `BlindSpotPath = 1`
- `BlindSpotMetrics = 1`

Root cause found in code:

- The generic lane-change state machine already blocks lane changes when `carState.leftBlindspot` or `carState.rightBlindspot` is true.
- Toyota `CP.enableBsm` was only enabled when CAN message `0x3F6` exists and the candidate is in `TSS2_CAR`.
- The device identifies as non-TSS2 `TOYOTA_HIGHLANDER`, so BSM parsing was disabled even if message `0x3F6` is present.
- The non-TSS2 Highlander DBC also lacked a `BSM` message definition, so enabling `CP.enableBsm` required adding that parser definition too.

Fix applied:

- Source branch file: `opendbc_repo/opendbc/car/toyota/interface.py`
- Source branch DBC: `opendbc_repo/opendbc/dbc/generator/toyota/toyota_tnga_k_pt.dbc`
- Install branch file: `selfdrive/car/toyota/interface.py`
- Install branch DBC: `opendbc/toyota_tnga_k_pt_generated.dbc`

The core logic now enables BSM for `TOYOTA_HIGHLANDER` when CAN message `0x3F6` is present.

## Validation Done

- `python -m py_compile` passed for the Toyota interface file.
- `git diff --check` passed.
- Toyota pytest did not run locally because the local Python environment is missing `capnp`.

## Next Steps

1. Install or test `https://installer.comma.ai/SkydiverRedMan/bsm-highlander-install`.
2. After install, verify BSM behavior on-road or from logs:
   - `carState.leftBlindspot` should go true when the left mirror BSM light is active.
   - `carState.rightBlindspot` should go true when the right mirror BSM light is active.
3. If left/right are flipped on this Highlander, adjust Toyota BSM parsing for this platform before using the feature.
