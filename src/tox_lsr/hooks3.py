#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Install tox-lsr hooks to tox (tox 2 and 3 version)."""

import traceback
from tempfile import NamedTemporaryFile
from typing import TYPE_CHECKING, cast

# pylint: disable=no-member,no-name-in-module,import-error
import py.iniconfig
import py.path
from tox import hookimpl
from tox.config import Config, Parser, TestenvConfig, testenvprefix

try:
    from tox.config import ParseIni  # tox 3.4.0+
except ImportError:  # pragma: no cover
    from tox.config import parseini as ParseIni  # pragma: no cover

from .utils import (
    add_tox_lsr_options,
    get_lsr_configdir,
    get_lsr_default,
    get_lsr_scriptdir,
    is_lsr_enabled,
    lsr_interpolate,
)

if TYPE_CHECKING:
    from configparser import ConfigParser
    from io import StringIO
    from typing import List, Mapping, MutableMapping, Tuple

    # pylint: disable=too-few-public-methods
    class CastAnyAway(object):
        """Helper that resolves 'Any in expression' complaint."""

        def get(
            self,  # type: CastAnyAway
            unused_name,  # type: str
            unused_default,  # type: MutableMapping[str, object]
        ):
            # type: (...) -> MutableMapping[str, object]
            """Provide correct typing information to mypy."""
            return {}

else:
    try:
        from cStringIO import StringIO
    except ImportError:  # pragma: no cover
        from io import StringIO  # pragma: no cover

    try:
        from ConfigParser import ConfigParser
    except ImportError:  # pragma: no cover
        from configparser import ConfigParser  # pragma: no cover

# code uses some protected members such as _cfg, _parser, _reader
# pylint: disable=protected-access


class _LSRPath(py.path.local):
    # pylint: disable=too-few-public-methods
    """
    Hack to make IniConfig read the merged tmp ini file.

    This is primarily for support of tox 2.x.  ParseIni in
    tox 2.x takes only the ini file, which it uses for all of
    the substitutions like toxinipath.  So that file name must
    be the real, actual, local rolerepo/tox.ini filename.  The
    problem is that we need to pass in a temp file which contains
    the merged ini data, which is read in by IniConfig.  This is
    the only place that uses the actual contents of the file.  We
    use this class so that when IniConfig asks for the filename,
    it returns the temp file which contains the real contents.
    Everywhere else, the rolerepo/tox.ini filename is returned.
    """

    tmppath = ""

    def __init__(self, path, tmppath=""):
        # type: (_LSRPath, str, str) -> None
        # pylint: disable=super-with-arguments
        super(_LSRPath, self).__init__(path)
        self.tmppath = tmppath

    def __str__(self):
        # type: (_LSRPath) -> str
        if self.tmppath:
            call_stack = cast(
                "List[Tuple[str, object, str, object]]",
                traceback.extract_stack(),
            )
            for filename, _, func, _ in call_stack:
                if (
                    filename.endswith("iniconfig.py")
                    or filename.endswith("iniconfig/__init__.py")
                ) and func == "__init__":
                    return self.tmppath
        # pylint: disable=super-with-arguments
        return super(_LSRPath, self).__str__()


def prop_is_set(envconf, propname):
    # type: (TestenvConfig, str) -> bool
    """
    Determine if property propname was explicitly set in envconf.

    If the value was set in the underlying config object, either
    in the testenv:section or in the "testenv" section, then assume
    the value was explicitly set and return True, otherwise False.
    """

    section_name = testenvprefix + envconf.envname
    cfg = envconf._reader._cfg.sections.get(section_name, {})
    tecfg = envconf._reader._cfg.sections.get("testenv", {})
    return propname in cfg or propname in tecfg


def merge_prop_values(propname, envconf, def_envconf):
    # type: (str, TestenvConfig, TestenvConfig) -> None
    """If propname is one of the values we can merge, do the merge."""

    if propname == "setenv":  # merge env vars
        for envvar in def_envconf.setenv.keys():
            if envvar not in envconf.setenv:
                envconf.setenv[envvar] = def_envconf.setenv[envvar]
    elif propname == "deps":
        envconf.deps = list(set(envconf.deps + def_envconf.deps))
    elif propname == "passenv":
        envconf.passenv = envconf.passenv.union(def_envconf.passenv)
    elif propname == "allowlist_externals":
        envconf.allowlist_externals = list(
            set(envconf.allowlist_externals + def_envconf.allowlist_externals)
        )


def set_prop_values_ini(propname, def_conf, conf):
    # type: (str, MutableMapping[str, str], MutableMapping[str, str]) -> None
    """If propname is one of the values we can merge, do the merge."""

    can_be_merged = set(["setenv", "deps", "passenv", "allowlist_externals"])
    conf_val = conf[propname]
    if propname not in def_conf:
        def_conf[propname] = conf_val
    elif propname in can_be_merged:
        # merge the merge-able values
        def_conf[propname] += "\n" + conf_val
    else:
        # replace default value with value from user
        def_conf[propname] = conf_val


