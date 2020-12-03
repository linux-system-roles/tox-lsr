#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Type annotations for tox.config."""

from typing import List, Mapping, Set

from py import iniconfig

testenvprefix: str

class TestenvConfig(object):
    envname: str
    # pylint: disable=used-before-assignment
    config: Config  # noqa: F821 - it is defined below
    factors: Set[str]
    whitelist_externals: List[str]

class Config(object):  # noqa: H238
    _cfg: iniconfig.IniConfig
    envlist: List[str]
    envlist_default: List[str]
    envlist_explicit: bool
    envconfigs: Mapping[str, TestenvConfig]
    toxworkdir: str

class ParseIni(object):
    _cfg: iniconfig.IniConfig
    config: Config

# pylint: disable=invalid-name
class parseini(ParseIni):
    pass

class Parser(object):
    _testenv_attr: List[str]
