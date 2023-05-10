#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Type annotations for tox.config."""

from typing import List, Mapping, Set, MutableMapping, Optional
from pathlib import Path

from py import iniconfig

from pluggy import PluginManager

from tox.config.source import Source
from tox.config.loader import Loader, Override

testenvprefix: str

class Parser(object):
    _testenv_attr: List[str]

    # pylint: disable=too-many-arguments
    def add_argument(
        self,
        name: str,
        dest: str,
        action: str,
        help: str,  # pylint: disable=redefined-builtin
        default: object,
    ) -> None: ...

class Parsed:
    workdir: str
    skip_missing_interpreters: bool

class SetenvDict:
    def __contains__(self, name: str) -> bool: ...
    def __getitem__(self, name: str) -> str: ...
    def __setitem__(self, name: str, value: str) -> None: ...
    def keys(self) -> List[str]: ...

class ConfigSet:
    loaders: List[Loader]

class CoreConfigSet(ConfigSet):
    _root: Path

class SectionReader:
    _cfg: iniconfig.IniConfig

class TestenvConfig(object):
    _reader: SectionReader
    envname: str
    setenv: SetenvDict
    # pylint: disable=used-before-assignment
    config: Config  # noqa: F821 - it is defined below
    factors: Set[str]
    deps: List[str]
    passenv: Set[str]
    allowlist_externals: List[str]

class Config(object):  # noqa: H238
    # tox 4
    _src: Source
    # tox 4
    _overrides: MutableMapping[str, List[Override]]
    _cfg: iniconfig.IniConfig
    _parser: Parser
    # tox 4
    _options: Parsed
    option: Parsed
    envlist: List[str]
    envlist_default: List[str]
    envlist_explicit: bool
    envconfigs: MutableMapping[str, TestenvConfig]
    toxinipath: str
    toxworkdir: str
    pluginmanager: PluginManager
    interpreters: List[str]
    _testenv_attr: List[str]

    # pylint: disable=too-many-arguments
    def __init__(
        self,
        pluginmanager: PluginManager,
        option: Parsed,
        interpreters: List[str],
        parser: Optional[Parser] = None,
        args: Optional[List[str]] = None,
    ) -> None: ...

class ParseIni(object):
    _cfg: iniconfig.IniConfig
    config: Config

    def __init__(
        self,
        config: Config,
        ini_path: str,
        ini_data: Optional[str] = None,
    ) -> None: ...

# pylint: disable=invalid-name
class parseini(ParseIni):
    pass
