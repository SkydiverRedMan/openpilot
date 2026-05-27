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

The short installer entry worked on the comma and is easier to type:

`SkydiverRedMan/bsm-highlander-install`

This installs the compiled/install branch with the backed-up defaults, Toyota Highlander BSM enablement, the Navigation Assist placeholder toggle, and Keith's custom startup sound.

Install note from 2026-05-26:

- Keith started installing this branch on the comma and saw the installer at about 26%.
- This can be slower than the prior FrogPilot install because the setup installer clones the custom branch from GitHub with submodules unless it can use a local cache.
- Keep the device powered and on reliable Wi-Fi. Do not interrupt unless it errors or sits with no progress for a long time.

Install error note from 2026-05-26:

- The first custom install reached "finalizing install" and then failed at startup with a manager traceback.
- Screenshot was moved locally to `C:\Users\keith\My Drive\Projects\FrogPilot\device_backups\install_errors\2026-05-26-manager-param-error.jpg`. It was not committed because it is a phone/device photo.
- Traceback pointed at `system/manager/manager.py` while initializing FrogPilot default params, through `common.params_pyx.Params.check_key`.
- Root cause: the install/prebuilt branch has a committed compiled `common/params_pyx.so` from `63b1beb Compile FrogPilot`. The new `NavigationAssistedDecisions` param was added after that compile, so the source had the key but the compiled params extension on-device did not.
- Fix: remove the new persistent param from the install branch and make the Navigation Assist placeholder a non-persistent test button that only refreshes FrogPilot toggles and plays a prompt sound.

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
- Do not add new persistent params to the install/prebuilt branch unless `common/params_pyx.so` is rebuilt for the device. Adding a new key only to `common/params.cc` can crash manager startup.
- Treat personal photos carefully because committed assets may be public on GitHub. If using a photo of Keith's wife, get clear permission first or keep those assets private/local.
- Avoid using a face/photo for safety-critical onroad icons if it makes state recognition slower or less clear.
- Make this a separate pass after verifying the BSM fix, settings defaults, startup sound, and install behavior.

## Custom Paramotor Boot Graphic

On 2026-05-26, the FrogPilot boot graphic was replaced with an original paramotor-themed emblem inspired by, but not copied from, Keith's `Paramotor Flight Tracker` app icon.

- Install branch asset: `frogpilot/assets/other_images/frogpilot_boot_logo.png`
- Source branch asset: `frogpilot/assets/other_images/frogpilot_boot_logo.jpg`
- The artwork is intentionally rotated inside the portrait-sized file to match the original comma/FrogPilot boot-logo display orientation.
- The stock restore image `frogpilot/assets/other_images/stock_bg.jpg` was not changed.
- If the comma is already installing while this commit is pushed, it may not pick up this image until the next reinstall/update depending on when the installer fetched the branch.

## Random Events Showcase

On 2026-05-26, a local showcase folder was added for Keith to browse the funny FrogPilot random-event sounds, popup/banner text, icons, and steering wheel animations on the laptop:

`personal/random_events_showcase/`

Contents:

- `README.md` catalogs the random-event popup text, sounds, visual assets, and trigger conditions.
- `play_random_event_sounds.ps1` plays every random-event WAV in order from PowerShell.
- `random_events_assets/` is copied from `frogpilot/assets/random_events/`.
- `stock_openpilot_sounds/` contains the normal openpilot alert sounds used by some FrogPilot banners.
- `holiday_theme_sounds/` contains the holiday theme sound packs.

The running assistant message transcript is being tracked in:

`personal/assistant_message_log.md`

## Navigation Assist Button UI Rebuild

On 2026-05-26, the missing `Navigation Assist Mode` button was traced to a stale prebuilt UI executable:

- Source already contained the button in `frogpilot/ui/qt/offroad/navigation_settings.cc`.
- The device's installed source file also contained the button text.
- The running executable `/data/openpilot/selfdrive/ui/ui` did not contain `Navigation Assist Mode`, so the C++ UI binary had not been rebuilt.

Fix path used:

