#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Tests for tox_lsr hooks shared code base."""

import os

try:
    from unittest2 import TestCase
except ImportError:
    from unittest import TestCase
except AttributeError:
    from unittest import TestCase

try:
    from unittest.mock import Mock
except ImportError:
    from mock import Mock

from tox_lsr.utils import (
    LSR_CONFIG_SECTION,
    LSR_ENABLE,
    LSR_ENABLE_ENV,
    is_lsr_enabled,
    tox_get_option,
    tox_get_tox_ini_item,
)

from .utils import (
    MockConfig,
    MockConfig4,
    MockConfigParser,
    MockIniSource,
    make_object,
)

# pylint: disable=protected-access


class UtilsTestCase(TestCase):
    """Test case for tox_lsr.utils."""

    def test_tox_get_option(self):
        """Test tox_get_option."""
        options = make_object(colored="yes")
        config3 = MockConfig(options)
        config4 = MockConfig4(options=options)

        self.assertEqual("yes", tox_get_option(config3, "colored", "no"))
        self.assertEqual("yes", tox_get_option(config4, "colored", "no"))
        self.assertEqual("no", tox_get_option(config3, "verbose", "no"))
        self.assertEqual("no", tox_get_option(config4, "verbose", "no"))

    def test_tox_get_tox_ini_item(self):
        """Test tox_get_tox_ini_item."""

        config_data = {
            "tox": {
                "envlist": ["py36", "py37"],
            },
            "lsr_black": {
                "configfile": "path/to/config.ini",
            },
        }
        config_parser = MockConfigParser(data=config_data)
        config_source = MockIniSource(parser=config_parser)

        def cfg_get_func(section, key, default):
            try:
                return config_data[section][key]
            except KeyError:
                pass
            return default

        config3 = MockConfig(cfg_get_func=cfg_get_func)
        config4 = MockConfig4(config_source=config_source)

        self.assertEqual(
            config_data["lsr_black"]["configfile"],
            tox_get_tox_ini_item(
                config3, "lsr_black", "configfile", "black.ini"
            ),
        )
        self.assertEqual(
            config_data["lsr_black"]["configfile"],
            tox_get_tox_ini_item(
                config4, "lsr_black", "configfile", "black.ini"
            ),
        )
        self.assertEqual(
            "black.ini",
            tox_get_tox_ini_item(
                config3, "lrs_black", "configfile", "black.ini"
            ),
        )
        self.assertEqual(
            "black.ini",
            tox_get_tox_ini_item(
                config4, "lrs_black", "configfile", "black.ini"
            ),
        )
        self.assertEqual(
            "black.ini",
            tox_get_tox_ini_item(
                config3, "lsr_black", "confgfile", "black.ini"
            ),
        )
        self.assertEqual(
            "black.ini",
            tox_get_tox_ini_item(
                config4, "lsr_black", "confgfile", "black.ini"
            ),
        )

    def test_is_lsr_enabled(self):
        """Test is_lsr_enabled."""

        config = MockConfig({})
        config._cfg.get = Mock(return_value="false")
        self.assertFalse(is_lsr_enabled(config))
        config._cfg.sections[LSR_CONFIG_SECTION] = {}
        self.assertFalse(is_lsr_enabled(config))
        self.assertFalse(is_lsr_enabled(config))
        config._cfg.get = Mock(return_value="true")
        self.assertTrue(is_lsr_enabled(config))

        config._cfg.get = Mock(return_value="true")
        os.environ[LSR_ENABLE_ENV] = "false"
        self.assertFalse(is_lsr_enabled(config))
        config._cfg.get = Mock(return_value="false")
        os.environ[LSR_ENABLE_ENV] = "true"
        self.assertTrue(is_lsr_enabled(config))

        config = MockConfig()
        config._cfg.get = Mock(return_value="false")
        os.environ[LSR_ENABLE_ENV] = "false"
        setattr(config.option, LSR_ENABLE, True)
        self.assertTrue(is_lsr_enabled(config))
        config._cfg.get = Mock(return_value="true")
        os.environ[LSR_ENABLE_ENV] = "true"
        setattr(config.option, LSR_ENABLE, False)
        self.assertFalse(is_lsr_enabled(config))
        del os.environ[LSR_ENABLE_ENV]
