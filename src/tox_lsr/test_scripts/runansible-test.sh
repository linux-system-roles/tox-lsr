#!/bin/bash
# SPDX-License-Identifier: MIT

# A shell wrapper around ansible-test.

set -euo pipefail

ME=$(basename "$0")
SCRIPTDIR=$(readlink -f "$(dirname "$0")")

. "$SCRIPTDIR/utils.sh"

if [ -z "${LSR_ROLE2COLL_NAMESPACE:-}" ] || [ -z "${LSR_ROLE2COLL_NAME:-}" ]; then
  lsr_info "${ME}: Collection format only."
  exit 1
fi

if ! ansible_test=$(type -p ansible-test) || [ -z "${ansible_test:-}" ]; then
  lsr_error "${ME}: ansible-test not found"
fi

src_ac_dir="$TOX_WORK_DIR/ansible_collections"
src_coll_dir="$src_ac_dir/$LSR_ROLE2COLL_NAMESPACE/$LSR_ROLE2COLL_NAME"
if [ ! -d "$src_coll_dir" ]; then
  lsr_error "${ME}: There is no collection at $src_coll_dir.  Please run 'tox -e collection' first."
fi

if [ "${LSR_ANSIBLE_TEST_DEBUG:-false}" = true ]; then
  truncate_flag="--truncate"
  truncate_val="0"
  default_v_arg="-vv"
  ansible_test_filter() {
    cat
  }
  set -x
else
  default_v_arg=""
  ansible_test_filter() {
    grep -v '^Requirement already satisfied' | grep -v '^Ignoring '
  }
fi

# We cannot run ansible-test directly against the collection in .tox from a git cloned
# repo.  ansible-test will look for the .git directory in all parent directories - if
# it finds this, it will use the equivalent of `git ls-files` which will not only
# exclude .tox but will include files that we do not want to test.  There is no apparent
# way to disable this "feature".
# We assume the `collection` testenv has already run and placed the collection in
# toxworkdir/ansible_collections - so we copy this to a tempdir in order to run
# ansible-test against it
dest_coll_dir=$(mktemp -d -t tox-XXXXXXXX)
# shellcheck disable=SC2064
trap "rm -rf $dest_coll_dir" 0
cp -a "$src_ac_dir" "$dest_coll_dir"

cd "$dest_coll_dir/ansible_collections/$LSR_ROLE2COLL_NAMESPACE/$LSR_ROLE2COLL_NAME"

if [ "${LSR_ANSIBLE_TEST_DOCKER:-false}" = true ]; then
  ansible-test sanity --docker 2>&1 | ansible_test_filter
  exit 0
fi

# remove the current venv from PATH
if [ -n "${VIRTUAL_ENV:-}" ] && [[ "${PATH}" == "${VIRTUAL_ENV:-}/bin:"* ]]; then
  PATH="${PATH##$VIRTUAL_ENV/bin:}:$VIRTUAL_ENV/bin"
fi
# use tox to set up 2.7 env - otherwise on platforms like F33, there is no
# native venv or virtualenv package - the only way to get a python 2.7
# virtual env is to use tox which seems smart enough to create one somehow
cat > tox-py27.ini <<EOF
[tox]
envlist = ansible-test-py-hack
skipsdist = true
skip_missing_interpreters = true

[testenv:ansible-test-py-hack]
basepython = python2.7
deps = virtualenv
EOF
TOXENV="" tox --workdir "$TOXINIDIR/.tox" -c tox-py27.ini
. "$TOXINIDIR/.tox/ansible-test-py-hack/bin/activate"

# ansible-test doesn't clean up after itself . . .
export TMPDIR="$dest_coll_dir"
#env
rval=0
LSR_ANSIBLE_TEST_TESTS="${LSR_ANSIBLE_TEST_TESTS:-$(ansible-test sanity --list-tests)}"
for test in $LSR_ANSIBLE_TEST_TESTS; do
  lsr_info "${ME}: Running $test ..."
  v_arg="$default_v_arg"
  if [ "$test" = ansible-doc ]; then
    v_arg="${LSR_ANSIBLE_DOC_DEBUG:-}"
  fi
  # https://github.com/koalaman/shellcheck/wiki/SC2086
  # shellcheck disable=SC2086
  if ! "$ansible_test" sanity ${truncate_flag:-} ${truncate_val:-} $v_arg --requirements --test "$test" \
          --color no --venv 2>&1 | ansible_test_filter ; then
    rval=1
  fi
done
deactivate
exit "$rval"
