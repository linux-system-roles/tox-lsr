#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
# Copyright (c) 2022 Red Hat, Inc.
#
# Check that versions are string in meta/main.yml
"""Check that versions are string in meta/main.yml."""

import os

import yaml

meta_main = os.path.join("meta", "main.yml")
if not os.path.exists(meta_main):
    raise Exception(f"meta file {meta_main} does not exist")

hsh = yaml.safe_load(open(meta_main))
errs = []
min_ans_ver = hsh["galaxy_info"].get("min_ansible_version", "not found")
if not isinstance(min_ans_ver, str):
    errs.append(
        f"in {meta_main}: min_ansible_version is not a string: {min_ans_ver}"
    )
# need to fix all roles to use string versions for platforms
# for platform in hsh["galaxy_info"]["platforms"]:
#     for ver in platform["versions"]:
#         if not isinstance(ver, str):
#             errs.append(
#                 f"ERROR: platform {platform['name']} "
#                 f"version is not a string: {ver}"
#             )

if errs:
    raise Exception(" - ".join(errs))
