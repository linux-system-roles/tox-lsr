#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Type annotations for tox.config.source."""

from configparser import ConfigParser
from typing import Dict, List

from tox.config.loader import Loader, Section

class Source:
    _section_to_loaders: Dict[str, List[Loader]]

class IniSource(Source):
    _parser: ConfigParser

    def get_core_section(self) -> Section: ...
