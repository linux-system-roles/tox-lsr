![CI Status](https://github.com/linux-system-roles/auto-maintenance/workflows/tox/badge.svg)
[![Coverage Status](https://coveralls.io/repos/github/linux-system-roles/tox-lsr/badge.svg?branch=main)](https://coveralls.io/github/linux-system-roles/tox-lsr?branch=main)

# Linux System Roles Plugin for `tox`

This plugin for `tox` provides default settings used for testing Linux system
roles via `tox`. The default settings can be overridden by role developer in
`tox.ini`.

## How to Get It

For local development, if you have already installed `tox` and `pip`:
```
pip install --user git+https://github.com/linux-system-roles/tox-lsr@main
```
This will install `tox-lsr` in your `~/.local` directory where tox should find
it.  If you want to use a release tagged version:
```
pip install --user git+https://github.com/linux-system-roles/tox-lsr@0.0.4
```
Look at https://github.com/linux-system-roles/tox-lsr/releases for the list of
releases and tags.

To confirm that you have it and that `tox` can use it:
```
# tox --help | grep lsr-enable
usage: tox [--lsr-enable] [--version] [-h] [--help-ini] [-v] [-q]
  --lsr-enable          Enable the use of the tox-lsr plugin (env: LSR_ENABLE)
```
This shows that the `--lsr-enable` flag is available.

### Molecule and Ansible Version Support

As of August 30, 2021, system roles do not support the latest versions of
molecule 3.x or later, which only support Ansible 3.x or later.  While it's
possible that system roles will work with Ansible 3.x and later, there is some
work that needs to be done to ensure that they are supportable and supported.
Therefore, for now, molecule testing is disabled by default, and we will revisit
this issue in the near future.

tox-lsr 2.0 and later use molecule v3, which support Ansible 2.8 and later.  If
for some reason you need to support Ansible 2.7 or earlier, use tox-lsr 1.x.

## Example tox.ini

The following is an example of a `tox.ini` from the kernel_settings role:
```ini
[lsr_config]
lsr_enable = true
commands_pre = bash -c '{toxinidir}/tests/install_tuned_for_testing.sh || {toxinidir}/tests/kernel_settings/install_tuned_for_testing.sh'

[lsr_yamllint]
configfile = {toxinidir}/.yamllint.yml
configbasename = .yamllint.yml

[testenv]
setenv =
    TEST_SRC_DIR = {toxinidir}/tests
```

The `[lsr_config]` section is the configuration for the `tox-lsr` plugin.  You
must set `lsr_enable = true` in order to use the plugin.  You can confirm that
the plugin is being used:
```
# tox -l
black
pylint
flake8
...
```
If the plugin is not enabled, you would only see testenv definitions in your
`tox.ini` file.

## Configuration

There are several ways to append to and override the default configuration.

### Tox command line arguments

All of the usual tox command line arguments work as you would expect.  The
information returned is a result of merging your local tox.ini with the default,
so flags like `-l` will return the default environments, `-e` can use the
default environments, `--showconfig` will show the full merged config, etc.
However, the `--skip-missing-interpreters` argument is ignored.  If you want to
explicitly set this, you must add it to your local tox.ini:
```
[tox]
skip_missing_interpreters = false
```

### Standard tox.ini configuration

You can use the standard `tox` configuration in your local `tox.ini`, and the
plugin will attempt to merge those settings with its default settings.  If the
setting is set in the local `tox.ini`, it will be applied, replacing any default
setting, if any.  However, there are a few settings which will be merged -
`setenv`, `passenv`, `deps`, `whitelist_external`.  For `setenv`, you can
override a default setting.  For example, if the default was:
```ini
[testenv:pylint]
setenv =
    A = a
    B = b
deps =
    a
    b
passenv =
    A
whitelist_externals =
    bash
commands = pylint ...
```
and you specified this in your local `tox.ini`:
```ini
[testenv:pylint]
setenv =
    A = c
    D = d
deps =
    c
    d
passenv =
    B
whitelist_externals =
    sed
    grep
commands = mypylint
```
The final result would be:
```ini
[testenv:pylint]
setenv =
    A = c
    B = b
    D = d
deps =
    a
    b
    c
    d
passenv =
    A
    B
whitelist_externals =
    bash
    sed
    grep
commands = mypylint
```
The local `tox.ini` settings were merged with the defaults, and in the case of
`setenv`, the local `tox.ini` settings replaced the defaults where there was a
conflict.  All of the other parameters you set in the local `tox.ini` will be
set, replacing any existing default parameters.

You can also define your own tests and config sections - you do not have to use
`custom`.  However, if you add your own tests, you must also add them to the
`[tox]` section `envlist`.  For example:
```ini
[tox]
envlist = mytest

[lsr_config]
lsr_enable = true

[mytests_common]
deps = mydeps

[testenv:mytest]
deps = {[mytests_common]mydeps} mytestdep
commands = mytest
```
Then `tox -l` will show `mytest` in addition to the default tests.

#### How to completely disable a test

Define its testenv but use `true` for `commands`.  For example, to disable
`flake8`:
```ini
[testenv:flake8]
commands = true
```

### Using the [lsr_config] section

There are a few settings that can be set in the `[lsr_config]` section:
* `lsr_enable` - `false` or `true` - default `false` - you must explicitly set
  this `lsr_enable = true` in your local `tox.ini` in order to use the `tox-lsr`
  plugin.
* `commands_pre` - a list of commands - default empty - this is a list of
  commands to run before the test, for every test.  If you want to run commands
  only before certain tests, you must make your tests aware of the
  `$LSR_TOX_ENV_NAME` environment variable, or use `{envname}` in your
  `commands_pre` definition.
* `commands_post` - a list of commands - default empty - this is a list of
  commands to run after the test, for every test.  If you want to run commands
  only after certain tests, you must make your tests aware of the
  `$LSR_TOX_ENV_NAME` environment variable, or use `{envname}` in your
  `commands_pre` definition.

Here is an example from the kernel_settings role that uses `commands_pre` to run
a script before every test, and the script will only execute for certain tests:
```ini
[lsr_config]
lsr_enable = true
commands_pre = bash -c '{toxinidir}/tests/install_tuned_for_testing.sh || {toxinidir}/tests/kernel_settings/install_tuned_for_testing.sh'
```
and this is what the script does:
```bash
KS_LSR_NEED_TUNED=0
case "${LSR_TOX_ENV_NAME:-}" in
  pylint) KS_LSR_NEED_TUNED=1 ;;
  py*) KS_LSR_NEED_TUNED=1 ;;
  coveralls) KS_LSR_NEED_TUNED=1 ;;
  flake8) KS_LSR_NEED_TUNED=1 ;;
esac
if [ "$KS_LSR_NEED_TUNED" = 1 ] ; then
  ks_lsr_install_tuned "$KS_LSR_PYVER" "$(ks_lsr_get_site_packages_dir)"
fi
```
So the script is only executed for `pylint`, `coveralls`, `flake8`, and any test
beginning with `py` e.g. `py38`.

### Using [lsr_TESTNAME] sections

Each test has a corresponding `[lsr_TESTNAME]` section.  For example, there is a
`[lsr_flake8]` section.  This is primarily used when you want to completely
replace the default config file.  If the default looks like this:
```ini
[lsr_flake8]
configfile = {lsr_configdir}/flake8.ini

[testenv:flake8]
commands =
    bash {lsr_scriptdir}/setup_module_utils.sh
    {[lsr_config]commands_pre}
    python -m flake8 --config {[lsr_flake8]configfile} \
        {env:RUN_FLAKE8_EXTRA_ARGS:} {posargs} .
    {[lsr_config]commands_post}
```
and you want to use your custom `flake8.conf` to completely override and replace
the default config, use this in your local `tox.ini`:
```ini
[lsr_flake8]
configfile = {toxinidir}/flake8.conf
```
Then doing `tox -e flake8` would use your flake8.conf.

### Using setenv and environment variables

These environment variables can be set in your local tox.ini `testenv` section.
Some of the environment variables we used in the old scripts are carried over:
* `RUN_PYTEST_SETUP_MODULE_UTILS` - if set to an arbitrary non-empty value, the
  environment will be configured so that tests of the `module_utils/` code will be
  run correctly
* `RUN_PYLINT_SETUP_MODULE_UTILS` - if set to an arbitrary non-empty value, the
  environment will be configured so that linting of the `module_utils/` code will
  be run correctly
* `RUN_FLAKE8_EXTRA_ARGS` - any extra command line arguments to provide e.g.
  `--ignore=some,errs`
* `RUN_SHELLCHECK_EXTRA_ARGS` - any extra command line arguments to provide e.g.
  `--ignore=some,errs`
* `RUN_BLACK_EXTRA_ARGS` - any extra command line arguments to provide e.g.
  `--ignore=some,errs`
* `LSR_PUBLISH_COVERAGE` - If the variable is unset or empty (the default), no
  coverage is published.  Other valid values for the variable are:
    * `strict` - the reporting is performed in strict mode, so situations like
      missing data to be reported are treated as errors
    * `debug` - coveralls is run in debug mode (see coveralls debug --help)
    * `normal` - coverage results will be reported normally
* `LSR_TESTSDIR` - a path to directory where tests and tests artifacts are
  located; if unset or empty, this variable is set to `${TOPDIR}/tests` - this
  path should already exist and be populated with tests artifacts before the
  script starts performing actions on it

There are some new variables which can be set via `setenv` in `tox.ini` or via
environment variables:
* `RUN_PYTEST_EXTRA_ARGS` - extra command line arguments to provide to pytest
* `RUN_PYLINT_EXTRA_ARGS` - extra command line arguments to provide to pylint
* `RUN_YAMLLINT_EXTRA_ARGS` - extra command line arguments to provide to
  yamllint
* `RUN_ANSIBLE_LINT_EXTRA_ARGS` - extra command line arguments to provide to
  ansible-lint
* `LSR_ROLE2COLL_VERSION` - a tag/commit of the lsr_role2collection script to
  use for the collection tox test.  The default is the latest stable version.
* `LSR_ROLE2COLL_NAMESPACE` - namespace to use for the lsr_role2collection
  script.  The default is `fedora`.
* `LSR_ROLE2COLL_NAME` - collection name to use for the lsr_role2collection
  script.  The default is `linux_system_roles`.
* `LSR_ANSIBLE_TEST_DEBUG` - if set to `true`, `ansible-test` will produce
  additional output for debugging purposes.  The default is `false`.
* `LSR_ANSIBLE_TEST_TESTS` - a space delimited list of `ansible-test` tests to
  run.  See `ansible-test sanity --list-tests` for the tests you can run. See
  also `LSR_ANSIBLE_DOC_DEBUG`.
* `LSR_ANSIBLE_DOC_DEBUG` - if set to `true`, `ansible-test` will produce
  additional output when running the `ansible-doc` test.  The default is
  `false`. This is very useful when working on the docs for a plugin or module
  and you want to see how it renders, and you don't want any other tests to run.
  See also `Working on collections docs` below.
* `RUN_BLACK_CONFIG_FILE` - path to config file to use instead of the default
* `RUN_FLAKE8_CONFIG_FILE` - path to config file to use instead of the default
* `RUN_YAMLLINT_CONFIG_FILE` - path to config file to use instead of the default
* `LSR_ANSIBLE_TEST_DOCKER` - if set to `true`, `ansible-test` will be run with
  `--docker`
* `LSR_ANSIBLE_TEST_DEP` - this is the dep to pass when doing the pip install of
  ansible for ansible-test.  The default is `ansible-core==2.12.*`.
* `LSR_PYLINT_ANSIBLE_DEP` - this is the dep to pass when doing the pip install of
  ansible for pylint.  The default is `ansible-core==2.12.*`.
* `LSR_RUN_TEST_DIR` - this is the directory to use to override `changedir`, for
  those tests that need it, primarily the tests run "recursively" via `-e collection`
* `LSR_CONTAINER_RUNTIME` - default `podman` - set to `docker` if you must

These environment variables are deprecated and will be removed soon:
* `LSR_EXTRA_PACKAGES` - set in `.github/workflows/tox.yml` - list of extra
  packages to install in the CI environment (typically an Ubuntu variant)
* `LSR_ANSIBLES` - set in `.github/workflows/tox.yml` - ansible versions to test
  molecule against in the form that is used with pip e.g. use
  `LSR_ANSIBLES='ansible==2.8.* ansible==2.9.*'` to use ansible 2.8 and ansible
  2.9.  Only ansible 2.8 and higher are supported. tox-lsr 2.0 uses molecule v3,
  which does not work with ansible 2.7 or earlier.
* `LSR_MSCENARIOS` - set in `.github/workflows/tox.yml` - molecule scenarios to
  test
* `LSR_MOLECULE_DRIVER` - default `docker` - The molecule driver to use.  If you
  want to use `podman`, use `LSR_MOLECULE_DRIVER=podman`
* `LSR_MOLECULE_DRIVER_VERSION` - default empty - use this if you want to
  override the version of the molecule driver pypi package - otherwise, the
  correct version will be auto-detected.  E.g.
  `LSR_MOLECULE_DRIVER=podman LSR_MOLECULE_DRIVER_VERSION='<4.4'` will evaluate
  to something like `pip install podman<4.4`

These environment variables have been removed:
* `RUN_PYLINT_INCLUDE` - use `RUN_PYLINT_EXTRA_ARGS`
* `RUN_PYLINT_EXCLUDE` - use `RUN_PYLINT_EXTRA_ARGS`
* `RUN_PYLINT_DISABLED` - see `How to completely disable a test`
* `RUN_FLAKE8_DISABLED` - see `How to completely disable a test`
* `RUN_SHELLCHECK_DISABLED` - see `How to completely disable a test`
* `RUN_BLACK_INCLUDE` - use `RUN_BLACK_EXTRA_ARGS`
* `RUN_BLACK_EXCLUDE` - use `RUN_BLACK_EXTRA_ARGS`
* `RUN_BLACK_DISABLED` - see `How to completely disable a test`

### Environment variables available for test scripts

These environment variables are set by the plugin or the default tox
configuration and are available for use by test scripts:

* `TOXINIDIR` - the full path to the local `tox.ini`
* `LSR_SCRIPTDIR` - the full path to where the `tox-lsr` scripts are installed.
  This is primarily useful for including `utils.sh` in your scripts:
```bash
. "$LSR_SCRIPTDIR/utils.sh"
lsr_some_shell_func ....
```
* `LSR_CONFIGDIR` - the full path to where the `tox-lsr` config files are
  installed.
* `LSR_TOX_ENV_NAME` - the name of the test environment e.g. `py38`, `flake8`,
  etc.
* `LSR_TOX_ENV_DIR` - the full path to the directory for the test environment
  e.g. `/path/to/ROLENAME/.tox/env-3.8`
* `LSR_TOX_ENV_TMP_DIR` - the full path to the temporary directory for the test
  environment - equivalent to tox `{envtmpdir}`

### Working on collections docs

It can be tricky to get the plugin and module docs to render correctly.  Use a
workflow like this:
```
> LSR_ANSIBLE_TEST_DEBUG=true LSR_ANSIBLE_TEST_TESTS=ansible-doc \
  tox -e collection,ansible-test
```
This will convert your role to a collection, run `ansible-test` with only the
`ansible-doc` test, and dump what the converted doc looks like, or dump errors
if your doc could not be rendered correctly.

### QEMU testing

Integration tests are run using qemu/kvm using the test playbooks in the
`tests/` directory, using the `standard-inventory-qcow2` script to create a VM
and an Ansible inventory. There are two test envs that can be used to run these
tests:
* `qemu` - tests against the latest version of ansible supported by the roles
* `qemu-ansible-core-2.11` - tests against ansible-core 2.11
* `qemu-ansible-core-2.12` - tests against ansible-core 2.12
* `qemu-ansible-core-2.13` - tests against ansible-core 2.13

These tests run in one of two modes, depending on which of the following
arguments you provide.  Note that you must use `--` on the command line after
the `-e qemu` or `-e qemu-ansible-core-2.x` so that `tox` will not attempt to
interpret these as `tox` arguments:
```
tox -e qemu -- --image-name fedora-34 ...
```
You must provide one of `--image-file` or `--image-name`.

* `--image-file` - this is the full path to a local qcow2 image file.  This
  assumes you have already downloaded the image to a local directory.  The
  corresponding environment variable is `LSR_QEMU_IMAGE_FILE`.
* `--image-name` - assuming you have a config file (`--config`) that maps the
  given image name to an image url and optional setup, you can just specify an
  image name like `--image-name fedora-34` and the script will download the
  latest qcow2 compose image for Fedora 34 to a local cache (`--cache`).  The
  script will check to see if the downloaded image in the cache is the latest,
  and will not download if not needed.  In the config file you can specify
  additional setup steps to be run e.g. setting up additional dnf/yum repos.
  The corresponding environment variable is `LSR_QEMU_IMAGE_NAME`.
* `--image-alias` - no default - Use this if you cannot use the full path to the
  image for the hostname in the inventory.  If you use the special value
  `BASENAME` the basename of the image path/file will be used.  The
  corresponding environment variable is `LSR_QEMU_IMAGE_ALIAS`.
* `--config` - default `$HOME/.config/linux-system-roles.json` - this is the
  full path to a config file that lists the image names, the source or compose,
  and additional setup steps.  The corresponding environment variable is
  `LSR_QEMU_CONFIG`.
* `--cache` - default `$HOME/.cache/linux-system-roles` - this is the directory
  where the downloaded qcow2 images will be cached - be sure this partition has
  a lot of space if you plan on downloading multiple images.  The corresponding
  environment variable is `LSR_QEMU_CACHE`.
* `--inventory` - default
  `/usr/share/ansible/inventory/standard-inventory-qcow2` - this is useful to
  set if you are working on the inventory script and want to use your local
  clone.  The corresponding environment variable is `LSR_QEMU_INVENTORY`.
* `--collection` - This tells the script that the given playbook should be run
  in the context of a collection.  You must have already created the collection
  by first using `tox -e collection`.  The corresponding environment
  variable is `LSR_QEMU_COLLECTION`.  The test playbook should be the converted
  test - so use something like
  `.tox/ansible_collections/fedora/linux_system_roles/tests/ROLE/tests_my_test.yml`
  Otherwise, you won't be testing the collection.
* `--debug` - This uses the `TEST_DEBUG=true` for `standard-inventory-qcow2` so
  that you can debug the VM.  The corresponding environment variable is
  `LSR_QEMU_DEBUG`.
* `--pretty` - pretty print the output e.g. use `ANSIBLE_STDOUT_CALLBACK=debug`
  - the default value is `true`.  The corresponding environment variable is
  `LSR_QEMU_PRETTY`.
* `--profile` - show the profile_tasks information.  The default value is `true`.
  The corresponding environment variable is `LSR_QEMU_PROFILE`.
* `--profile-task-limit` - if using `--profile`, this specifies how many tasks
  to show in the output.  The default is `30`.  The corresponding environment
  variable is `LSR_QEMU_PROFILE_TASK_LIMIT`.
* `--use-yum-cache` - Create 1 GB files in your `cache` directory for the purpose
  of storing package cache and metadata information for the VM.  The files will
  be named `$PLATFORM_yum_cache` and `$PLATFORM_yum_varlib`.  These are mounted
  into the VM at `/var/cache/dnf` and `/var/lib/dnf` (or `yum` for YUM platforms).
  If you plan to run multiple tests on the same platform, this can speed up
  subsequent runs by installing packages from the cache rather than the network.
  The default is `false`.  The corresponding environment variable is
  `LSR_QEMU_USE_YUM_CACHE`.
* `--use-snapshot` - Create a snapshot of the image using the original image as
  the backing file.  This is useful when you want to pre-load a image for testing
  multiple test runs, but do not want to alter the original downloaded image e.g.
  pre-configuring package repos, pre-installing packages, etc.  This will create
  a file called `$IMAGE_PATH.snap` e.g. `~/.cache/linux-system-roles/fedora-34.qcow2.snap`.
  The default is `false`.  The corresponding environment variable is
  `LSR_QEMU_USE_SNAPSHOT`.
* `--wait-on-qemu` - This tells the script to wait for qemu to fully exit after
  each call to `ansible-playbook`.  This can solve race conditions if you are using
  `runqemu` to run multiple tests sequentially.  The default value is `false`.  Do
  not use this if you are using `runqemu` interactively, especially with `--debug`.
  This is intended only for use by automated test applications.  The corresponding
  environment variable is `LSR_QEMU_WAIT_ON_QEMU`.  NOTE: Don't use this unless
  you know what you are doing.
* `--setup-yml` - You can specify one or more of your own setup.yml playbooks to
  use in addition to the setup steps in the `config` file.  The corresponding
  environment variable is `LSR_QEMU_SETUP_YML`, which is a comma-delimited list
  of playbook files.  These setup playbooks should be playbooks which would be
  applied to the snapshot if using `--use-snapshot`.  If you have playbooks
  which do other types of per-test setup, do not use `--setup-yml`.  Just specify
  them in order on the command line after all of the arguments.
* `--write-inventory` - Specify a file to write the generated inventory to.  The
  filename must be simply `inventory`, or must end in `.yml`.  Examples:
  `/path/to/inventory` or `/tmp/inventory.xxx.yml`.  The user is responsible for
  removing when no longer in use.  This is useful if you use `--debug` or
  `LOCK_ON_FILE` which leave the VM running, and you want to run Ansible against
  the VM again.
* `--erase-old-snapshot` - If `true`, erase the current snapshot.  The default
  is `false`.  Use this with `--use-snapshot` to ensure a brand new snapshot is
  created.  The corresponding environment variable is `LSR_QEMU_ERASE_OLD_SNAPSHOT`.
* `--post-snap-sleep-time` - Amount in seconds to sleep after creating the
  snapshot. There is some sort of race condition that is highly platform
  dependent - if you try to use the snapshot too soon after creation, you will
  get hangs, kernel crashes, etc. in the new guest.  The only remedy so far is
  to figure out how long to sleep after creating the snapshot. The default value
  is `1` second.  The corresponding environment variable is
  `LSR_QEMU_POST_SNAP_SLEEP_TIME`.
* `--batch-file`, `--batch-report`, `--batch-id` - see below
* `--log-file` - by default, output from ansible and other commands go to
  stdout/stderr - if you pass in a path to a file, the logs will be written to
  this file - the file is opened with `"a"` so if you want a new file you should
  remove it first.  The corresponding environment variable is
  `LSR_QEMU_LOG_FILE`.
* `--log-level` - default is `warning`.  The corresponding environment variable
  is `LSR_QEMU_LOG_LEVEL`.  It is recommended to use `info` if you are using
  `--batch-file` so you can see what it is doing.
* `--tests-dir` - this is used to specify the directory where the main test
  playbook is located, usually the directory containing the `provision.fmf` used
  for the test.  `runqemu` allows specifying multiple playbooks to run.  By default
  the tests directory is the directory of the first playbook.  However, in some cases
  you may need to specify setup playbooks to run before the test.  e.g.
  `runqemu ... save-state.yml /path/to/tests/tests_1.yml ...`
  In that case, you need to tell `runqemu` where is the main `tests` directory:
  `runqemu --tests-dir  /path/to/tests ... save-state.yml /path/to/tests/tests_1.yml ...`
  The corresponding environment variable is `LSR_QEMU_TESTS_DIR`.
* `--artifacts` - The path of the directory containing the VM provisioner log files.
  By default this is `artifacts/` and `artifacts.snap/` in the current directory.
  The corresponding environment variable is `LSR_QEMU_ARTIFACTS`.

Each additional command line argument is passed through to ansible-playbook, so
it must either be an argument or a playbook.  If you want to pass both arguments
and playbooks, separate them with a `--` on the command line:
```
tox -e qemu -- --image-name fedora-34 --become --become-user root -- tests_default.yml
```
This is because `runqemu` cannot tell the difference between an Ansible argument
and a playbook.  If you do not have any ansible-playbook arguments, only
playbooks, you can omit the `--`:
```
tox -e qemu -- --image-name fedora-34 tests_default.yml
```
If using `--collection`, it is assumed you used `tox -e collection` first.  Then
specify the path to the test playbook inside this collection:
```
tox -e collection
tox -e qemu -- --image-name fedora-34 --collection .tox/ansible_collections/fedora/linux-system-roles/tests/ROLE/tests_default.yml
```

The config file looks like this:
```
{
    "images": [
    {
      "name": "fedora-34",
      "compose": "https://kojipkgs.fedoraproject.org/compose/cloud/latest-Fedora-Cloud-34/compose/",
      "setup": [
        {
          "name": "Enable HA repos",
          "hosts": "all",
          "become": true,
          "gather_facts": false,
          "tasks": [
            { "name": "Enable HA repos",
              "command": "dnf config-manager --set-enabled ha"
            }
          ]
        }
      ]
    },
    ...
}
```

Example:
```
tox -e qemu -- --image-name fedora-34 tests/tests_default.yml
```
This will lookup `fedora-34` in your `~/.config/linux-system-roles.json`, will
check if it needs to download a new image to `~/.cache/linux-system-roles`, will
create a setup playbook based on the `"setup"` section in the config, and will
run `ansible-playbook` with `standard-inventory-qcow2` as the inventory script
with `tests/tests_default.yml`.

The environment variables are useful for customizing in your local tox.ini.  For
example, if I want to use a custom location for my config and cache, and I do not
want to use the profile_tasks plugin, I can do this:
```
[qemu_common]
setenv =
    LSR_QEMU_CONFIG = /home/username/myconfig.json
    LSR_QEMU_CACHE = /my/big/partition
    LSR_QEMU_PROFILE = false
```

#### batch-file, batch-report, batch-id

There are cases where you want to run several playbooks in the same running VM,
but in multiple invocations of `ansible-playbook`.  You can use `--batch-file`
to run in this mode.  The argument to `--batch-file` is a plain text file.  Each
line is an invocation of `ansible-playbook`.  The contents of the line are the
same as the command line arguments to `runqemu`.  You can use almost all of the
same command-line parameters.  For example:
```
--log-file /path/to/test1.log --artifacts /path/to/test1-artifacts --setup-yml /path/to/setup-snapshot.yml --tests-dir /path/to/tests -e some_ansible_var="some ansible value" --batch-id tests_test1.yml -- _setup.yml save.yml /path/to/tests/tests_test1.yml restore.yml cleanup.yml
--log-file /path/to/test2.log --artifacts /path/to/test2-artifacts --setup-yml /path/to/setup-snapshot.yml --tests-dir /path/to/tests -e some_ansible_var="some ansible value" --batch-id tests_test2.yml -- _setup.yml save.yml /path/to/tests/tests_test2.yml restore.yml cleanup.yml
...
```
if you pass this as `runqemu.py --batch-file this-file.txt` it will start a VM
and create an inventory, then run
```
ansible-playbook --inventory inventory -e some_ansible_var="some ansible value" -- _setup.yml save.yml /path/to/tests/tests_test1.yml restore.yml cleanup.yml >> /path/to/test1.log 2>&1
# artifacts such as default_provisioner.log and the vm logs will go to /path/to/test1-artifacts
ansible-playbook --inventory inventory -e some_ansible_var="some ansible value" -- _setup.yml save.yml /path/to/tests/tests_test2.yml restore.yml cleanup.yml >> /path/to/test2.log 2>&1
# artifacts such as default_provisioner.log and the vm logs will go to /path/to/test2-artifacts
```
then it will shutdown the VM.  If you want to leave the VM running for
debugging, use `--debug` in the *last* entry in the batch file e.g.
`--debug --log-file /path/to/testN.log ...`

Only the following `runqemu` arguments are supported in batch files:
`--log-file`, `--artifacts`, `--setup-yml`, `--tests-dir`, and `--debug` (only
on last line). In addition, there is an argument used only in batch files -
`--batch-id` - which you can use as an identifier to correlate lines in your
batch file with the corresponding line in your batch report file. You can use
many/most `ansible-playbook` arguments.  Arguments passed in on the `runqemu`
command line will be the default values.  Specifying arguments in the batch file
will override the `runqemu` command line arguments. NOTE: With batch file, you
can use `runqemu` without providing any playbooks on the command line.  However,
if you want to provide Ansible arguments on the `runqemu` command line, you will
need to add `--` to the end of the `runqemu` command line, because `runqemu`
cannot tell the difference between an Ansible argument and a playbook.  Also, it
is recommended to put any Ansible arguments *after* any `runqemu` arguments.
Example:
```
runqemu.py --log-level info --batch-file batch.txt --batch-report report.txt \
  --skip-tags tests::nvme --
```
Since `--skip-tags` is an Ansible argument, it should come last, and it must be
followed by `--`.

`runqemu` will run *ALL* lines specified in the file, and will exit with an
error code at the end if *ANY* of the invocations had an error.  If you want to
know exactly which tests succeeded and failed, and the exit code from each test,
specify `--batch-report /path/to/file.txt`.  Each line of this file will contain
the following in this order:
* the exit code from the run
* the timestamp when the run started in sec.usec format
* the timestamp when the run finished in sec.usec format
* the batch-id, if any
* the list of playbooks for that run
```
0 1654718873.937814 1654718878.705445 tests_default.yml /path/to/tests/tests_default.yml
0 1654718879.937814 1654718881.705445 tests_ssh.yml /path/to/tests/tests_ssh.yml
2 1654718879.937814 1654718881.705445 bogus.yml /path/to/bogus.yml
```
Line `N` in the report should correspond to line `N` in the batch file, and you
can also use the batch-id for correlation.

#### Ansible Vault support

If you want to test using variables encrypted with
[Ansible Vault](https://docs.ansible.com/ansible/latest/user_guide/vault.html) do the
following:
* put the password in the file `tests/vault_pwd` e.g. `echo -n password > tests/vault_pwd`
* `mkdir tests/vars`
* encrypt the variables
```
ansible-vault encrypt_string --vault-password-file tests/vault_pwd my_secret_value \
  --name my_secret_var_name >> tests/vars/vault-variables.yml
ansible-vault encrypt_string --vault-password-file tests/vault_pwd another_value \
  --name another_var >> tests/vars/vault-variables.yml
```
Then if you run
```
tox -e qemu-... -- --image-name name tests/tests_that_uses_my_secret_value.yml
```
the variable `my_secret_var_name` will be automatically decrypted.  It is a good
idea to test roles that use passwords, keys, tokens, etc. with vault to ensure
that encryption works according to our documentation.

There may be some tests that you want to run without the variable being defined.
For example, there are some roles that always require a password to be provided
by the user, and some tests want to check the failure mode if there is no
password.  That is, you want to provide an encrypted password for all tests
except certain ones.  In that case, create the file
`tests/no-vault-variables.txt` containing the *basename* of the tests you want
to skip, one per line.  For example, if you want to run all tests except
tests_a.yml and tests_b.yml with the encrypted passwords, create the file
`tests/no-vault-variables.txt` like this:
```
tests_a.yml
tests_b.yml
```
Then you can run `tox -e qemu-... -- tests/tests_a.yml` and the vault encrypted
variables will not be defined.
