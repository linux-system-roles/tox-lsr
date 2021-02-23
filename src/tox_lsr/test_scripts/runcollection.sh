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
STABLE_TAG=${2:-master}
export LSR_ROLE2COLL_NAMESPACE="${LSR_ROLE2COLL_NAMESPACE:-fedora}"
export LSR_ROLE2COLL_NAME="${LSR_ROLE2COLL_NAME:-linux_system_roles}"

# Since .tox is in .gitignore, ansible-test is skipped
# if the collection path is in LSR_TOX_ENV_DIR.
# Using a temp dir outside of .tox.
export MY_LSR_TOX_ENV_DIR=$( mktemp -d -t tox-XXXXXXXX )
trap "rm -rf ${MY_LSR_TOX_ENV_DIR}" 0
cd "$MY_LSR_TOX_ENV_DIR"
testlist="yamllint,flake8,shellcheck"
# py38 - pyunit testing is not yet supported
#testlist="${testlist},py38"

automaintenancerepo=https://raw.githubusercontent.com/linux-system-roles/auto-maintenance/
curl -s -L -o lsr_role2collection.py "${automaintenancerepo}${STABLE_TAG}"/lsr_role2collection.py

python lsr_role2collection.py --src-path "$TOPDIR/.." --dest-path "$MY_LSR_TOX_ENV_DIR" --role "$role" \
  --namespace "${LSR_ROLE2COLL_NAMESPACE}" --collection "${LSR_ROLE2COLL_NAME}" \
  2>&1 | tee "$MY_LSR_TOX_ENV_DIR"/collection.out

cd ansible_collections/"${LSR_ROLE2COLL_NAMESPACE}"/"${LSR_ROLE2COLL_NAME}"

# unit testing not working yet - will need these and more
#export RUN_PYTEST_UNIT_DIR="$role/unit"
#export PYTHONPATH="$MY_LSR_TOX_ENV_DIR/ansible_collections/"${LSR_ROLE2COLL_NAME}"/"${LSR_ROLE2COLL_NAME}"/plugins/modules:$MY_LSR_TOX_ENV_DIR/ansible_collections/"${LSR_ROLE2COLL_NAME}"/"${LSR_ROLE2COLL_NAME}"/plugins/module_utils"
RUN_YAMLLINT_CONFIG_FILE="$LSR_CONFIGDIR/collection_yamllint.yml" \
tox --workdir "$TOXINIDIR/.tox" -e "$testlist" 2>&1 | tee "$MY_LSR_TOX_ENV_DIR"/collection.tox.out || :

rval=0
if [ "${LSR_ROLE2COLL_RUN_ANSIBLE_TESTS:-}" = "true" ]; then
    # ansible-test needs meta data
    curl -s -L -o galaxy.yml "${automaintenancerepo}${STABLE_TAG}"/galaxy.yml
    if ! ${SCRIPTDIR}/runansible-doc.sh; then
        rval=1
    fi
    if ! ${SCRIPTDIR}/runansible-test.sh; then
        rval=1
    fi
fi

cd "${TOPDIR}"
res=$( grep "^ERROR: .*failed" "$MY_LSR_TOX_ENV_DIR"/collection.tox.out || : )
if [ "$res" != "" -o $rval -ne 0 ]; then
    lsr_error "${ME}: tox in the converted collection format failed."
    exit 1
fi
