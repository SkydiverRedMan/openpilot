# FrogPilot Personal Handoff

Last updated: 2026-05-27

## Current Status

The comma successfully booted after installing the clean BSM branch:

`SkydiverRedMan/bsm`

Expected installed commit:

`3d2ec297`

This is now the recommended installer path. It is a lean prebuilt install branch and intentionally does not contain the `personal/` notes or random-events showcase files.

## What `bsm` Contains

- Toyota Highlander BSM enablement:
  - `selfdrive/car/toyota/interface.py` enables BSM for `TOYOTA_HIGHLANDER` when CAN message `0x3F6` is present.
  - `opendbc/toyota_tnga_k_pt_generated.dbc` includes the `BSM` message with `L_ADJACENT` and `R_ADJACENT`.
- Custom paramotor boot logo:
  - `frogpilot/assets/other_images/frogpilot_boot_logo.png`
- Corrected custom startup sound location:
  - `frogpilot/assets/random_events/sounds/startup.wav`
  - This is the direct override path read by `selfdrive/ui/soundd.py`, so it avoids the earlier issue where the sound lived only in the frog/holiday theme path.
- Old working prebuilt UI binary:
  - `selfdrive/ui/ui`
  - Do not replace it with the previously rebuilt UI binary.

## Current Branch Guide

- `bsm`: current clean comma installer. Use this for the Highlander BSM fix, boot logo, and custom startup sound.
- `my-frogpilot`: older stable prebuilt branch. Useful as a known-good base, but it does not include the Highlander BSM install work.
- `bsm-highlander-install`: historical/test branch with the heavier notes/random files and failed UI rebuild history. Do not install this unless intentionally reviewing history.
- `bsm-highlander-source`: source-side BSM work branch.
- `my-frogpilot-source`: source-side Navigation Assist scaffold branch.

The deleted temporary branch `bsm-highlander-clean-install` was replaced by short branch `bsm`.

## Device Notes

- Device IP found on Wi-Fi: `192.168.68.134`.
- The Pond web UI has been reachable at `http://192.168.68.134:8082`.
- SSH was enabled on 2026-05-26 and GitHub username `SkydiverRedMan` was added for SSH keys.
- If SSH complains about host identity after a reset/reinstall, remove the stale `known_hosts` entry for `192.168.68.134`.

## Backups

Local backups were saved under:

`C:\Users\keith\My Drive\Projects\FrogPilot\device_backups`

That folder is intentionally ignored by git because it may contain settings, tokens, keys, or vehicle-specific params. Do not commit `device_backups/`.

Known backup folders:

- `comma_192.168.68.134_20260526_171855`
- `comma_192.168.68.134_ssh_20260526_181543`

## Active Next Steps

1. When the comma is fully up, verify the installed branch and commit over SSH if possible:
   - branch should be `bsm`
   - commit should be `3d2ec297`
2. Carefully test BSM behavior before trusting lane-change blocking:
   - left mirror BSM light should produce `carState.leftBlindspot = true`
   - right mirror BSM light should produce `carState.rightBlindspot = true`
3. If left/right are flipped, fix Toyota BSM parsing before relying on the lane-change behavior.
4. Only after BSM behavior is verified should any new UI or branding work be considered.

## Expired Or Completed Notes

- Installing `SkydiverRedMan/bsm-highlander-install` is expired. Use `SkydiverRedMan/bsm`.
- The long branch `bsm-highlander-clean-install` was temporary and has been deleted from GitHub.
- The installer failures around `bsm-highlander-install` are considered superseded by the successful lean `bsm` install.
- The custom startup sound wrong-path issue is complete: the sound is now in `frogpilot/assets/random_events/sounds/startup.wav` on `bsm`.
- The paramotor boot logo install is complete.
- The persistent-param crash from `NavigationAssistedDecisions` is complete: do not add new persistent params to prebuilt branches without rebuilding the matching compiled params extension.
- The failed native UI rebuild path is expired as an active plan. Keep it only as a warning.

## Native UI Warning

Do not try to make the native `Navigation Assist Mode` button show up again by transplanting a single rebuilt `selfdrive/ui/ui` binary.

What happened historically:

- The C++ source contained the button, but the prebuilt UI binary did not.
- A UI binary rebuilt directly on the comma was ARM64 and contained the button text.
- After install, the comma reached the boot logo but the UI did not stay up.
- Wayland/Qt environment fixes and manager launch workarounds did not make it stable.
- The install branch was rolled back to the old working prebuilt UI binary.

If native UI changes are needed later, build a complete matching prebuilt release from one source commit, or put personal/test controls in The Pond web UI instead.

## Future Work

- Verify and, if needed, correct the Highlander BSM left/right mapping.
- Consider a cosmetic RedManPilot pass only after driving behavior is verified.
- Keep installer branches lean. Notes, showcase files, and experiment logs should stay off the comma install branch.
