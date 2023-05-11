#!/bin/bash
# SPDX-License-Identifier: MIT

# Do not exit on an error to continue ansible-doc and ansible-test.
set -euo pipefail

#uncomment if you use $ME - otherwise set in utils.sh
#ME=$(basename "$0")
SCRIPTDIR=$(readlink -f "$(dirname "$0")")

. "${SCRIPTDIR}/utils.sh"

# Collection commands that are run when `tox -e collection`:
role=$(basename "${TOPDIR}")
STABLE_TAG=${1:-master}

testlist="yamllint,flake8,shellcheck,ansible-plugin-scan"
# py38 - pyunit testing is not yet supported
#testlist="${testlist},py38"

if [ -z "${LSR_ROLE2COLL_PATH:-}" ]; then
  automaintenancerepo=https://raw.githubusercontent.com/linux-system-roles/auto-maintenance/
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
  2>&1 | tee "$TOX_ENV_DIR/collection.out"

cp "$LSR_TOX_ENV_DIR/tmp/galaxy.yml" "$TOX_WORK_DIR/ansible_collections/$LSR_ROLE2COLL_NAMESPACE/$LSR_ROLE2COLL_NAME"

# create the collection in this dir to share with other testenvs
cd "$TOX_WORK_DIR/ansible_collections/$LSR_ROLE2COLL_NAMESPACE/$LSR_ROLE2COLL_NAME"

# these are for ansible-lint
cp "$LSR_CONFIGDIR/collection_yamllint.yml" \
  "$TOX_WORK_DIR/ansible_collections/$LSR_ROLE2COLL_NAMESPACE/$LSR_ROLE2COLL_NAME/.yamllint.yml"
touch "$TOX_WORK_DIR/ansible_collections/$LSR_ROLE2COLL_NAMESPACE/$LSR_ROLE2COLL_NAME/CHANGELOG.md"

# unit testing not working yet - will need these and more
#export RUN_PYTEST_UNIT_DIR="$role/unit"
#export PYTHONPATH="$MY_LSR_TOX_ENV_DIR/ansible_collections/"${LSR_ROLE2COLL_NAME}"/"${LSR_ROLE2COLL_NAME}"/plugins/modules:$MY_LSR_TOX_ENV_DIR/ansible_collections/"${LSR_ROLE2COLL_NAME}"/"${LSR_ROLE2COLL_NAME}"/plugins/module_utils"
RUN_YAMLLINT_CONFIG_FILE="$LSR_CONFIGDIR/collection_yamllint.yml" \
RUN_PLUGIN_SCAN_EXTRA_ARGS="--check-fqcn=plugins" \
LSR_RUN_TEST_DIR="$TOX_WORK_DIR/ansible_collections/$LSR_ROLE2COLL_NAMESPACE/$LSR_ROLE2COLL_NAME" \
TOXENV="" tox --workdir "$TOXINIDIR/.tox" -e "$testlist" 2>&1 | tee "$TOX_ENV_DIR/collection.tox.out" || :

if grep "^ERROR: .*failed" "$TOX_ENV_DIR/collection.tox.out"; then
  lsr_error "${ME}: Some tests failed when run against the converted collection.
  This usually indicates either a problem with the collection conversion,
  or additional error suppressions are needed."
fi

exit 0
