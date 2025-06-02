#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Tests for tox 4 tox_lsr hooks."""

# pylint: disable=protected-access

from copy import deepcopy

try:
    from unittest2 import TestCase
except ImportError:
    from unittest import TestCase
except AttributeError:
    from unittest import TestCase

try:
    from unittest.mock import patch
except ImportError:
    from mock import patch

from tox_lsr.hooks4 import tox_add_core_config, tox_add_option

from .utils import (
    MockArgumentParser,
    MockConfigParser,
    MockCoreConfigSet,
    MockIniLoader,
    MockIniSource,
    MockState,
)

DEFAULT_INI = {
    "tox": {
        "envlist": "py{27,36,37,38,39,310,311,312,313}, black, pylint, flake8",
        "skip_missing_interpreters": "true",
    },
    "testenv": {
        "basepython": "python3",
        "passenv": "*",
        "setenv": (
            "\nLC_ALL = C.UTF-8"
            "\nLSR_ROLE2COLL_VERSION = main"
            "\nLSR_ROLE2COLL_NAMESPACE = fedora"
            "\nLSR_ROLE2COLL_NAME = linux_system_roles"
            "\nLSR_SCRIPTDIR = {lsr_scriptdir}"
            "\nLSR_CONFIGDIR = {lsr_configdir}"
        ),
        "deps": ("\npytest" "\nPyYAML" "\ncolorama"),
        "allowlist_externals": ("\nbash" "\ntouch" "\nfind"),
        "command": "pytest tests/unit",
    },
    "testenv:py36": {
        "basepython": "python3.6",
    },
}
TOX_INI_MISSING_TOX_SECTION = {
    "lsr_black": {
        "configfile": "{lsr_configdir}/myconfig.cfg",
    },
}
TOX_INI_MISSING_TOX_SECTION_MERGED = {
    "tox": {
        "envlist": "py{27,36,37,38,39,310,311,312,313}, black, pylint, flake8",
        "skip_missing_interpreters": "true",
    },
    "testenv": {
        "basepython": "python3",
        "passenv": "*",
        "setenv": (
            "\nLC_ALL = C.UTF-8"
            "\nLSR_ROLE2COLL_VERSION = main"
            "\nLSR_ROLE2COLL_NAMESPACE = fedora"
            "\nLSR_ROLE2COLL_NAME = linux_system_roles"
            "\nLSR_SCRIPTDIR = ./scripts"
            "\nLSR_CONFIGDIR = ./config"
        ),
        "deps": ("\npytest" "\nPyYAML" "\ncolorama"),
        "allowlist_externals": ("\nbash" "\ntouch" "\nfind"),
        "command": "pytest tests/unit",
    },
    "testenv:py36": {
        "basepython": "python3.6",
    },
    "lsr_black": {
        "configfile": "./config/myconfig.cfg",
    },
}
TOX_INI_OVERRIDE_DEFAULTS = {
    "tox": {
        "skip_missing_interpreters": "false",
        "skipsdist": "true",
    },
    "testenv": {
        "setenv": "\nLSR_SCRIPTDIR = {lsr_scriptdir}/../../my_scripts",
        "deps": ("\nblack" "\npylint"),
        "allowlist_externals": ("\nexpect" "\nsed" "\ngrep"),
        "command": "pytest tests/unit {posargs}",
    },
    "lsr_black": {
        "configfile": "{lsr_configdir}/myconfig.cfg",
    },
}
TOX_INI_OVERRIDE_DEFAULTS_MERGED = {
    "tox": {
        "envlist": "py{27,36,37,38,39,310,311,312,313}, black, pylint, flake8",
        "skip_missing_interpreters": "false",
        "skipsdist": "true",
    },
    "testenv": {
        "basepython": "python3",
        "passenv": "*",
        "setenv": (
            "\nLC_ALL = C.UTF-8"
            "\nLSR_ROLE2COLL_VERSION = main"
            "\nLSR_ROLE2COLL_NAMESPACE = fedora"
            "\nLSR_ROLE2COLL_NAME = linux_system_roles"
            "\nLSR_SCRIPTDIR = ./scripts"
            "\nLSR_CONFIGDIR = ./config"
            "\n"
            "\nLSR_SCRIPTDIR = ./scripts/../../my_scripts"
        ),
        "deps": ("\npytest" "\nPyYAML" "\ncolorama" "\n" "\nblack" "\npylint"),
        "allowlist_externals": (
            "\nbash" "\ntouch" "\nfind" "\n" "\nexpect" "\nsed" "\ngrep"
        ),
        "command": "pytest tests/unit {posargs}",
    },
    "testenv:py36": {
        "basepython": "python3.6",
    },
    "lsr_black": {
        "configfile": "./config/myconfig.cfg",
    },
}


