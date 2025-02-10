#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Type annotations for tox.config.loader.ini."""

from typing import List

from configparser import ConfigParser
from tox.config.loader import Section, Loader, Override

class IniLoader(Loader):
    _parser: ConfigParser
    core_section: Section

    # pylint: disable=too-many-arguments,unknown-option-value,too-many-positional-arguments
    def __init__(
        self,
        section: Section,
        parser: ConfigParser,
        overrides: List[Override],
        core_section: Section,
        section_key: str,
    ) -> None: ...
