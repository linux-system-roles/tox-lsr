#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Type annotations for tox."""

from typing import Callable, TypeVar, overload

from tox.config import Config, Parser

_HFTP = TypeVar("_HFTP", bound=Callable[[Parser], None])
_HFTC = TypeVar("_HFTC", bound=Callable[[Config], None])

@overload
def hookimpl(function: _HFTP) -> _HFTP: ...

@overload
def hookimpl(
    tryfirst: bool = ...,
    trylast: bool = ...,
) -> Callable[[_HFTC], _HFTC]: ...
