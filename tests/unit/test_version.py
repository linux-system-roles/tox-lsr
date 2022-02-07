#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Test for version presence."""

# pylint: disable=duplicate-code
try:
    from unittest2 import TestCase
except ImportError:
    from unittest import TestCase
except AttributeError:
    from unittest import TestCase

from tox_lsr import __version__


class VersionTestCase(TestCase):
    def test_version(self):
        self.assertIsInstance(__version__, str)
