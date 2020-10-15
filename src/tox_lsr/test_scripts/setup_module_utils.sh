#!/bin/bash
# SPDX-License-Identifier: MIT

set -euo pipefail

if [ -n "${DEBUG:-}" ] ; then
    set -x
fi

if [ "$LSR_TOX_ENV_NAME" = pylint ] && [ -n "${RUN_PYLINT_SETUP_MODULE_UTILS:-}" ]; then
    : # pass
elif [ "$LSR_TOX_ENV_NAME" = pytest ] && [ -n "${RUN_PYTEST_SETUP_MODULE_UTILS:-}" ]; then
    : # pass
else
    exit 0
fi

if [ ! -d "${SRC_MODULE_UTILS_DIR:-}" ] ; then
    echo Either ansible is not installed, or there is no ansible/module_utils
    echo in "${SRC_MODULE_UTILS_DIR:-}" - Skipping
    exit 0
fi

if [ ! -d "${DEST_MODULE_UTILS_DIR:-}" ] ; then
    echo Role has no module_utils - Skipping
    exit 0
fi

# we need absolute path for $DEST_MODULE_UTILS_DIR
absmoddir=$( readlink -f "$DEST_MODULE_UTILS_DIR" )

# clean up old links to module_utils
for item in "$SRC_MODULE_UTILS_DIR"/* ; do
    if lnitem=$( readlink "$item" ) && test -n "$lnitem" ; then
        case "$lnitem" in
            *"${DEST_MODULE_UTILS_DIR}"*) rm -f "$item" ;;
        esac
    fi
done

# add new links to module_utils
for item in "$absmoddir"/* ; do
    case "$item" in
        *__pycache__) continue;;
        *.pyc) continue;;
        *__init__.py) continue;;
    esac
    bnitem=$( basename "$item" )
    ln -s "$item" "$SRC_MODULE_UTILS_DIR/$bnitem"
done
