#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""
Install tox-lsr hooks to tox (tox 4 version).

How tox 4 reads its configuration
=================================

They are two types of configuration:
1. project configuration (tox.ini in project root)
2. user configuration (tox/config.ini in user's configuration directory)

We are interested in the first one. When tox starts, these steps are performed
before tox_add_core_config hook is called:
- create State as state
  - parse CLI options
  - create IniSource as config_source
    - set self._section_to_loaders to the empty dictionary
    - set self._parser to ConfigParser with tox.ini loaded
    - set self._section_mapping to the empty dictionary
  - create Config as config
    - set self._src to config_source
    - set self._key_to_conf_set to the empty ordered dictionary
    - set self._core_set to None (this is where configuration under the [tox]
      section is stored)
  - set state.conf to config
- run provision(state)
  - access state.conf.core property
    - set state.conf._core_set to CoreConfigSet instance with
      - self._conf set to state.conf
      - self.loaders set to the empty list
      - self._defines set to the empty dictionary
      - self._keys set to the empty dictionary
      - self._alias set to the empty dictionary
      - add the constant key "config_file_path"
      - add a key "tox_root" with an alias "toxinidir"
      - add a key "work_dir" with an alias "toxworkdir"
        * accessing this key also access "tox_root" key
      - add a key "temp_dir"
        * accessing this key also access "work_dir" key
      - add the constant key "host_python"
      - add a key "env_list" with an alias "envlist"
    - set state.conf._src._section_to_loaders["tox"] to the empty list
    - if project configuration (tox.ini) has [tox] section
      - append IniLoader for [tox] section to
        state.conf._src._section_to_loaders["tox"]
    - add a key "base" to state.conf._core_set
    - if "base" is in [tox] section
      - for every existing section X in "base" (access state.conf.core["base"],
        cache the value)
        - append X loader to state.conf._src._section_to_loaders["tox"]
        - set X.parent to be the following loader (if any)
    - add loaders from state.conf._src._section_to_loaders["tox"] to
      state.conf._core_set.loaders
  - add more keys to state.conf.core
    - "min_version" with an alias "minversion"
    - "provision_tox_env"
    - "requires"
      * accessing this key also access "min_version"
  - access state.conf.core["requires"], cache the value
  - access state.conf.core["min_version"], cache the value
  - access state.conf.core["tox_root"], cache the value
  - access state.conf.core["provision_tox_env"], cache the value
  - add a key "labels" to state.conf._core_set
  - invoke tox_add_core_config hook

From the above, we can deduce the following:
* the list of accessed and cached keys from the core ([tox]) section are:
  - base, requires, min_version, tox_root, and provision_tox_env
* if the project tox.ini has no [tox] section, accessed keys fall back to their
  defaults (there is no loader for the [tox] section)
* keys and sections are loaded from the ConfigParser on demand

Injecting defaults to the project config
========================================
Default configuration from tox-default.ini is injected into project
configuration, usually in tox.ini file, in the following way:
1. For every pair (section, key) in tox-default.ini:
   * if (section, key) is not in tox.ini:
     * interpolate the value and add it to tox.ini under (section, key);
   * otherwise, if key is one of deps, setenv, passenv or allowlist_externals:
     * add the default value before the user-specific value and interpolate the
       entire result;
   * otherwise, interpolate the user-specific value.
2. Interpolate the remaining (section, key) pairs in tox.ini that were not
   interpolated in the previous step.
3. Add a [tox] section loader, if necessary, so tox will use LSR specific
   defaults and not its internal ones.

During the interpolation {lsr_scriptdir} and {lsr_configdir} are expanded to
their real values.
"""

from configparser import ConfigParser
from typing import TYPE_CHECKING, cast

from tox.config.loader.ini import IniLoader
from tox.plugin import impl

from .utils import (
    add_tox_lsr_options,
    get_lsr_configdir,
    get_lsr_default,
    get_lsr_scriptdir,
    is_lsr_enabled,
    lsr_interpolate,
)

if TYPE_CHECKING:
    from typing import List, Optional

    from tox.config import CoreConfigSet, Parser
    from tox.config.loader import Loader
    from tox.config.source import IniSource
    from tox.session import State

# pylint: disable=protected-access


def get_default_config():
    # type: () -> ConfigParser
    """Return config parser with tox-default.ini loaded."""

    config = ConfigParser(interpolation=None)
    config.read_string(get_lsr_default())
    return config


def find_tox_loader(loaders):
    # type: (List[Loader]) -> Optional[Loader]
    """
    Find a loader for [tox] section.

    :param loaders: The list of loaders

    Return a loader that reads values from the [tox] section or None if there
    is no such a loader.
    """

    for loader in loaders:
        if isinstance(loader, IniLoader) and loader.core_section.key == "tox":
            return loader
    return None


def update_config_loaders(core_conf, state):
    # type: (CoreConfigSet, State) -> None
    """
    Update configuration loaders.

    :param core_conf: The core ([tox]) configuration set
    :param state: The state of tox

    If injecting the defaults creates a [tox] section inside the tox.ini
    parser, add the [tox] section loader if it is missing.
    """

    # No [tox] section in tox.ini -> skip this step
    if not cast("IniSource", state.conf._src)._parser.has_section("tox"):
        return

    loaders = state.conf._src._section_to_loaders["tox"]
    core_conf_loaders = core_conf.loaders

    # Check the integrity of loaders and core_conf_loaders
    tox_loader = find_tox_loader(loaders)
    if tox_loader is not find_tox_loader(core_conf_loaders):
        raise ValueError("tox-lsr: [tox] loaders mismatch")

    # [tox] section loader already present -> we are done
    if tox_loader:
        return

    # Create a new loader for the [tox] section and add it to the loaders
    # lists. Without the existing loader tox ignores the [tox] section and
    # fallbacks to its defaults
    core_section = cast("IniSource", state.conf._src).get_core_section()
    tox_loader = IniLoader(
        section=core_section,
        parser=cast("IniSource", state.conf._src)._parser,
        overrides=state.conf._overrides.get(core_section.key, []),
        core_section=core_section,
        section_key=core_section.key,
    )
    loaders.insert(0, tox_loader)
    if loaders is not core_conf_loaders:
        core_conf_loaders.insert(0, tox_loader)


def inject_defaults(config, default_config):
    # type: (ConfigParser, ConfigParser) -> None
    """
    Inject tox-defaults.ini into tox.ini.

    :param config: The configuration from tox.ini
    :param default_config: The configuration from tox-default.ini

    For every (section, key) in tox-default.ini:
    * if (section, key) is not in tox.ini, add it and interpolate
    * otherwise, if key is one of setenv, deps, passenv, or
      allowlist_externals:
      * insert the value from tox-default.ini before the value from tox.ini and
        interpolate
    * otherwise, only interpolate

    Also interpolate remaining configuration values in tox.ini.

    During the interpolation {lsr_scriptdir} and {lsr_configdir} are expanded
    to their real values.
    """

    scripts = get_lsr_scriptdir()
    configs = get_lsr_configdir()

    seen = set()

    for section in default_config.sections():
        if (
            not config.has_section(section)
            and len(default_config.options(section)) > 0
        ):
            config.add_section(section)
        for key in default_config.options(section):
            seen.add((section, key))
            value = default_config.get(section, key)
            if not config.has_option(section, key):
                config.set(
                    section, key, lsr_interpolate(value, scripts, configs)
                )
            elif key in ("setenv", "deps", "passenv", "allowlist_externals"):
                value += "\n" + config.get(section, key)
                config.set(
                    section, key, lsr_interpolate(value, scripts, configs)
                )
            else:
                value = config.get(section, key)
                config.set(
                    section, key, lsr_interpolate(value, scripts, configs)
                )

    for section in config.sections():
        for key in config.options(section):
            if (section, key) not in seen:
                value = config.get(section, key)
                config.set(
                    section, key, lsr_interpolate(value, scripts, configs)
                )


@impl
def tox_add_option(parser):
    # type: (Parser) -> None
    """
    Add lsr-enable option.

    :param parser: The tox argument parser
    """

    add_tox_lsr_options(parser)


@impl(tryfirst=True)
def tox_add_core_config(core_conf, state):
    # type: (CoreConfigSet, State) -> None
    """
    Adjust tox configuration.

    :param core_conf: The core ([tox]) configuration set
    :param state: The state of tox

    Called when [tox] section is loaded. This is the only place the tox
    configuration can be adjusted "in time". Since the configuration values are
    loaded on demand, we can update [tox] section even when the section is
    already loaded. However, there is one restriction: do not use any of base,
    requires, min_version, tox_root, or provision_tox_env in [tox] section in
    tox-default.ini. Since these are read before the hook invocation and their
    values already had impact on control flow, there is no way how to tell tox
    "Hey, revert and repeat this step with the default from tox-default.ini and
    not with your internally defined default!" other than manipulating Python
    stack frame and other affected objects.
    """

    if not is_lsr_enabled(state.conf):
        return

    # Inject before updating loaders. Missing [tox] section makes IniLoader
    # raise the exception during __init__
    inject_defaults(
        cast("IniSource", state.conf._src)._parser, get_default_config()
    )
    update_config_loaders(core_conf, state)
