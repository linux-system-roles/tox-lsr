#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Test utilities."""
try:
    from unittest.mock import Mock
except ImportError:
    from mock import Mock

# I have no idea why pylint complains about this.  This works:
# command = python -c 'import py; print(dir(py.path))'
# bug in pylint?  anyway, just ignore it
# in addition - pylint does not allow me to disable it
# on the same line, so I have to disable it before the line
# pylint: disable=no-member
import py


# mocks the tox.config.Config class
class MockConfig(object):
    # pylint: disable=too-many-instance-attributes
    __slots__ = (
        "_parser",
        "_testenv_attr",
        "pluginmanager",
        "option",
        "interpreters",
        "toxworkdir",
        "args",
        "toxinipath",
        "toxinidir",
        "_cfg",
        "envlist_explicit",
        "envconfigs",
    )

    def __init__(self, *args, **kwargs):
        """Mock the tox.config.Config constructor."""

        if len(args) > 0:
            self.option = args[0]
        else:
            self.option = Mock()
        if len(args) > 1:
            self.pluginmanager = args[1]
        else:
            self.pluginmanager = Mock()
        if len(args) > 2:
            self.interpreters = args[2]
        else:
            self.interpreters = Mock()
        if len(args) > 3:
            self._parser = args[3]
        else:
            self._parser = Mock()
        if len(args) > 4:
            self.args = args[4]
        else:
            self.args = Mock()
        if "toxworkdir" in kwargs:
            self.toxworkdir = kwargs["toxworkdir"]
            self.toxinipath = py.path.local(self.toxworkdir)
        self._cfg = Mock()
        self._cfg.sections = {}
        self._cfg.sections["tox"] = {}
        self.envlist_explicit = Mock()
        self.envconfigs = {}
        self._testenv_attr = Mock()


class MockToxParseIni(object):
    def __init__(self, config, ini_path, ini_data):
        """Mock the tox.config.ParseIni constructor."""
        self.config = config
        self.ini_path = ini_path
        self.ini_data = ini_data
