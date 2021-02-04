#!/bin/bash
# SPDX-License-Identifier: MIT

# A shell wrapper around ansible-doc.

set -euo pipefail

ME=$(basename "$0")
SCRIPTDIR=$(readlink -f "$(dirname "$0")")

. "$SCRIPTDIR/utils.sh"

if [ "${LSR_ROLE2COLL_NAMESPACE:-}" = "" -o "${LSR_ROLE2COLL_NAME:-}" = "" ]; then
    lsr_info "${ME}: Collection format only."
    exit 1
fi

LSR_ROLE2COLL_MODULES="$MY_LSR_TOX_ENV_DIR"/ansible_collections/"$LSR_ROLE2COLL_NAMESPACE"/"$LSR_ROLE2COLL_NAME"/plugins/modules

rval=0
if [ -d "$LSR_ROLE2COLL_MODULES" ]; then
  modules=()
  for module_path in $( ls "$LSR_ROLE2COLL_MODULES" ); do
    module_file=$( basename $module_path )
    module="${module_file%%.*}"
    modules+=("$LSR_ROLE2COLL_NAMESPACE"."$LSR_ROLE2COLL_NAME"."$module")
  done

  for module in "${modules[@]}"; do
    lsr_info "${ME}: Checking $module ..."
    if ! ANSIBLE_COLLECTIONS_PATHS="$MY_LSR_TOX_ENV_DIR" ansible-doc \
        -M "$LSR_ROLE2COLL_MODULES" -vvv --type module "$module"; then
        rval=1
    fi
  done
fi
exit $rval
