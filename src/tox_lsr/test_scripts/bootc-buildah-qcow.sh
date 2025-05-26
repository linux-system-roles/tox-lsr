#!/bin/sh
# Build a qcow2 image from a bootc buildah container
# resulting image will be in tmp/<buildah id>/qcow2/disk.qcow2
# Usage: build-buildah-qcow.sh <buildah id>
set -eu

BUILDAH_ID="$1"

MYDIR=$(dirname $0)
OCI_TAG="localhost/bootc-tmp:$BUILDAH_ID"

# extract private SSH key from standard-inventory-qcow2, and generate pubkey from it
# keep this in sync with ./runqemu.py
INVENTORY_URL="https://pagure.io/fork/rmeggins/standard-test-roles/raw/linux-system-roles/f/inventory/standard-inventory-qcow2"
INVENTORY="${TOX_WORK_DIR:-.tox}/standard-inventory-qcow2"
[ -e "$INVENTORY" ] || curl --fail -o "$INVENTORY" "$INVENTORY_URL"

PUBKEY=$(sed -n '/BEGIN.*PRIVATE KEY/,/END.*PRIVATE KEY/ { s/^.*"""//; p }' \
    "$INVENTORY" | ssh-keygen -y -f /dev/stdin)

# user's or system podman storage location
STORAGE=$(podman info -f '{{.Store.GraphRoot}}')

OS_RELEASE=$(buildah run "$BUILDAH_ID" cat /etc/os-release)

# buildah → container image
buildah commit "$BUILDAH_ID" "$OCI_TAG"
# always clean up the temporary tag
trap "podman rmi $OCI_TAG" EXIT INT QUIT PIPE

# invoke booc-image-builder
rm -rf tmp
OUTPUT="./tmp/$BUILDAH_ID"
mkdir -p "$OUTPUT"

cat <<EOF > tmp/bib.config.json
{
    "blueprint": {
        "customizations": {
            "user": [
                {"name": "root", "password": "foobar", "key": "$PUBKEY"}
            ]
        }
    }
}
EOF

# for local development, support adding "sudo_password" to the vault, see README.md
# not necessary for e.g. GitHub actions which has passwordless sudo
if [ -e vault_pwd ] && [ -e vars/vault-variables.yml ]; then
    export SUDO_ASKPASS="$MYDIR/vault-sudo-askpass.sh"
fi

# boot-cimage-builder must be run as root container; also support breaking out of toolbox
AM_ROOT=
if systemd-detect-virt --quiet --container; then
    if [ -n "${SUDO_ASKPASS:-}" ]; then
        # the helper is in toolbox, not the host; so we can only feed the password via stdin
        run_root() { "$SUDO_ASKPASS" | flatpak-spawn --host sudo -S -- "$@"; }
    else
        # best-effort: won't work in Ansible (no stdin), but for interactive calling
        run_root() { flatpak-spawn --host sudo -S -- "$@"; }
    fi
elif [ "$(id -u)" != 0 ]; then
    if [ -n "${SUDO_ASKPASS:-}" ]; then
        run_root() { sudo -A -- "$@"; }
    else
        run_root() { sudo -- "$@"; }
    fi
else
    AM_ROOT=1
    run_root() { "$@"; }
fi

# GitHub's runners create a $STORAGE/db.sql which contains the absolute storage path; that breaks
# podman in the bootc-image-builder container. This is just a cache and can be removed safely
if [ -z "$AM_ROOT" ] && [ -e "$STORAGE/db.sql" ]; then
    mv "$STORAGE/db.sql" "$STORAGE/db.sql.bak"
fi

# image-builder requires --rootfs option for Fedora
if echo "$OS_RELEASE" | grep -q '^ID=fedora'; then
    ROOTFS_OPT="--rootfs=btrfs"
fi

# image-builder unfortunately needs $STORAGE to be writable, but that would destroy
# permissions on the host; so mount it with a temp overlay
run_root podman run --rm -i --privileged --security-opt=label=type:unconfined_t \
    --volume="$STORAGE":/var/lib/containers/storage:O \
    --volume=./tmp/bib.config.json:/config.json \
    --volume="$OUTPUT":/output \
    quay.io/centos-bootc/bootc-image-builder:latest \
    --type=qcow2 ${ROOTFS_OPT:-} --config=/config.json \
    "$OCI_TAG"

# when running as user, restore permissions
if [ -z "$AM_ROOT" ]; then
    run_root chown -R "$(id -u):$(id -g)" "$OUTPUT"
    if [ -e "$STORAGE/db.sql.bak" ]; then
        mv "$STORAGE/db.sql.bak" "$STORAGE/db.sql"
    fi
fi
