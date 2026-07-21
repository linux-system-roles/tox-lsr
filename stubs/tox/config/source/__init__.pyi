#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Type annotations for tox.config.source."""

from configparser import ConfigParser
from typing import Dict, List, Mapping, Optional

from tox.config.loader import Loader, Override, Section

class Source:
    # Present on tox < 4.58; removed when loaders became on-demand.
    _section_to_loaders: Dict[str, List[Loader]]

class IniSource(Source):
    _parser: ConfigParser

    def get_core_section(self) -> Section: ...

    def get_loader(
        self, section: Section, override_map: Mapping[str, List[Override]]
    ) -> Optional[Loader]: ...