class Patcher(object):
    """Patching context manager."""

    def __init__(self, **spec):
        """Initialize the context manager."""

        def mock_get_lsr_default():
            return spec.get("lsr_default", DEFAULT_INI)

        def mock_get_lsr_scriptdir():
            return spec.get("lsr_scriptdir", "./scripts")

        def mock_get_lsr_configdir():
            return spec.get("lsr_configdir", "./config")

        def mock_is_lsr_enabled(unused_state):
            return spec.get("lsr_enabled", True)

        self.__patchset = [
            patch("tox_lsr.hooks4.ConfigParser", MockConfigParser),
            patch("tox_lsr.hooks4.get_lsr_default", mock_get_lsr_default),
            patch("tox_lsr.hooks4.IniLoader", MockIniLoader),
            patch("tox_lsr.hooks4.get_lsr_scriptdir", mock_get_lsr_scriptdir),
            patch("tox_lsr.hooks4.get_lsr_configdir", mock_get_lsr_configdir),
            patch("tox_lsr.hooks4.is_lsr_enabled", mock_is_lsr_enabled),
        ]

    def __enter__(self):
        """Enter the context."""
        for patch_item in self.__patchset:
            patch_item.start()
        return self

    def __exit__(self, *args):
        """Exit the context."""
        for patch_item in reversed(self.__patchset):
            patch_item.stop()


def make_core_conf_state_pair(tox_ini_data):
    """Make a pair (core_conf, state) from tox.ini data."""
    core_conf = MockCoreConfigSet()
    tox_ini = MockConfigParser(data=tox_ini_data)
    config_source = MockIniSource(parser=tox_ini)
    config_source._section_to_loaders["tox"] = []
    if "tox" in tox_ini_data:
        loader = MockIniLoader(
            section=config_source.get_core_section(),
            parser=tox_ini,
            overrides=[],
            core_section=config_source.get_core_section(),
            section_key="tox",
        )
        config_source._section_to_loaders["tox"].append(loader)
        core_conf.loaders.append(loader)
    return core_conf, MockState(config_source=config_source)


class Hooks4TestCase(TestCase):
    """Test case for tox 4 version of hooks."""

    def setUp(self):
        """Set up the test."""
        self.maxDiff = None  # pylint: disable=invalid-name

    def test_option_added(self):
        """Test whether tox_add_option adds an option."""
        parser = MockArgumentParser()
        self.assertEqual(0, len(parser.arguments))
        tox_add_option(parser)
        self.assertEqual("--lsr-enable", parser.arguments[0][0][0])

    def test_tox_lsr_is_not_enabled(self):
        """
        Test whether is_lsr_enabled can disable the plugin.

        Test tox_add_core_config changes nothing when tox_lsr plugin is
        disabled.
        """
        core_conf, state = make_core_conf_state_pair(
            TOX_INI_MISSING_TOX_SECTION
        )
        self.assertEqual(0, len(core_conf.loaders))
        self.assertEqual(0, len(state.conf._src._section_to_loaders["tox"]))
        with Patcher(lsr_enabled=False):
            tox_add_core_config(core_conf, state)
        self.assertEqual(0, len(core_conf.loaders))
        self.assertEqual(0, len(state.conf._src._section_to_loaders["tox"]))
        self.assertEqual(
            TOX_INI_MISSING_TOX_SECTION, state.conf._src._parser._data
        )

    def test_missing_tox_section(self):
        """Test whether default [tox] section is injected."""
        core_conf, state = make_core_conf_state_pair(
            TOX_INI_MISSING_TOX_SECTION
        )
        self.assertEqual(0, len(core_conf.loaders))
        self.assertEqual(0, len(state.conf._src._section_to_loaders["tox"]))
        with Patcher():
            tox_add_core_config(core_conf, state)
        self.assertEqual(
            TOX_INI_MISSING_TOX_SECTION_MERGED, state.conf._src._parser._data
        )
        self.assertIs(
            core_conf.loaders[0], state.conf._src._section_to_loaders["tox"][0]
        )

    def test_tox_section_not_injected(self):
        """
        Test whether loaders are not updated when [tox] section does not exist.

        If neither tox.ini nor tox-default.ini has [tox] section do not add a
        loader for this section.
        """
        core_conf, state = make_core_conf_state_pair(
            TOX_INI_MISSING_TOX_SECTION
        )
        default_ini = deepcopy(DEFAULT_INI)
        del default_ini["tox"]
        with Patcher(lsr_default=default_ini):
            tox_add_core_config(core_conf, state)
        # No [tox] section implies no IniLoader added
        self.assertEqual(0, len(core_conf.loaders))
        self.assertEqual(0, len(state.conf._src._section_to_loaders["tox"]))

    def test_loaders_are_not_consistent(self):
        """Test loaders consistency check."""
        core_conf, state = make_core_conf_state_pair(TOX_INI_OVERRIDE_DEFAULTS)
        del core_conf.loaders[-1]
        with self.assertRaises(ValueError):
            with Patcher():
                tox_add_core_config(core_conf, state)

    def test_override_defaults(self):
        """Test overriding settings from tox-default.ini."""
        core_conf, state = make_core_conf_state_pair(TOX_INI_OVERRIDE_DEFAULTS)
        with Patcher():
            tox_add_core_config(core_conf, state)
        self.assertEqual(
            TOX_INI_OVERRIDE_DEFAULTS_MERGED, state.conf._src._parser._data
        )
        self.assertIs(
            core_conf.loaders[0], state.conf._src._section_to_loaders["tox"][0]
        )
