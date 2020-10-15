#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Install tox-lsr hooks to tox."""

import os
import traceback

try:
    from cStringIO import StringIO
except ImportError:
    from io import StringIO

try:
    from ConfigParser import ConfigParser
except ImportError:
    from configparser import ConfigParser

from tempfile import NamedTemporaryFile

import pkg_resources

# pylint: disable=no-member,no-name-in-module,import-error
import py.iniconfig
import py.path
from tox import hookimpl
from tox.config import Config, Parser, TestenvConfig, testenvprefix

try:
    from tox.config import ParseIni  # tox 3.4.0+
except ImportError:
    from tox.config import parseini as ParseIni

TEST_SCRIPTS_SUBDIR = "test_scripts"
CONFIG_FILES_SUBDIR = "config_files"
LSR_ENABLE = "lsr_enable"
LSR_ENABLE_ENV = "LSR_ENABLE"
LSR_CONFIGDIR_KW = "{lsr_configdir}"
LSR_SCRIPTDIR_KW = "{lsr_scriptdir}"
LSR_CONFIGDIR_ENV = "LSR_CONFIGDIR"
LSR_SCRIPTDIR_ENV = "LSR_SCRIPTDIR"
LSR_CONFIG_SECTION = "lsr_config"
SCRIPT_NAME = "utils.sh"  # script that must always exist
CONFIG_NAME = "black.toml"  # config file that must always exist
TOX_DEFAULT_INI = "tox-default.ini"  # name of default tox ini


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
        # pylint: disable=super-with-arguments
        super(_LSRPath, self).__init__(path)
        self.tmppath = tmppath

    def __str__(self):
        if self.tmppath:
            call_stack = traceback.extract_stack()
            for filename, _, func, _ in call_stack:
                if filename.endswith("iniconfig.py") and func == "__init__":
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
    elif propname == "whitelist_externals":
        envconf.whitelist_externals = list(
            set(envconf.whitelist_externals + def_envconf.whitelist_externals)
        )


def set_prop_values_ini(propname, def_conf, conf):
    # type: (str, dict, dict) -> None
    """If propname is one of the values we can merge, do the merge."""

    can_be_merged = set(["setenv", "deps", "passenv", "whitelist_externals"])
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
                    setattr(envconf, propname, getattr(def_envconf, propname))
                except AttributeError:  # some props cannot be set
                    pass
            else:
                merge_prop_values(propname, envconf, def_envconf)


def merge_ini(config, default_config):
    # type: (Config, str) -> str
    """Merge the default config into the user provided config."""

    default_ini = py.iniconfig.IniConfig("", default_config)
    for section_name, section in config._cfg.sections.items():
        def_section = default_ini.sections.setdefault(section_name, section)
        if def_section is not section:
            for key in section:
                set_prop_values_ini(key, def_section, section)
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
    def_tox_sec = default_config._cfg.sections["tox"]
    tox_sec = config._cfg.sections.get("tox", {})
    for propname in dir(default_config):
        if propname.startswith("_"):
            continue
        # set in config if not set and it's set in default
        if propname in def_tox_sec and propname not in tox_sec:
            setattr(config, propname, getattr(default_config, propname))
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


def is_lsr_enabled(config):
    # type: (Config) -> bool
    """
    See if the tox-lsr plugin is enabled.

    First look for a cmdline option, then the env var, then
    finally see if there is a setting in the [lsr_config]
    section.
    """
    opt = getattr(config.option, LSR_ENABLE, None)
    if opt is not None:
        return opt
    if LSR_ENABLE_ENV in os.environ:
        return os.environ[LSR_ENABLE_ENV] == "true"
    return config._cfg.get(LSR_CONFIG_SECTION, LSR_ENABLE, "false") == "true"


@hookimpl
def tox_addoption(parser):
    # type: (Parser) -> None
    """Add lsr-enable option."""

    parser.add_argument(
        "--lsr-enable",
        dest=LSR_ENABLE,
        action="store_true",
        help="Enable the use of the tox-lsr plugin (env: {envvar})".format(
            envvar=LSR_ENABLE_ENV
        ),
        default=None,
    )


# Run this hook *before* any other tox_configure hook,
# especially the tox-travis one, because this plugin sets up the
# environments that tox-travis may use
@hookimpl(tryfirst=True)
def tox_configure(config):
    # type: (Config) -> None
    """Adjust tox configuration right after it is loaded."""

    if not is_lsr_enabled(config):
        return

    lsr_scriptdir = os.environ.get(LSR_SCRIPTDIR_ENV)
    if not lsr_scriptdir:
        lsr_script_filename = pkg_resources.resource_filename(
            __name__,
            "{tsdir}/{tsname}".format(
                tsdir=TEST_SCRIPTS_SUBDIR,
                tsname=SCRIPT_NAME,
            ),
        )
        lsr_scriptdir = os.path.dirname(lsr_script_filename)
    lsr_configdir = os.environ.get(LSR_CONFIGDIR_ENV)
    if not lsr_configdir:
        lsr_config_filename = pkg_resources.resource_filename(
            __name__,
            "{cfdir}/{cfname}".format(
                cfdir=CONFIG_FILES_SUBDIR,
                cfname=CONFIG_NAME,
            ),
        )
        lsr_configdir = os.path.dirname(lsr_config_filename)
    lsr_default = pkg_resources.resource_string(
        __name__,
        "{cfdir}/{deftox}".format(
            cfdir=CONFIG_FILES_SUBDIR,
            deftox=TOX_DEFAULT_INI,
        ),
    ).decode()
    lsr_default = (
        merge_ini(config, lsr_default)
        .replace(LSR_SCRIPTDIR_KW, lsr_scriptdir)
        .replace(LSR_CONFIGDIR_KW, lsr_configdir)
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
    tox_ini_tmp = NamedTemporaryFile(delete=False)
    try:
        with open(tox_ini_tmp.name, "w") as tox_ini_tmp_f:
            tox_ini_tmp_f.write(lsr_default)
        lsr_path = _LSRPath(config.toxinipath, tox_ini_tmp.name)
        try:
            _ = ParseIni(default_config, lsr_path, None)
        except TypeError:  # old version of tox
            _ = ParseIni(default_config, lsr_path)
        merge_config(config, default_config)
    finally:
        os.unlink(tox_ini_tmp.name)
