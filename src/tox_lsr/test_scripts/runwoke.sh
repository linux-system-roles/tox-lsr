#!/bin/bash
# SPDX-License-Identifier: MIT

# Do not exit on an error to continue ansible-doc and ansible-test.
set -euo pipefail

#uncomment if you use $ME - otherwise set in utils.sh
#ME=$(basename "$0")
SCRIPTDIR=$(readlink -f "$(dirname "$0")")

. "${SCRIPTDIR}/utils.sh"

curl -sSfL https://git.io/getwoke | bash -s -- -b "$LSR_TOX_ENV_DIR/bin"
WOKE_CMD="$LSR_TOX_ENV_DIR/bin/woke"
WOKE_OUT="$LSR_TOX_ENV_DIR/tmp/woke_output.txt"

"$WOKE_CMD" -c "$LSR_CONFIGDIR/woke.yml" > "$WOKE_OUT" 2>&1 || :

if grep 'instead (error)' "$WOKE_OUT" 2>&1 /dev/null ; then
  cat "$WOKE_OUT"
  lsr_error "${ME}: Conscious language violation was reported."
fi
exit 0
