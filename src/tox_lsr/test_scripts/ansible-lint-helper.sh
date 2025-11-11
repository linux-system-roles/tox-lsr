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
    # create symlinks for the roles to be FQCN - ansible-lint does not like
    # import_role unless the role is installed in a standard location
    if [ -d roles ]; then
        pushd roles
        for role in *; do
            if [ -d "$role" ]; then
                role_link="$LSR_ROLE2COLL_NAMESPACE.$LSR_ROLE2COLL_NAME.$role"
                if [ -L "$role_link" ]; then
                    continue  # already a symlink
                fi
                ln -s "$role" "$role_link"
            fi
        done
        popd
    fi
}

post() {
    if [ -f "$mm_bkup" ]; then
        mv "$mm_bkup" "$mm"
    fi
    # see above
    if [ -d roles ]; then
        pushd roles
        for role in *; do
            role_link="$LSR_ROLE2COLL_NAMESPACE.$LSR_ROLE2COLL_NAME.$role"
            if [ -L "$role_link" ]; then
                rm "$role_link"
            fi
        done
        popd
    fi
}

"$@"
