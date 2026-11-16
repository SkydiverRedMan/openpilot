# Navigation Assist: deployment to the comma 3X

## How the comma gets updates (investigated 2026-11-16)

* The comma was installed from `installer.comma.ai/SkydiverRedMan/na2`, which clones
  `https://github.com/SkydiverRedMan/openpilot.git`, branch `na2`, into `/data/openpilot`.
* **Settings → Software → Update** runs `system/updated/updated.py`: `git fetch origin na2`, then
  `git checkout --force -B na2 FETCH_HEAD`, `git reset --hard`, `git clean -xdff`, AGNOS update if needed, and a
  finalized overlay that is swapped in at the next reboot. There is no update server or manifest: **the newest commit
  on GitHub `na2` is the update.** A new commit hash is what makes the device offer it.
* `na2` is a **prebuilt** branch (`prebuilt` file present). The device does **not** compile anything on update, and
  `git clean -xdff` deletes anything not committed. So every compiled file must be in the commit.
* Pushing source changes to `na2` alone would therefore install Python that expects a param key and schema the old
  compiled `params_pyx.so` and UI don't have, which crashes (this happened before). Replacing only `selfdrive/ui/ui`
  was unstable before, because it was built from different source.

## The supported release path

FrogPilot builds its releases on comma devices (`.github/workflows/compile_frogpilot.yaml`, self-hosted runners on a
C3/C3X): full `scons` build of one source commit, then `release/prepare_release.py`, which copies runtime files and
compiled outputs, adds `prebuilt`, and verifies imports and shared libraries. `tools/na2/build_on_device.sh` does the
same on your comma, from `na2-src`.

```
na2-src (source, GitHub) ──► comma: build_on_device.sh ──► release commit (on the comma)
                                                                │
PC: publish_from_pc.sh ◄── git fetch over SSH ──────────────────┘
        │  checks: built on top of current na2, prebuilt marker, aarch64 UI, no tests
        └─► git push origin <release>:na2   (fast-forward, never forced)
comma: Settings → Software → Update  ──► installs it normally
```

The release commit has two parents: the previous `na2` release and the `na2-src` commit it was built from. So `na2`
history is never rewritten, and each release records its exact source.

The panda firmware is kept byte-identical to the current `na2` when the panda source is unchanged (it is), so an
update never reflashes the panda unnecessarily.

## One-time setup

1. **SSH key on this PC.** In Git Bash: `ssh-keygen -t ed25519` (accept defaults), then add the contents of
   `~/.ssh/id_ed25519.pub` to GitHub → Settings → SSH and GPG keys on the `SkydiverRedMan` account. The comma copies
   that account's keys when the GitHub username is entered (Settings → Network → Advanced → SSH Keys; done
   2026-05-26), so after adding the new key press **Remove** and **Add** `SkydiverRedMan` again to refresh. Then test:
   `ssh comma@192.168.68.134 echo ok`.
2. **Comma on the same Wi-Fi**, car parked. The last known address is `192.168.68.134`; check it in FrogPilot →
   Navigation → "Manage Your Settings At".
3. GitHub push access from this PC already works (it pushed the `na2bk` backup).

No GitHub secrets or Actions runners are needed. (Optional later: register the comma as a self-hosted GitHub Actions
runner and use FrogPilot's `compile_frogpilot.yaml`; that needs a runner token and a personal access token, and keeps
the comma busy, so it is not set up.)

## Each release

From the repo on the PC (Git Bash), with `na2-src` pushed:

```bash
git push origin na2-src
```

```bash
ssh comma@192.168.68.134 'bash -s' < tools/na2/build_on_device.sh
```

(openpilot stops during the 15-40 minute build and restarts afterwards, even if the build fails.)

```bash
tools/na2/publish_from_pc.sh 192.168.68.134 --dry-run
```

```bash
tools/na2/publish_from_pc.sh 192.168.68.134
```

Then on the comma: **Settings → Software → Check / Update**, and reboot when it asks.

Before publishing, the dry run proves the exact commit is retrievable and builds on the current `na2`; after the push
the script confirms GitHub's `na2` points at it, which is exactly what `updated` fetches.

## Recovery

* **Updated but something is wrong, comma still boots:** `tools/na2/rollback.sh` pushes a new commit whose files equal
  `na2bk` (the pre-Navigation-Assist release). Then Settings → Software → Update. History is kept.
* **Roll back to any earlier na2 release:** `tools/na2/rollback.sh <commit>`.
* **The comma does not boot into openpilot:** reinstall with the comma installer URL
  `installer.comma.ai/SkydiverRedMan/na2bk` (uninstall from the device's recovery/reset menu, then Custom Software).
  `na2bk` and tag `na2-baseline-2026-11-16` are the untouched 2026-11-16 release `3fe4ed25`. Restore your settings
  from a toggle backup made **before** the update (see `KNOWN-LIMITATIONS.md`).
* Before the first update, back up your toggles: The Pond → Manage Toggles → Backup Toggles.

## Status

See the results table in `TESTING.md` and the session notes in the commit history for what has been built, published
and installed. Nothing is published to `na2` until a device build passes its checks.
