#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Test for version presence."""

import unittest2

from tox_lsr import __version__


class VersionTestCase(unittest2.TestCase):
    def test_version(self):
        self.assertIsInstance(__version__, str)