- Copied the full source tree from the laptop to the comma in verified chunks.
- Reassembled `/data/frogpilot-source.tar` on the comma and verified its SHA-256 hash against the laptop archive.
- Extracted to `/data/build_openpilot_ui`, added temporary local Git metadata, installed `uv`, ran `uv sync --frozen`, then built `selfdrive/ui/ui` on the comma with `scons -j2 --minimal selfdrive/ui/ui`.
- Verified the rebuilt executable is ARM64/aarch64 and contains `Navigation Assist Mode`.
- Stripped debug symbols before copying back: the rebuilt binary went from about 74 MB to about 3.5 MB.

The install branch now has the rebuilt `selfdrive/ui/ui` binary. After the comma installs this update, the Navigation page should show `Navigation Assist Mode` with a `TEST` button.

## Louder WooHoo Startup Sound

On 2026-05-26, Keith noticed the custom WooHoo startup sound was quieter than the other FrogPilot sounds.

Change made:

- `frogpilot/assets/random_events/sounds/startup.wav` was amplified by `+4 dB`.
- Audio format stayed the same: 48 kHz, mono, 16-bit PCM WAV, about 3.01 seconds.
- Volume changed from roughly `mean=-20.8 dB, max=-4.7 dB` to `mean=-16.8 dB, max=-0.7 dB`.
- The same audio change was applied in both the install worktree and the source worktree.

## Boot Logo Hang After UI Update

After the rebuilt UI update was installed on the comma, the device reached the FrogPilot boot logo but did not show the normal UI.

Findings:

- SSH still worked at `192.168.68.134`, so the device was not bricked.
- `/data/openpilot` was on commit `e8938a7`.
- The rebuilt `selfdrive/ui/ui` binary was present and executable.
- Running the UI without display variables aborted during Qt display/platform initialization.
- Running the same UI manually with `QT_QPA_PLATFORM=wayland`, `XDG_RUNTIME_DIR=/var/tmp/weston`, and `WAYLAND_DISPLAY=wayland-0` worked.

Fix:

- Added those Weston/Qt display defaults to `launch_env.sh`.
- Copied the fixed `launch_env.sh` directly to `/data/openpilot/launch_env.sh` on the comma.
- Rebooted the comma so the boot script would source the new environment.

## Resume After Laptop WSL Reboot

Keith is rebooting the laptop to install WSL while the comma is downloading/reinstalling `SkydiverRedMan/bsm-highlander-install`.

When continuing:

1. Ask Keith what happened on the comma install screen after download/finalizing.
2. Research the internet for how other openpilot/FrogPilot developers build or rebuild the Qt UI for comma hardware:
   - whether people successfully compile `selfdrive/ui/ui` directly on a comma 3/3X,
   - whether WSL/Ubuntu cross-compiling is preferred,
   - what official or community build commands/toolchains are recommended,
   - and whether committing a stripped `selfdrive/ui/ui` binary into an installer branch is reliable.
3. Compare that research against what happened here: on-device compile worked, but the rebuilt UI needed explicit Weston display environment variables in `launch_env.sh`.
4. Before rebuilding UI again, decide whether to use WSL/Ubuntu locally, build on the comma, or avoid binary rebuilds unless absolutely needed.

## UI Segfault Under Manager After Install

After the install finished, the comma showed the custom boot logo but did not advance to the normal UI. SSH still worked.

Findings:

- Installed branch was `bsm-highlander-install`.
- The device eventually updated to commit `066d5cf`.
- `launch_env.sh` had the Weston variables and manager inherited them.
- `managerState` showed `ui running=False should=True exit=-11`, meaning the manager-launched UI segfaulted.
- Running the same UI from a shell survived until manually killed by `timeout`.
- Reproduced the crash by launching UI through Python `multiprocessing.Process`, matching manager's native launcher path.
- Launching UI with `subprocess.Popen` survived.

Fix:

- Patched `system/manager/process.py` so native processes launch through a small `NativeSubprocess` wrapper using `subprocess.Popen`.
- Added dead-process clearing before process start so a one-time native crash does not leave manager latched to a dead process object.
- Hotpatched `/data/openpilot/system/manager/process.py` on the comma, syntax-checked it, converted LF line endings, and rebooted.
- On the next boot, the first UI attempt still exited `-11`, manager logged `ui exited with -11, restarting`, and the restarted `./ui` stayed running.

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
