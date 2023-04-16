#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Install tox-lsr hooks to tox."""

# pylint: disable=unused-import

from tox.version import __version__

if int(__version__.split(".")[0]) < 4:  # pylint: disable=use-maxsplit-arg
    from .hooks3 import tox_addoption, tox_configure  # noqa: F401

else:
    from .hooks4 import tox_add_core_config, tox_add_option  # noqa: F401
