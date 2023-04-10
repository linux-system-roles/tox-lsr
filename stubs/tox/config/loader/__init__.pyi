#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Type annotations for tox.config.loader."""

from typing import Dict

class Section:
    key: str

class Override:
    namespace: str
    key: str
    value: str

class Loader:
    overrides: Dict[str, Override]