def merge_envconf(envconf, def_envconf):
    # type: (TestenvConfig, TestenvConfig) -> None
    """Merge the default envconfig from def_envconf into the given envconf."""

    # access what was actually set in the customized tox.ini so that
    # we can override the properties which were not set
    for propname in dir(def_envconf):
        if propname.startswith("_"):
            continue
        if prop_is_set(def_envconf, propname):
            if not prop_is_set(envconf, propname):
                try:
                    setattr(
                        envconf,
                        propname,
                        cast(object, getattr(def_envconf, propname)),
                    )
                except AttributeError:  # some props cannot be set
                    pass
            else:
                merge_prop_values(propname, envconf, def_envconf)


def merge_ini(config, default_config):
    # type: (Config, str) -> str
    """Merge the default config into the user provided config."""

    default_ini = py.iniconfig.IniConfig("", default_config)
    for section_name, section in config._cfg.sections.items():
        def_section = cast(
            "MutableMapping[str, Mapping[str, str]]", default_ini.sections
        ).setdefault(section_name, section)
        if def_section is not section:
            for key in section:
                set_prop_values_ini(
                    key,
                    cast("MutableMapping[str, str]", def_section),
                    cast("MutableMapping[str, str]", section),
                )
    # convert back to string using ConfigParser
    conf_p = ConfigParser()
    for section_name, section_data in default_ini.sections.items():
        conf_p.add_section(section_name)
        for key, val in section_data.items():
            conf_p.set(section_name, key, val)
    strio = StringIO()
    conf_p.write(strio)
    return strio.getvalue()


def merge_config(config, default_config):
    # type: (Config, Config) -> None
    """Merge default_config into config."""

    # merge the top level config properties
    def_tox_sec = cast(
        "MutableMapping[str, object]", default_config._cfg.sections["tox"]
    )
    tox_sec = cast("CastAnyAway", config._cfg.sections).get("tox", {})
    for propname in dir(default_config):
        if propname.startswith("_"):
            continue
        # set in config if not set and it's set in default
        if propname in def_tox_sec and propname not in tox_sec:
            setattr(
                config,
                propname,
                cast(object, getattr(default_config, propname)),
            )
    # handle skip_missing_interpreters specially because
    # it is stored in config.option
    if (
        "skip_missing_interpreters" not in tox_sec
        and "skip_missing_interpreters" in def_tox_sec
    ):
        default_config.option.skip_missing_interpreters = cast(
            bool, def_tox_sec["skip_missing_interpreters"]
        )
        config.option.skip_missing_interpreters = (
            default_config.option.skip_missing_interpreters
        )
    # merge the top level config properties that are set implicitly
    if hasattr(config, "envlist_explicit") and not config.envlist_explicit:
        config.envlist_default = list(
            set(config.envlist_default + default_config.envlist_default)
        )
        config.envlist = list(set(config.envlist + default_config.envlist))

    # merge the testenvs
    for def_envname, def_envconf in default_config.envconfigs.items():
        if def_envname not in config.envconfigs:
            config.envconfigs[def_envname] = def_envconf
        else:
            merge_envconf(config.envconfigs[def_envname], def_envconf)


@hookimpl
def tox_addoption(parser):
    # type: (Parser) -> None
    """Add lsr-enable option."""

    add_tox_lsr_options(parser)


# Run this hook *before* any other tox_configure hook,
# because this plugin sets up the environments that other plugins
# may use
@hookimpl(tryfirst=True)
def tox_configure(config):
    # type: (Config) -> None
    """Adjust tox configuration right after it is loaded."""

    if not is_lsr_enabled(config):
        return

    lsr_scriptdir = get_lsr_scriptdir()
    lsr_configdir = get_lsr_configdir()
    lsr_default = get_lsr_default()
    lsr_default = lsr_interpolate(
        merge_ini(config, lsr_default), lsr_scriptdir, lsr_configdir
    )
    config.option.workdir = config.toxworkdir
    try:
        default_config = Config(
            config.pluginmanager,
            config.option,
            config.interpreters,
            config._parser,
            [],
        )
    except TypeError:  # old version of tox
        # pylint: disable=no-value-for-parameter
        default_config = Config(
            config.pluginmanager,
            config.option,
            config.interpreters,
        )
        default_config._parser = config._parser
        default_config._testenv_attr = config._testenv_attr
    with NamedTemporaryFile(
        mode="w",
        prefix="tox-lsr-",
        suffix=".ini",
    ) as tox_ini_tmp:
        tox_ini_tmp.write(lsr_default)
        tox_ini_tmp.flush()
        lsr_path = _LSRPath(config.toxinipath, tox_ini_tmp.name)
        try:
            _ = ParseIni(default_config, cast(str, lsr_path), None)
        except TypeError:  # old version of tox
            _ = ParseIni(default_config, cast(str, lsr_path))
        merge_config(config, default_config)
