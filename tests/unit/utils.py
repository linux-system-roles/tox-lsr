#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Test utilities."""


class MockConfig(object):
    __slots__ = ("envlist",)

    def __init__(self, envlist=None):
        if envlist is None:
            self.envlist = []
        else:
            self.envlist = envlist[:]
