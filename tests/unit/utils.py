#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Test utilities."""

from copy import deepcopy

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


class Namespace(object):
    """Attribute container."""


def make_object(**kwargs):
    """Create object with attributes from kwargs."""

    obj = Namespace()
    # pylint: disable=consider-using-dict-items
    for key in kwargs:
        setattr(obj, key, kwargs[key])
    return obj


class MockConfigParser(object):
    """Mock the ConfigParser."""

    # pylint: disable=unused-argument
    def __init__(self, *args, **kwargs):
        """Initialize the ConfigParser mock."""

        self._data = deepcopy(kwargs.get("data", {}))

    def sections(self):
        """Mock the ConfigParser.sections method."""

        return list(self._data.keys())

    def options(self, section):
        """Mock the ConfigParser.options method."""

        return list(self._data[section].keys())

    def has_section(self, section):
        """Mock the ConfigParser.has_section method."""

        return section in self._data

    def has_option(self, section, key):
        """Mock the ConfigParser.has_option method."""

        return key in self._data[section]

    def get(self, section, key):
        """Mock the ConfigParser.get method."""

        return self._data[section][key]


class MockIniSource(object):
    """Mock the IniSource."""

    # pylint: disable=unused-argument
    def __init__(self, *args, **kwargs):
        """Initialize the IniSource mock."""

        self._parser = kwargs.get("parser", None)


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

    # pylint: disable=unused-argument
    def cfg_get_func(self, section, key, default):
        """Mock the self._cfg.get method."""

        return default

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
        self._cfg.get = kwargs.get("cfg_get_func", self.cfg_get_func)
        self.envlist_explicit = Mock()
        self.envconfigs = {}
        self._testenv_attr = Mock()


class MockConfig4(object):
    """Mock tox 4 Config."""

    def __init__(self, **kwargs):
        """Initialize config with kwargs."""
        self._options = kwargs.get("options", None)
        self._src = kwargs.get("config_source", None)


class MockToxParseIni(object):
    def __init__(self, config, ini_path, ini_data):
        """Mock the tox.config.ParseIni constructor."""
        self.config = config
        self.ini_path = ini_path
        self.ini_data = ini_data
