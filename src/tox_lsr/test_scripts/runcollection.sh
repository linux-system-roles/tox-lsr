#!/bin/bash
# SPDX-License-Identifier: MIT

# Do not exit on an error to continue ansible-doc and ansible-test.
set -euo pipefail

#uncomment if you use $ME - otherwise set in utils.sh
#ME=$(basename "$0")
SCRIPTDIR=$(readlink -f "$(dirname "$0")")

. "${SCRIPTDIR}/utils.sh"

if [ "${LSR_ROLE2COLL_DEBUG:-false}" = true ]; then
  set -x
  export LSR_DEBUG=true
fi
# Collection commands that are run when `tox -e collection`:
STABLE_TAG=${LSR_ROLE2COLL_VERSION:-main}
if [ "$#" -gt 0 ] && [[ "$1" != --* ]]; then
  STABLE_TAG="$1"
  shift
fi
mode=--current-role
mode_set=false
for arg in "$@"; do
  case "$arg" in
    --current-role|--full|--clear)
      if [ "$mode_set" = true ] && [ "$mode" != "$arg" ]; then
        echo "Specify only one collection mode" >&2
        exit 2
      fi
      mode="$arg"
      mode_set=true
      ;;
    *)
      echo "Unknown collection argument: $arg" >&2
      exit 2
      ;;
  esac
done

if [ "$mode" = --clear ]; then
  rm -rf "$TOX_WORK_DIR/ansible_collections/$LSR_ROLE2COLL_NAMESPACE"
  exit 0
fi

testlist="yamllint,flake8,shellcheck,ansible-plugin-scan"
# py38 - pyunit testing is not yet supported
#testlist="${testlist},py38"

seed_from_cache=false
if [ "$mode" = --full ]; then
  python "$SCRIPTDIR/collection-cache.py" --collection \
    "$LSR_ROLE2COLL_NAMESPACE.$LSR_ROLE2COLL_NAME"
  seed_from_cache=true
fi
LSR_ROLE2COLL_VERSION="$STABLE_TAG" bash "$SCRIPTDIR/prepare-local-collection.sh" \
  "$TOPDIR" "$TOX_WORK_DIR" "${LSR_COLLECTIONS_CACHE:-$HOME/.cache/linux-system-roles}" \
  "$seed_from_cache" 2>&1 | tee "$TOX_ENV_DIR/collection.out"

coll_path="$TOX_WORK_DIR/ansible_collections/$LSR_ROLE2COLL_NAMESPACE/$LSR_ROLE2COLL_NAME"

# create the collection in this dir to share with other testenvs
cd "$coll_path"

# unit testing not working yet - will need these and more
#export RUN_PYTEST_UNIT_DIR="$role/unit"
#export PYTHONPATH="$MY_LSR_TOX_ENV_DIR/ansible_collections/"${LSR_ROLE2COLL_NAME}"/"${LSR_ROLE2COLL_NAME}"/plugins/modules:$MY_LSR_TOX_ENV_DIR/ansible_collections/"${LSR_ROLE2COLL_NAME}"/"${LSR_ROLE2COLL_NAME}"/plugins/module_utils"
RUN_YAMLLINT_CONFIG_FILE="$LSR_CONFIGDIR/collection_yamllint.yml" \
RUN_PLUGIN_SCAN_EXTRA_ARGS="--check-fqcn=plugins" \
LSR_RUN_TEST_DIR="$coll_path" TOXENV="" tox --workdir "$TOXINIDIR/.tox" -e "$testlist" 2>&1 | \
  tee "$TOX_ENV_DIR/collection.tox.out" || :

if grep "^ERROR: .*failed" "$TOX_ENV_DIR/collection.tox.out"; then
  lsr_error "${ME}: Some tests failed when run against the converted collection.
  This usually indicates either a problem with the collection conversion,
  or additional error suppressions are needed."
fi

exit 0
