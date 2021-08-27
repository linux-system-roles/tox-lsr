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

testlist="yamllint,flake8,shellcheck"
# py38 - pyunit testing is not yet supported
#testlist="${testlist},py38"

automaintenancerepo=https://raw.githubusercontent.com/linux-system-roles/auto-maintenance/
curl -s -L -o "$LSR_TOX_ENV_DIR/tmp/lsr_role2collection.py" "${automaintenancerepo}${STABLE_TAG}"/lsr_role2collection.py
curl -s -L -o "$LSR_TOX_ENV_DIR/tmp/runtime.yml" "${automaintenancerepo}${STABLE_TAG}"/lsr_role2collection/runtime.yml

rm -rf "$TOX_WORK_DIR/ansible_collections"
python "$LSR_TOX_ENV_DIR/tmp/lsr_role2collection.py" --src-path "$TOPDIR/.." --dest-path "$TOX_WORK_DIR" \
  --role "$role" --namespace "${LSR_ROLE2COLL_NAMESPACE}" --collection "${LSR_ROLE2COLL_NAME}" \
  --meta-runtime "$LSR_TOX_ENV_DIR/tmp/runtime.yml" \
  2>&1 | tee "$TOX_ENV_DIR/collection.out"

# create the collection in this dir to share with other testenvs
cd "$TOX_WORK_DIR/ansible_collections/$LSR_ROLE2COLL_NAMESPACE/$LSR_ROLE2COLL_NAME"

# unit testing not working yet - will need these and more
#export RUN_PYTEST_UNIT_DIR="$role/unit"
#export PYTHONPATH="$MY_LSR_TOX_ENV_DIR/ansible_collections/"${LSR_ROLE2COLL_NAME}"/"${LSR_ROLE2COLL_NAME}"/plugins/modules:$MY_LSR_TOX_ENV_DIR/ansible_collections/"${LSR_ROLE2COLL_NAME}"/"${LSR_ROLE2COLL_NAME}"/plugins/module_utils"
RUN_YAMLLINT_CONFIG_FILE="$LSR_CONFIGDIR/collection_yamllint.yml" \
TOXENV="" tox --workdir "$TOXINIDIR/.tox" -e "$testlist" 2>&1 | tee "$TOX_ENV_DIR/collection.tox.out" || :

if grep "^ERROR: .*failed" "$TOX_ENV_DIR/collection.tox.out"; then
  lsr_error "${ME}: Some tests failed when run against the converted collection.
  This usually indicates either a problem with the collection conversion,
  or additional error suppressions are needed."
fi

# ansible-test needs meta data
curl -s -L -o galaxy.yml "${automaintenancerepo}${STABLE_TAG}/galaxy.yml"

exit 0
