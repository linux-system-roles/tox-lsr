#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Type annotations for tox."""

from typing import Callable, TypeVar

from tox.config import Config

_HFT = TypeVar("_HFT", bound=Callable[[Config], None])

def hookimpl(trylast: bool = False) -> Callable[[_HFT], _HFT]: ...
