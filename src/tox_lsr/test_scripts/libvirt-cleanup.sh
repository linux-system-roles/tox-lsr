#!/bin/bash
# SPDX-License-Identifier: MIT
#
# Run cleanup.sh in every libvirt-* workdir under the image cache.

set -euo pipefail

IMAGE_DIR="${LSR_QCOW_IMAGE_DIR:-$HOME/.cache/linux-system-roles}"

if [ ! -d "$IMAGE_DIR" ]; then
    echo "Image directory does not exist: $IMAGE_DIR" >&2
    exit 1
fi

found=0
for workdir in "$IMAGE_DIR"/libvirt-*; do
    if [ ! -d "$workdir" ]; then
        continue
    fi
    cleanup_script="$workdir/cleanup.sh"
    if [ ! -f "$cleanup_script" ]; then
        echo "Skipping $workdir: no cleanup.sh" >&2
        continue
    fi
    if [ ! -x "$cleanup_script" ]; then
        chmod +x "$cleanup_script"
    fi
    found=1
    echo "Running $cleanup_script"
    "$cleanup_script"
done

if [ "$found" -eq 0 ]; then
    echo "No libvirt workdirs with cleanup.sh found in $IMAGE_DIR"

fi
