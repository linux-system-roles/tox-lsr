#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Install tox-lsr hooks to tox."""

from tox.version import __version__

if int(__version__.split(".")[0]) < 4:  # pylint: disable=use-maxsplit-arg
    from .hooks3 import setup

else:
    from .hooks4 import setup


setup()
