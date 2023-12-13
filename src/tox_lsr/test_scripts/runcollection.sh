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
role=$(basename "${TOPDIR}")
STABLE_TAG=${1:-main}

testlist="yamllint,flake8,shellcheck,ansible-plugin-scan"
# py38 - pyunit testing is not yet supported
#testlist="${testlist},py38"

if [ -z "${LSR_ROLE2COLL_PATH:-}" ]; then
  automaintenancerepo=https://raw.githubusercontent.com/${LSR_SRC_OWNER}/auto-maintenance/
  curl -s -L -o "$LSR_TOX_ENV_DIR/tmp/lsr_role2collection.py" "${automaintenancerepo}${STABLE_TAG}"/lsr_role2collection.py
  curl -s -L -o "$LSR_TOX_ENV_DIR/tmp/runtime.yml" "${automaintenancerepo}${STABLE_TAG}"/lsr_role2collection/runtime.yml
  # ansible-test needs meta data
  curl -s -L -o "$LSR_TOX_ENV_DIR/tmp/galaxy.yml" "${automaintenancerepo}${STABLE_TAG}"/galaxy.yml
else
  cp "$LSR_ROLE2COLL_PATH/lsr_role2collection.py" "$LSR_TOX_ENV_DIR/tmp"
  cp "$LSR_ROLE2COLL_PATH/lsr_role2collection/runtime.yml" "$LSR_TOX_ENV_DIR/tmp"
  cp "$LSR_ROLE2COLL_PATH/galaxy.yml" "$LSR_TOX_ENV_DIR/tmp"
fi

rm -rf "$TOX_WORK_DIR/ansible_collections"
python "$LSR_TOX_ENV_DIR/tmp/lsr_role2collection.py" --src-path "$TOPDIR/.." --dest-path "$TOX_WORK_DIR" \
  --role "$role" --namespace "${LSR_ROLE2COLL_NAMESPACE}" --collection "${LSR_ROLE2COLL_NAME}" \
  --meta-runtime "$LSR_TOX_ENV_DIR/tmp/runtime.yml" --subrole-prefix "private_${role}_subrole_" \
  --src-owner "$LSR_SRC_OWNER" 2>&1 | tee "$TOX_ENV_DIR/collection.out"

coll_path="$TOX_WORK_DIR/ansible_collections/$LSR_ROLE2COLL_NAMESPACE/$LSR_ROLE2COLL_NAME"
cp "$LSR_TOX_ENV_DIR/tmp/galaxy.yml" "$coll_path"

# create the collection in this dir to share with other testenvs
cd "$coll_path"

# these are for ansible-lint
cp "$LSR_CONFIGDIR/collection_yamllint.yml" "$coll_path/.yamllint.yml"
touch "$coll_path/CHANGELOG.md"
if [ -f "$TOXINIDIR"/.ansible-lint ]; then
  cp "$TOXINIDIR"/.ansible-lint "$coll_path"
fi

# grab our ignore files
for file in "$TOXINIDIR"/.sanity-ansible-ignore-*.txt; do
  if [ -f "$file" ]; then
    if [ ! -d tests/sanity ]; then
      mkdir -p tests/sanity
    fi
    cp "$file" "tests/sanity/${file//*.sanity-ansible-}"
  fi
done

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
