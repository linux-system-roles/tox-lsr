#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Type annotations for tox.plugin."""

from typing import Callable, TypeVar, overload

from tox.config import CoreConfigSet, Parser
from tox.session import State

_HFTP = TypeVar("_HFTP", bound=Callable[[Parser], None])
_HFTCS = TypeVar("_HFTCS", bound=Callable[[CoreConfigSet, State], None])

@overload
def impl(function: _HFTP) -> _HFTP: ...

@overload
def impl(
    tryfirst: bool = ...,
    trylast: bool = ...,
) -> Callable[[_HFTCS], _HFTCS]: ...
