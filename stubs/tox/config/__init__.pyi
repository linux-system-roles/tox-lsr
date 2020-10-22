#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Type annotations for tox.config."""

from typing import List

from py import iniconfig

class Config:  # noqa: H238
    _cfg: iniconfig.IniConfig
    envlist: List[str]
