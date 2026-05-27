#!/usr/bin/bash

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1

# The rebuilt Qt UI needs the Weston socket when launched by the boot tmux script.
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-wayland}"
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/var/tmp/weston}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"

if [ -z "$AGNOS_VERSION" ]; then
  export AGNOS_VERSION="10.1"
fi

export STAGING_ROOT="/data/safe_staging"
