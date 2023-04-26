#!/bin/bash
# SPDX-License-Identifier: MIT

# Do not exit on an error to continue ansible-doc and ansible-test.
set -euo pipefail

#uncomment if you use $ME - otherwise set in utils.sh
#ME=$(basename "$0")
SCRIPTDIR=$(readlink -f "$(dirname "$0")")

. "${SCRIPTDIR}/utils.sh"

if ! type -p npm > /dev/null 2>&1; then
  lsr_info "${ME}: on Fedora try 'dnf -y install npm'"
  lsr_error "${ME}: npm command not found"
fi

pushd "$LSR_TOX_ENV_DIR"
npm install @commitlint/config-conventional @commitlint/cli

cp "$LSR_CONFIGDIR/commitlint.config.js" ./

npx commitlint --from origin/HEAD \
    --to $(git rev-parse --abbrev-ref HEAD) --verbose
popd
