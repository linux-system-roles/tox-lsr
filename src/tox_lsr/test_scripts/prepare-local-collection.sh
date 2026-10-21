#!/bin/bash
# SPDX-License-Identifier: MIT
# Convert the current role, optionally starting from a cached collection.
set -euo pipefail

role_dir="$1"
local_base="$2"
cache_base="$3"
seed_from_cache="${4:-false}"
namespace="${LSR_ROLE2COLL_NAMESPACE:-fedora}"
collection="${LSR_ROLE2COLL_NAME:-linux_system_roles}"
role="$(basename "$role_dir")"
collection_dir="$local_base/ansible_collections/$namespace/$collection"
cached_dir="$cache_base/ansible_collections/$namespace/$collection"
script_dir="$(dirname "$0")"
work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

if [ -n "${LSR_ROLE2COLL_PATH:-}" ]; then
    cp "$LSR_ROLE2COLL_PATH/lsr_role2collection.py" "$work_dir/"
    cp "$LSR_ROLE2COLL_PATH/lsr_role2collection/runtime.yml" "$work_dir/"
    cp "$LSR_ROLE2COLL_PATH/galaxy.yml" "$work_dir/"
else
    repo="https://raw.githubusercontent.com/${LSR_SRC_OWNER:-linux-system-roles}/auto-maintenance/${LSR_ROLE2COLL_VERSION:-main}"
    curl -fLsS -o "$work_dir/lsr_role2collection.py" "$repo/lsr_role2collection.py"
    curl -fLsS -o "$work_dir/runtime.yml" "$repo/lsr_role2collection/runtime.yml"
    curl -fLsS -o "$work_dir/galaxy.yml" "$repo/galaxy.yml"
fi

mkdir -p "$(dirname "$collection_dir")"
if [ "$seed_from_cache" = true ]; then
    if [ ! -f "$cached_dir/MANIFEST.json" ]; then
        echo "Cached collection is missing: $cached_dir" >&2
        exit 1
    fi
    rm -rf "$collection_dir"
    cp -a "$cached_dir" "$collection_dir"
elif [ "$seed_from_cache" != false ]; then
    echo "Unknown collection mode: $seed_from_cache" >&2
    exit 2
fi
# Replace only the current role, leaving other local roles intact.
rm -rf "$collection_dir/roles/$role" "$collection_dir/tests/$role"

python "$work_dir/lsr_role2collection.py" --src-path "$(dirname "$role_dir")" \
    --dest-path "$local_base" --role "$role" --namespace "$namespace" \
    --collection "$collection" --meta-runtime "$work_dir/runtime.yml" \
    --subrole-prefix "private_${role}_subrole_" \
    --src-owner "${LSR_SRC_OWNER:-linux-system-roles}"
cp "$work_dir/galaxy.yml" "$collection_dir/"

if [ -n "${LSR_COLLECTION_VERSION:-}" ]; then
    sed -e "s/^requires_ansible:.*/requires_ansible: \"\>=${LSR_COLLECTION_VERSION}\"/" \
        -i "$collection_dir/meta/runtime.yml"
fi

config_dir="${LSR_CONFIGDIR:-$script_dir/../config_files}"
cp "$config_dir/collection_yamllint.yml" "$collection_dir/.yamllint.yml"
sed -e '/^extends:/d' -i "$collection_dir/.yamllint.yml"
touch "$collection_dir/CHANGELOG.md"
if [ -f "$role_dir/.ansible-lint" ]; then
    cp "$role_dir/.ansible-lint" "$collection_dir/"
fi
for file in "$role_dir"/.sanity-ansible-ignore-*.txt; do
    if [ -f "$file" ]; then
        mkdir -p "$collection_dir/tests/sanity"
        cp "$file" "$collection_dir/tests/sanity/${file##*.sanity-ansible-}"
    fi
done
