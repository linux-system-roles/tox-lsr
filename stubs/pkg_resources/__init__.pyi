#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Type annotations for pkg_resources."""

def resource_filename(package_or_requirement: str, resource_name: str) -> str: ...
def resource_string(package_or_requirement: str, resource_name: str) -> bytes: ...
