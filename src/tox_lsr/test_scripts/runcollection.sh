#!/bin/bash
# SPDX-License-Identifier: MIT

set -euo pipefail

#uncomment if you use $ME - otherwise set in utils.sh
#ME=$(basename "$0")
SCRIPTDIR=$(readlink -f "$(dirname "$0")")

. "${SCRIPTDIR}/utils.sh"

# Collection commands that are run when `tox -e collection`:
role=$(basename "${TOPDIR}")
STABLE_TAG=${2:-master}
LSR_ROLE2COLL_NAMESPACE="${LSR_ROLE2COLL_NAMESPACE:-fedora}"
LSR_ROLE2COLL_NAME="${LSR_ROLE2COLL_NAME:-linux_system_roles}"
cd "$LSR_TOX_ENV_DIR"
testlist="yamllint,black,flake8,shellcheck"
# py38 - pyunit testing is not yet supported
#testlist="${testlist},py38"

automaintenancerepo=https://raw.githubusercontent.com/linux-system-roles/auto-maintenance/
curl -s -L -o lsr_role2collection.py "${automaintenancerepo}${STABLE_TAG}"/lsr_role2collection.py

python lsr_role2collection.py --src-path "$TOPDIR/.." --dest-path "$LSR_TOX_ENV_DIR" --role "$role" \
  --namespace "${LSR_ROLE2COLL_NAMESPACE}" --collection "${LSR_ROLE2COLL_NAME}" \
  > "$LSR_TOX_ENV_DIR"/collection.out 2>&1

line_length_warning() {
    python -c 'import sys
from configparser import ConfigParser
cfg = ConfigParser()
cfg.read(sys.argv[1])
if "lsr_yamllint" not in cfg:
  cfg["lsr_yamllint"] = {}
cmdline = "sed -i -e \"s/\( *\)\(document-start: disable\)/\\1\\2\\n\\1line-length:\\n\\1\\1level: warning/\" {envtmpdir}/yamllint_defaults.yml"
if "commands_pre" in cfg["lsr_yamllint"]:
  cfg["lsr_yamllint"]["commands_pre"] += "\n" + cmdline
else:
  cfg["lsr_yamllint"]["commands_pre"] = cmdline
cfg.write(open(sys.argv[1], "w"))
' "$1"
}

cd ansible_collections/"${LSR_ROLE2COLL_NAMESPACE}"/"${LSR_ROLE2COLL_NAME}"
# customize yamllint processing - make line-length reporting a warning
if [ ! -f tox.ini ]; then
    touch tox.ini
fi
line_length_warning tox.ini

# unit testing not working yet - will need these and more
#export RUN_PYTEST_UNIT_DIR="$role/unit"
#export PYTHONPATH="$LSR_TOX_ENV_DIR/ansible_collections/"${LSR_ROLE2COLL_NAME}"/"${LSR_ROLE2COLL_NAME}"/plugins/modules:$LSR_TOX_ENV_DIR/ansible_collections/"${LSR_ROLE2COLL_NAME}"/"${LSR_ROLE2COLL_NAME}"/plugins/module_utils"
tox -e "$testlist" 2>&1 | tee "$LSR_TOX_ENV_DIR"/collection.tox.out || :

rm -rf "${LSR_TOX_ENV_DIR}"/auto-maintenance "$LSR_TOX_ENV_DIR"/ansible_collections
cd "${TOPDIR}"
res=$( grep "^ERROR: .*failed" "$LSR_TOX_ENV_DIR"/collection.tox.out || : )
if [ "$res" != "" ]; then
    lsr_error "${ME}: tox in the converted collection format failed."
    exit 1
fi
