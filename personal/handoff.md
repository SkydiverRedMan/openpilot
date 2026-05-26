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
- SSH on port `22` was closed when checked, so a full `/data/params/d` backup could not be pulled yet.

## Backups

A The Pond toggle backup was saved locally at:

`C:\Users\keith\My Drive\Projects\FrogPilot\device_backups\comma_192.168.68.134_20260526_171855`

That folder is intentionally ignored by git because it may contain settings, tokens, keys, or vehicle-specific params. Do not commit `device_backups/`.

The backup folder contains:

- `toggle-backup.json` from `POST /api/toggles/backup`
- `pond-stats.json`
- `diagnostic-params.json`
- `CarParamsPersistent.param`
- `FrogPilotCarParamsPersistent.param`
- small text snapshots like `CarModel.param`, `GitBranch.param`, and `IsMetric.txt`

For a full backup, enable SSH on the comma, set the GitHub username in device settings, then copy at least:

- `/data/params/d`
- `/data/toggle_backups`
- `/data/backups`

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

1. Enable SSH on the comma and confirm `ssh comma@192.168.68.134` works.
2. Pull a full `/data/params/d` backup before installing anything.
3. Install or test `SkydiverRedMan/openpilot` branch `bsm-highlander-install`.
4. After install, verify BSM behavior on-road or from logs:
   - `carState.leftBlindspot` should go true when the left mirror BSM light is active.
   - `carState.rightBlindspot` should go true when the right mirror BSM light is active.
5. If left/right are flipped on this Highlander, adjust Toyota BSM parsing for this platform before using the feature.
