#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Install tox-lsr hooks to tox."""

from tox import hookimpl
from tox.config import Config


# Run this hook *after* any other tox_configure hook, especially the tox-travis
# one.
@hookimpl(trylast=True)
def tox_configure(config: Config) -> None:
    """Adjust tox configuration right after it is loaded."""

    config.envlist.sort()
