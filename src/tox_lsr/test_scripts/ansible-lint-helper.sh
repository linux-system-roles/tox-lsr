#!/bin/bash

set -euo pipefail

#uncomment if you use $ME - otherwise set in utils.sh
#ME=$(basename "$0")
SCRIPTDIR=$(readlink -f "$(dirname "$0")")

. "${SCRIPTDIR}/utils.sh"

role=$(basename "${TOPDIR}")
mm=meta/main.yml
mm_bkup="$LSR_TOX_ENV_TMP_DIR/meta_main.yml.backup"

pre() {
    if [ -f "$mm" ]; then
        cp -p "$mm" "$mm_bkup"
        # change $mm - ensure galaxy_info.role_name and .namespace
        if ! grep -q '^  *namespace:' "$mm"; then
            sed "/galaxy_info:/a\  namespace: $LSR_ROLE2COLL_NAME" -i "$mm"
        fi
        if ! grep -q '^  *role_name:' "$mm"; then
            sed "/galaxy_info:/a\  role_name: $role" -i "$mm"
        fi
    fi
}

post() {
    if [ -f "$mm_bkup" ]; then
        mv "$mm_bkup" "$mm"
    fi
}

"$@"
