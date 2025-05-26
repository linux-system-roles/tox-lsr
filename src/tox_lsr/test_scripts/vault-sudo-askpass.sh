#!/bin/sh
# `sudo -A` ($SUDO_ASKPASS) script that gets the value of `sudo_password` from
# the vault, as described in ./README.md
set -eu
# we need the tail to strip off the "localhost | CHANGED .." summary
ansible localhost -m command -a 'echo {{ sudo_password }}' -e '@vars/vault-variables.yml' --vault-password-file vault_pwd | tail -n1
