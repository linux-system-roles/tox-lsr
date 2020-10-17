#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Tests for tox_lsr hooks."""

import unittest2

from tox_lsr.hooks import tox_configure

from .utils import MockConfig


class HooksTestCase(unittest2.TestCase):
    def setUp(self):
        self.__envlist_unsorted = ["envC", "envB", "envA"]
        self.__envlist_sorted = ["envA", "envB", "envC"]

    def test_tox_configure_sorts_envlist(self):
        config = MockConfig(envlist=self.__envlist_unsorted)

        tox_configure(config)
        self.assertEqual(config.envlist, self.__envlist_sorted)
