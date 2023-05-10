#!/bin/bash

set -euo pipefail

#uncomment if you use $ME - otherwise set in utils.sh
#ME=$(basename "$0")
SCRIPTDIR=$(readlink -f "$(dirname "$0")")

. "${SCRIPTDIR}/utils.sh"

if grep -EIlr -e "{{ ansible_managed }}" -e "# {{ ansible_managed" ./*; then
  echo In the above files, the ansible_managed variable must be commented with '"{{ ansible_managed | comment }}"' as described in https://docs.ansible.com/ansible/latest/user_guide/playbooks_filters.html#manipulating-text
  exit 1
fi
