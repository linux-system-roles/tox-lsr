#!/bin/bash

set -euo pipefail

#uncomment if you use $ME - otherwise set in utils.sh
#ME=$(basename "$0")
SCRIPTDIR=$(readlink -f "$(dirname "$0")")

. "${SCRIPTDIR}/utils.sh"

set -x

lsr_distro_ver=""
osbuild_distro_ver=""
OSBUILD_DIR="${OSBUILD_DIR:-"$(dirname "$SCRIPTDIR")/osbuild-manifests"}"

# input is the distro_ver format used by runqemu --image-name
# lsr_distro_ver is the format used by role/.ostree/
get_distro_ver() {
    if [[ "$1" =~ ^rhel-([0-9]+)-([0-9]+) ]]; then
        lsr_distro_ver="RedHat-${BASH_REMATCH[1]}.${BASH_REMATCH[2]}"
        osbuild_distro_ver="rhel_${BASH_REMATCH[1]}_${BASH_REMATCH[2]}"
    elif [[ "$1" =~ ^centos-([0-9]+) ]]; then
        lsr_distro_ver="CentOS-${BASH_REMATCH[1]}"
        osbuild_distro_ver="cs${BASH_REMATCH[1]}"
    elif [[ "$1" =~ ^fedora-([0-9]+) ]]; then
        lsr_distro_ver="Fedora-${BASH_REMATCH[1]}"
        osbuild_distro_ver="f${BASH_REMATCH[1]}"
    fi
}

# image_name is e.g. rhel-8-9, centos-9, fedora-38
image_name="$1"
IMAGE_DIR="${IMAGE_DIR:-"$HOME/.cache/linux-system-roles"}"
CACHE_DIR="${CACHE_DIR:-"$IMAGE_DIR/$image_name"}"
IMAGE_FILE="${IMAGE_FILE:-"$IMAGE_DIR/${image_name}-ostree.qcow2"}"

if [ "${LSR_BUILD_IMAGE_USE_VM:-false}" = true ] || \
  [ -n "${LSR_BUILD_IMAGE_VM_DISTRO_FILE:-}" ]; then
    if [ -n "${LSR_BUILD_IMAGE_VM_DISTRO_FILE:-}" ]; then
        osbuildvm_mpp_yml="OSBUILDVM_MPP_YML=$LSR_BUILD_IMAGE_VM_DISTRO_FILE"
    fi  # else use the default
    make -C "$OSBUILD_DIR" BUILDDIR="$CACHE_DIR" OUTPUTDIR="$IMAGE_DIR" ${osbuildvm_mpp_yml:-} osbuildvm-images
    use_vm=VM=1
fi

get_distro_ver "$image_name"

if [ -f .ostree/get_ostree_data.sh ]; then
    # read -d "" causes read to exit 1
    read -r -d "" -a pkgs <<< "$(.ostree/get_ostree_data.sh packages testing "$lsr_distro_ver" raw)" || :
    read -r -a extra_pkgs <<< "${LSR_EXTRA_PKGS:-}"
    PKGS_JSON="["
    comma=""
    for pkg in "${pkgs[@]}" "${extra_pkgs[@]}"; do
        PKGS_JSON="${PKGS_JSON}${comma}\"$pkg\""
        comma=","
    done
    PKGS_JSON="${PKGS_JSON}]"
    if grep -q ^get_repos .ostree/get_ostree_data.sh; then
        EXTRA_REPOS="$(.ostree/get_ostree_data.sh repos testing "$lsr_distro_ver" json)"
    fi
fi

if [ -z "${PKGS_JSON:-}" ]; then
    PKGS_JSON="[]"
fi

if [ -z "${EXTRA_REPOS:-}" ]; then
    EXTRA_REPOS="[]"
fi

if [ ! -f "$OSBUILD_DIR/distro/${osbuild_distro_ver}.ipp.yml" ]; then
    extra_distro="EXTRA_DISTRO=$HOME/.config/${osbuild_distro_ver}.ipp.yml"
fi
make -C "$OSBUILD_DIR" BUILDDIR="$CACHE_DIR" OUTPUTDIR="$IMAGE_DIR" DESTDIR="$IMAGE_DIR" \
  "${osbuild_distro_ver}-qemu-lsr-ostree.x86_64.qcow2" \
  ${extra_distro:-} ${use_vm:-} EXTRA_REPOS="$EXTRA_REPOS" \
  DEFINES=extra_rpms="${PKGS_JSON}"
mv "$IMAGE_DIR/${osbuild_distro_ver}-qemu-lsr-ostree.x86_64.qcow2" "$IMAGE_FILE"
