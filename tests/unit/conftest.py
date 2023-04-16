#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""
pytest configuration.

Mock tox module so unit tests will run both for tox 3 and tox 4. Based on
https://stackoverflow.com/questions/43162722/mocking-a-module-import-in-pytest
"""

# pylint: disable=no-member

import sys


def dummy_hook(*args, **unused_kwargs):
    """
    Implement dummy pluggy.HookimplMarker.

    Make unit tests pass for both tox 3 and tox 4.
    """
    if not args:
        # Called with kwargs only, like @impl(tryfirst=...). The next call will
        # have decorated function as the first argument so return itself:
        return dummy_hook
    # Return decorated function:
    return args[0]


tox = type(sys)("tox")
tox.hookimpl = dummy_hook

tox.config = type(sys)("config")
tox.config.Parser = None  # will be mocked
tox.config.Config = None  # will be mocked
tox.config.TestenvConfig = None  # will be mocked
tox.config.testenvprefix = "testenv:"
tox.config.ParseIni = None  # will be mocked

tox.config.loader = type(sys)("loader")
tox.config.loader.ini = type(sys)("ini")
tox.config.loader.ini.IniLoader = None  # will be mocked

tox.plugin = type(sys)("plugin")
tox.plugin.impl = dummy_hook

sys.modules["tox"] = tox
sys.modules["tox.config"] = tox.config
sys.modules["tox.config.loader"] = tox.config.loader
sys.modules["tox.config.loader.ini"] = tox.config.loader.ini
sys.modules["tox.plugin"] = tox.plugin
