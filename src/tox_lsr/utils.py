#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Shared utilities."""

import os
from typing import TYPE_CHECKING, cast

try:
    # Python >= 3.9
    import importlib.resources

    def resource_filename(pkg, ref):
        # type: (str, str) -> str
        """Get path of a resource."""
        return str(importlib.resources.files(pkg) / ref)

    def resource_bytes(pkg, ref):
        # type: (str, str) -> bytes
        """Get file bytes of a resource."""
        return (importlib.resources.files(pkg) / ref).read_bytes()

except ImportError:
    # Python 2
    import pkg_resources

    def resource_filename(pkg, ref):
        # type: (str, str) -> str
        """Get path of a resource."""
        return pkg_resources.resource_filename(pkg, ref)

    def resource_bytes(pkg, ref):
        # type: (str, str) -> bytes
        """Get file bytes of a resource."""
        return pkg_resources.resource_string(pkg, ref)


if TYPE_CHECKING:
    from tox.config import Config, Parser
    from tox.config.source import IniSource

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

# pylint: disable=protected-access


def tox_get_option(config, name, default):
    # type: (Config, str, object) -> object
    """
    Get the value of CLI option.

    :param config: The tox configuration object
    :param name: The option name as stored by ArgumentParser
    :param default: The fallback value if the option is not specified
    """

    # Here tox 4 keep CLI options
    options = cast("object", getattr(config, "_options", None))
    if options is None:
        # Fallback to tox<4
        options = config.option
    return getattr(options, name, default)


def tox_get_tox_ini_item(config, section, key, default):
    # type: (Config, str, str, object) -> object
    """
    Load the value from tox.ini.

    :param config: The tox configuration object
    :param section: The section in tox.ini
    :param key: The key under the section
    :param default: The fallback value

    In tox 4 the section and key are read from yet unprocessed tox.ini (no
    interpolations or replacements yet happened).
    """

    # tox<4 case
    if hasattr(config, "_cfg"):
        return config._cfg.get(section, key, default)
    # tox 4 case
    tox_ini = cast("IniSource", config._src)._parser
    if tox_ini.has_section(section) and tox_ini.has_option(section, key):
        return tox_ini.get(section, key)
    return default


def is_lsr_enabled(config):
    # type: (Config) -> bool
    """
    See if the tox-lsr plugin is enabled.

    :param config: The tox configuration object

    First look for a cmdline option, then the env var, then
    finally see if there is a setting in the [lsr_config]
    section.
    """

    opt = tox_get_option(config, LSR_ENABLE, None)
    if opt is not None:
        return cast(bool, opt)
    if LSR_ENABLE_ENV in os.environ:
        return os.environ[LSR_ENABLE_ENV] == "true"
    return (
        tox_get_tox_ini_item(config, LSR_CONFIG_SECTION, LSR_ENABLE, "false")
        == "true"
    )


def get_lsr_scriptdir():
    # type: () -> str
    """Get the path to test scripts."""

    lsr_scriptdir = os.environ.get(LSR_SCRIPTDIR_ENV)
    if not lsr_scriptdir:
        # pylint: disable=consider-using-f-string
        lsr_script_filename = resource_filename(
            __package__,
            "{tsdir}/{tsname}".format(
                tsdir=TEST_SCRIPTS_SUBDIR,
                tsname=SCRIPT_NAME,
            ),
        )
        lsr_scriptdir = os.path.dirname(lsr_script_filename)
    return lsr_scriptdir


def get_lsr_configdir():
    # type: () -> str
    """Get the path to configuration."""

    lsr_configdir = os.environ.get(LSR_CONFIGDIR_ENV)
    if not lsr_configdir:
        # pylint: disable=consider-using-f-string
        lsr_config_filename = resource_filename(
            __package__,
            "{cfdir}/{cfname}".format(
                cfdir=CONFIG_FILES_SUBDIR,
                cfname=CONFIG_NAME,
            ),
        )
        lsr_configdir = os.path.dirname(lsr_config_filename)
    return lsr_configdir


def get_lsr_default():
    # type: () -> str
    """Get the content of tox-default.ini."""

    # pylint: disable=consider-using-f-string
    return resource_bytes(
        __package__,
        "{cfdir}/{deftox}".format(
            cfdir=CONFIG_FILES_SUBDIR,
            deftox=TOX_DEFAULT_INI,
        ),
    ).decode()


def lsr_interpolate(value, scriptdir, configdir):
    # type: (str, str, str) -> str
    """
    Interpolate the configuration value.

    :param value: The configuration value
    :param scriptdir: The path to scripts
    :param configdir: The path to configurations

    In value, replace {lsr_scriptdir} and {lsr_configdir} by scriptdir and
    configdir, respectively.
    """

    return value.replace(LSR_SCRIPTDIR_KW, scriptdir).replace(
        LSR_CONFIGDIR_KW, configdir
    )


def add_tox_lsr_options(parser):
    # type: (Parser) -> None
    """
    Add tox-lsr specific options to tox.

    :param parser: The argument parser
    """

    # pylint: disable=consider-using-f-string
    parser.add_argument(
        "--lsr-enable",
        dest=LSR_ENABLE,
        action="store_true",
        help="Enable the use of the tox-lsr plugin (env: {envvar})".format(
            envvar=LSR_ENABLE_ENV
        ),
        default=None,
    )
