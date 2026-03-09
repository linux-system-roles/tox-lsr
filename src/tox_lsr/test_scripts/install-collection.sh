#!/bin/bash
# SPDX-License-Identifier: MIT

set -euo pipefail

ME=$(basename "$0")
SCRIPTDIR=$(readlink -f "$(dirname "$0")")

. "$SCRIPTDIR/utils.sh"

if [ -z "${LSR_ROLE2COLL_NAMESPACE:-}" ] || [ -z "${LSR_ROLE2COLL_NAME:-}" ]; then
  lsr_info "${ME}: Collection format only."
  exit 1
fi

for file in $TOX_WORK_DIR/$LSR_ROLE2COLL_NAMESPACE-$LSR_ROLE2COLL_NAME-*.tar.gz; do
  if [ -f "$file" ]; then
    collection_file="$file"
    break
  fi
done

if [ -z "${collection_file:-}" ]; then
  lsr_error "${ME}: No collection file found in $TOX_WORK_DIR - please run 'tox -e build-collection' first."
  exit 1
fi

lsr_info "${ME}: Installing collection from $collection_file"

if ! ansible_galaxy=$(type -p ansible-galaxy) || [ -z "${ansible_galaxy:-}" ]; then
  lsr_error "${ME}: ansible-galaxy not found"
fi

"$ansible_galaxy" collection install --force -p "$TOX_WORK_DIR" --offline --no-deps "$collection_file" "$@"
