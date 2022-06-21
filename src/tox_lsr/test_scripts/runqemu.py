#!/usr/bin/env python
"""Launch qemu tests."""

import argparse
import errno
import glob
import json
import logging
import os
import re
import shlex
import shutil
import subprocess  # nosec
import sys
import tempfile
import time
import traceback

try:
    import urllib.parse
    import urllib.request
except ImportError:
    import urllib
from contextlib import contextmanager

import yaml

try:
    import productmd.compose

    HAS_PRODUCTMD = True
except ImportError:
    print("No productmd")
    HAS_PRODUCTMD = False
try:
    from bs4 import BeautifulSoup

    HAS_BS4 = True
except ImportError:
    # print("No soup for you!")
    HAS_BS4 = False

try:
    ProcessLookupError
except NameError:
    ProcessLookupError = OSError


# https://www.freedesktop.org/wiki/CommonExtendedAttributes/
URL_XATTR = "user.xdg.origin.url"
DATE_XATTR = "user.dublincore.date"
DEFAULT_QEMU_INVENTORY = (
    "/usr/share/ansible/inventory/standard-inventory-qcow2"
)
DEFAULT_QEMU_INVENTORY_URL = (
    "https://pagure.io/fork/rmeggins/standard-test-roles/raw/"
    "linux-system-roles/f/inventory/standard-inventory-qcow2"
)
INVENTORY_FAIL_MSG = "ERROR: Inventory is empty, tests did not run"
DEFAULT_PROFILE_TASK_LIMIT = 30  # report up to 30 tasks in profile
DEFAULT_POST_SNAP_SLEEP_TIME = 1  # seconds

COLLECTION_NAMESPACE = "fedora"
COLLECTION_NAME = "linux_system_roles"


def strtobool(val):
    """
    Convert a string representation of truth to true (1) or false (0).

    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
    'val' is anything else.
    """
    val = val.lower()
    if val in ("y", "yes", "t", "true", "on", "1"):
        return 1
    elif val in ("n", "no", "f", "false", "off", "0"):
        return 0
    else:
        raise ValueError("invalid truth value %r" % (val,))


def is_ansible_env_var_supported(env_var_name):
    """See if ansible supports the given config env var."""
    result = subprocess.check_output(  # nosec
        ["ansible-config", "list"], stderr=subprocess.STDOUT, encoding="utf-8"
    )
    # look for name: ENV_VAR_NAME in output
    match = re.search(r"name: {}\n".format(env_var_name), result)
    if match:
        return True
    return False


def get_metadata_from_file(path, attr_key):
    """Get metadata from key attr_key in file at given path."""
    try:
        mdbytes = os.getxattr(path, attr_key)
    except OSError as e:
        if e.errno == errno.ENODATA:
            return None
        raise
    return os.fsdecode(mdbytes)


def image_source_last_modified_by_file_metadata(path):
    """Get last update metadata from file at given path."""
    return (
        get_metadata_from_file(path, DATE_XATTR)
        if os.path.exists(path)
        else ""
    )


def origurl(path):
    """Return the original URL that a given file was downloaded from."""
    return get_metadata_from_file(path, URL_XATTR)


def get_metadata_from_url(url, metadata_key):
    """Get metadata from given url."""
    try:
        with urllib.request.urlopen(url) as url_response:  # nosec
            return url_response.getheader(metadata_key)
    except Exception:
        with urllib.urlopen(url) as url_response:  # nosec
            return url_response.getheader(metadata_key)


def get_inventory_script(inventory):
    """Get inventory script if URL, or set local path."""
    if inventory.startswith("http"):
        inventory_tempfile = os.path.join(
            os.environ["TOX_WORK_DIR"], "standard-inventory-qcow2"
        )
        try:
            with urllib.request.urlopen(  # nosec
                inventory  # nosec
            ) as url_response:  # nosec
                with open(inventory_tempfile, "wb") as inf:
                    shutil.copyfileobj(url_response, inf)
            os.chmod(inventory_tempfile, 0o777)  # nosec
            inventory = inventory_tempfile
        except Exception:  # pylint: disable=broad-except
            logging.warning(traceback.format_exc())
            inventory = DEFAULT_QEMU_INVENTORY
    return inventory


def fetch_image(url, cache, label):
    """
    Fetch an image from url into the cache with label.

    Fetches an image from @url into @cache as @label if a file with the
    same name downloaded from the same URL doesn't yet exist. There is
    no need for fancier caching, as image URLs are unique enough.

    Labels are not unique enough, because the URL corresponding to
    the label may get updated. And using a filename derived from URL
    would lead to leftover image files filling up the cache directory,
    as nobody would delete them when the URL changes.

    Returns the full path to the image.
    """

    original_name = url.split("/")[-1]
    nameroot, suffix = os.path.splitext(original_name)
    image_name = label + suffix
    path = os.path.join(cache, image_name)
    image_last_modified_by_src = get_metadata_from_url(url, "Last-Modified")
    image_last_modified_by_file = image_source_last_modified_by_file_metadata(
        path
    )

    if (
        not os.path.exists(path)
        or url != origurl(path)
        or image_last_modified_by_src != image_last_modified_by_file
    ):
        logging.info("Fetch url %s for %s", url, image_name)

        image_tempfile = tempfile.NamedTemporaryFile(dir=cache, delete=False)
        try:
            request = urllib.request.urlopen(url)  # nosec
            shutil.copyfileobj(request, image_tempfile)
            request.close()
        except Exception:  # pylint: disable=broad-except
            logging.warning(traceback.format_exc())
            os.unlink(image_tempfile.name)
            return None

        os.setxattr(image_tempfile.name, URL_XATTR, os.fsencode(url))
        os.setxattr(
            image_tempfile.name,
            DATE_XATTR,
            os.fsencode(image_last_modified_by_src),
        )
        os.rename(image_tempfile.name, path)
    else:
        logging.info("Using cached image %s for %s", path, image_name)

    return path


def composeurl2images(
    composeurl, desiredarch, desiredvariant=None, desiredsubvariant=None
):
    """Find the latest url for a compose link."""
    # we will need to join it with a relative path component
    if composeurl.endswith("/"):
        composepath = composeurl
    else:
        composepath = composeurl + "/"

    compose = productmd.compose.Compose(composepath)

    candidates = set()

    for variant, arches in compose.images.images.items():
        for arch in arches:
            if arch == desiredarch:
                for image in arches[arch]:
                    if image.type == "qcow2":
                        candidates.add((image, variant, image.subvariant))

    # variant and subvariant are used only as a hint
    # to disambiguate if multiple images were found
    if len(candidates) > 1:
        if desiredvariant:
            variantmatch = {
                imginfo
                for imginfo in candidates
                if imginfo[1] == desiredvariant
            }
            if len(variantmatch) > 0:
                candidates = variantmatch
    if len(candidates) > 1:
        if desiredsubvariant:
            subvariantmatch = {
                imginfo
                for imginfo in candidates
                if imginfo[2] == desiredsubvariant
            }
            if len(subvariantmatch) > 0:
                candidates = subvariantmatch

    return [(composepath + qcow2[0].path) for qcow2 in candidates]


def centoshtml2image(url, desiredarch):
    """Find the latest image url for the CentOS Stream HTML image list."""
    # we will need to join it with a relative path component
    if url.endswith("/"):
        path = url
    else:
        path = url + "/"
    if path.find("/centos/9-stream/") > -1:
        centosver = 9
    elif path.find("/centos/8-stream/") > -1:
        centosver = 8
    else:
        logging.error("Could not determine CentOS version from %s", url)
        return ""

    page = urllib.request.urlopen(url)  # nosec
    tree = BeautifulSoup(page.read(), "html.parser")
    imagelist = [
        td.a["href"]
        for td in tree.find_all("td", class_="indexcolname")
        if td.a["href"].endswith(".qcow2")
    ]
    pat = (
        r"CentOS-Stream-GenericCloud-{}-\([1-9][0-9]+[.][0-9]+\)[.]{}[.]qcow2"
    )
    namematch = re.compile(pat.format(centosver, desiredarch))

    def getdatekey(imagename):
        match = namematch.match(imagename)
        if match and len(match.groups()) > 0:
            return match.group(1)
        return ""

    candidate = sorted(imagelist, key=getdatekey)[-1]
    return path + candidate


def get_url(image):
    """Get the url to use to download the given image."""
    source = image.get("source")
    compose_url = image.get("compose")
    centoshtml_url = image.get("centoshtml")
    if source:
        return source
    elif compose_url:
        variant = image.get("variant")
        image_urls = composeurl2images(compose_url, "x86_64", variant)
        if len(image_urls) == 1:
            return image_urls[0]
        else:
            if image_urls:
                logging.error(
                    "Multiple images found: %s" "in compose %s",
                    image_urls,
                    compose_url,
                )
            else:
                logging.error("no image found in compose %s", compose_url)
    elif centoshtml_url:
        return centoshtml2image(centoshtml_url, "x86_64")
    else:
        logging.error(
            "neither source nor compose nor centoshtml specified"
            "in image %s",
            image["name"],
        )


def get_image(images, image_name):
    """Get the image config for the given image_name, or None."""
    for image in images:
        if image["name"] == image_name:
            return image
    return None


def make_setup_yml(
    image, cache, remove_cloud_init, use_snapshot, use_yum_cache
):
    """Make a setup.yml to setup the VM.  Keep in cache."""
    pre_setup_yml = os.path.join(cache, image["name"] + "_setup.yml")
    post_setup_yml = os.path.join(cache, image["name"] + "_post_setup.yml")
    setup_play = {
        "name": "Set up host for test playbooks",
        "hosts": "all",
        "gather_facts": False,
        "tasks": [],
    }
    no_log = True
    setup_plays = []
    post_setup_plays = []
    if "setup" in image:
        if isinstance(image["setup"], str):
            setup_play["tasks"].append({"raw": image["setup"]})
        else:
            setup_plays.extend(image["setup"])
    if remove_cloud_init:
        setup_play["tasks"].extend(
            [
                {
                    "name": "get cloud-init requires",
                    "command": "rpm -q --requires cloud-init",
                    "register": "__cloud_init_reqs",
                    "no_log": no_log,
                    "ignore_errors": True,
                },
                {
                    "name": "remove cloud-init",
                    "package": {"name": "cloud-init", "state": "absent"},
                    "no_log": no_log,
                    "when": "__cloud_init_reqs is success",
                },
                {
                    "name": "get deps for each cloud-init req",
                    "command": "rpm -q --whatrequires {{ item | quote }}",
                    "loop": "{{ __cloud_init_reqs.stdout_lines | unique }}",
                    "ignore_errors": True,
                    "register": "__cloud_init_deps",
                    "no_log": no_log,
                    "when": "__cloud_init_reqs is success",
                },
                {
                    "name": "remove packages that were required only by cloud-init",  # noqa: E501
                    "package": {"name": "{{ item.0 }}", "state": "absent"},
                    "loop": "{{ __cloud_init_reqs.stdout_lines | unique | zip(__cloud_init_deps.results) | list }}",  # noqa: E501
                    "when": [
                        "__cloud_init_reqs is success",
                        "item.1.stdout is match('no package requires ')",
                        "not item.0 is match('^procps')",
                        "not item.0 is match('^libselinux-python')",
                    ],  # noqa: E501
                    "ignore_errors": True,
                    "no_log": no_log,
                },
            ]
        )
    if use_snapshot or use_yum_cache:
        setup_play["gather_facts"] = True
        epelname = "Create EPEL {{ ansible_distribution_major_version }} repo"
        setup_play["tasks"].extend(
            [
                {
                    "name": epelname,
                    "command": (
                        "yum install -y https://dl.fedoraproject.org/pub/epel/"
                        "epel-release-latest-"
                        "{{ ansible_distribution_major_version }}.noarch.rpm"
                    ),
                    "no_log": no_log,
                    "args": {
                        "creates": "/etc/yum.repos.d/epel.repo",
                    },
                    "when": [
                        "ansible_distribution in ['RedHat', 'CentOS']",
                        "ansible_distribution_major_version in ['7', '8']",
                    ],
                },
                {
                    "name": "Create yum cache",
                    "command": "yum makecache",
                    "when": "ansible_pkg_mgr == 'yum'",
                    "no_log": no_log,
                },
                {
                    "name": "Create dnf cache",
                    "command": "dnf makecache",
                    "when": "ansible_pkg_mgr == 'dnf'",
                    "no_log": no_log,
                },
                {
                    "name": "Disable EPEL 7",
                    "command": "yum-config-manager --disable epel",
                    "no_log": no_log,
                    "when": [
                        "ansible_distribution in ['RedHat', 'CentOS']",
                        "ansible_distribution_major_version == '7'",
                    ],
                },
                {
                    "name": "Disable EPEL 8",
                    "command": "dnf config-manager --set-disabled epel",
                    "no_log": no_log,
                    "when": [
                        "ansible_distribution in ['RedHat', 'CentOS']",
                        "ansible_distribution_major_version == '8'",
                    ],
                },
            ]
        )
        if use_snapshot:
            # This MUST be the last task run to ensure all changes are flushed
            # completely to the persistent store
            post_setup_plays.append(
                {
                    "name": "Post setup - these happen last",
                    "hosts": "all",
                    "gather_facts": False,
                    "tasks": [
                        {
                            "name": "force sync of filesystems - ensure setup changes are made to snapshot",  # noqa: E501
                            "command": "sync",
                            "no_log": no_log,
                        },
                        {
                            "name": "shutdown guest",
                            "command": "shutdown now",
                            "async": 60,
                            "poll": 0,
                            "no_log": no_log,
                        },
                    ],
                },
            )

    if setup_plays or setup_play["tasks"]:
        if setup_play["tasks"]:
            setup_plays.append(setup_play)
        with open(pre_setup_yml, "w") as syf:
            yaml.safe_dump(setup_plays, syf)
    else:
        if os.path.exists(pre_setup_yml):
            os.unlink(pre_setup_yml)
        pre_setup_yml = None
    if post_setup_plays:
        with open(post_setup_yml, "w") as syf:
            yaml.safe_dump(post_setup_plays, syf)
    else:
        if os.path.exists(post_setup_yml):
            os.unlink(post_setup_yml)
        post_setup_yml = None
    return pre_setup_yml, post_setup_yml


def get_image_config(args):
    """Get the image to use."""
    images = {}

    if args.config != "NONE":
        with open(args.config) as configfile:
            config = json.load(configfile)
            images = config["images"]

    if args.image_name:
        image = get_image(images, args.image_name)
        if not image:
            logging.critical(
                "Given image %s not found in config %s.",
                args.image_name,
                args.config,
            )
            sys.exit(1)
    else:
        image = {
            "name": os.path.basename(args.image_file),
            "file": args.image_file,
        }
    return image


def prep_el6(args):
    """
    Extra treatment for EL6.

    1) Create openssl_el6.conf in $HOME/.config and set OPENSSL_CONF to it.
    2) Set the ssh extra args to ansible_args for the ansible execution
       as well as to the environment variable TEST_EXTRA_SSH_ARGS for qemu.
    """
    if not args.ssh_el6:
        return
    # If it does not exist, create openssl_el6.conf in ~/.config.
    dot_config = os.path.join(os.environ["HOME"], ".config")
    if not os.path.isdir(dot_config):
        os.makedirs(dot_config)
    openssl_el6_conf = os.path.join(dot_config, "openssl_el6.conf")
    os.environ["OPENSSL_CONF"] = openssl_el6_conf
    if not os.path.exists(openssl_el6_conf):
        s = """\
.include /etc/pki/tls/openssl.cnf
[openssl_init]
alg_section = evp_properties
[evp_properties]
rh-allow-sha1-signatures = yes
"""
        with open(openssl_el6_conf, "w") as f:
            f.write(s)
    os.environ["TEST_EXTRA_SSH_ARGS"] = (
        "-o KexAlgorithms=+diffie-hellman-group14-sha1 -o MACs=+hmac-sha1 "
        "-o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedKeyTypes=+ssh-rsa"
    )
    logging.info("EL6 - ssh args: %s", os.environ["TEST_EXTRA_SSH_ARGS"])
    return


def download_image(image, cache):
    """Download the image to the cache."""
    if "file" not in image:
        image_url = get_url(image)
        if not image_url:
            formatstr = "Could not determine download URL for {} from {}."
            errstr = formatstr.format(image["name"], image)
            logging.critical(errstr)
            raise Exception(errstr)
        image_path = fetch_image(image_url, cache, image["name"])
        if not image_path:
            formatstr = "Could not download image {} from URL {}."
            errstr = formatstr.format(image["name"], image_url)
            logging.critical(errstr)
            raise Exception(errstr)
        image["file"] = image_path


def stop_qemu(test_env):
    """Stop qemu using LOCK_ON_FILE and wait for it to exit."""
    lock_on_file = test_env.get("LOCK_ON_FILE")
    if lock_on_file and os.path.exists(lock_on_file):
        del test_env["LOCK_ON_FILE"]
        with open(lock_on_file) as lff:
            try:
                waitpid = int(lff.read())
            except ValueError:
                waitpid = -1
        os.unlink(lock_on_file)
        logging.info(
            "Shutting down VM pid [%d] from lock_on_file [%s]",
            waitpid,
            lock_on_file,
        )
        if waitpid == -1:
            return
        while True:
            try:
                os.kill(waitpid, 0)
                time.sleep(1)
            except ProcessLookupError as ple:
                if ple.errno == 3:
                    break  # no such process
                else:
                    raise


@contextmanager
def file_or_stdout(file_to_open, mode="a"):
    """Return a file handle or stdout, stderr for subprocess."""
    if file_to_open is None:
        stdout = sys.stdout
        stderr = sys.stderr
    else:
        stdout = open(file_to_open, mode)
        stderr = subprocess.STDOUT
    try:
        yield stdout, stderr
    finally:
        if stdout != sys.stdout:
            stdout.close()


def internal_run_ansible_playbooks(
    test_env,
    inventory,
    ansible_args,
    playbooks,
    cwd,
    wait_on_qemu=False,
    log_file=None,
    last_rc=0,
    batch_rc=0,
):
    """Run ansible-playbook with the LOCK_ON_FILE if wait_on_qemu is True."""
    if wait_on_qemu:
        test_env["LOCK_ON_FILE"] = tempfile.NamedTemporaryFile().name
    try:
        with file_or_stdout(log_file) as (stdout, stderr):
            subprocess.check_call(  # nosec
                [
                    "ansible-playbook",
                    "-vv",
                    "--inventory=" + inventory,
                    "-e",
                    "last_rc=" + str(last_rc),
                    "-e",
                    "batch_rc=" + str(batch_rc),
                ]
                + ansible_args
                + playbooks,
                env=test_env,
                cwd=cwd,
                stdout=stdout,
                stderr=stderr,
            )
    finally:
        if wait_on_qemu:
            stop_qemu(test_env)


def refresh_snapshot(
    image_file,
    snapfile,
    inventory,
    test_env,
    ansible_args,
    setup_yml,
    cwd,
    post_snap_sleep_time,
    log_file,
):
    """Create the snapshot if it is missing or too old."""
    need_refresh = False
    if not os.path.isfile(snapfile):
        need_refresh = True
        logging.info("Creating snapshot because %s does not exist", snapfile)
    else:
        snap_stats = os.stat(snapfile)
        file_stats = os.stat(image_file)
        now = time.time()
        # snapshot is older than 1 day or backing file is newer
        if now - snap_stats.st_ctime > 86400:
            need_refresh = True
            logging.info("Creating snapshot because %s is too old", snapfile)
        elif snap_stats.st_ctime < file_stats.st_ctime:
            need_refresh = True
            logging.info(
                "Creating snapshot because %s is older than backing file %s",
                snapfile,
                image_file,
            )
    if need_refresh:
        if "LOCK_ON_FILE" in test_env:
            stop_qemu(test_env)
            test_env["LOCK_ON_FILE"] = tempfile.NamedTemporaryFile().name
        with file_or_stdout(log_file) as (stdout, stderr):
            subprocess.check_call(  # nosec
                [
                    "qemu-img",
                    "create",
                    "-f",
                    "qcow2",
                    "-b",
                    image_file,
                    "-F",
                    "qcow2",
                    snapfile,
                ],
                stdout=stdout,
                stderr=stderr,
            )
        test_env_setup = {}
        test_env_setup.update(test_env)
        test_env_setup["TEST_WRITE_TO_IMAGE"] = "True"
        if "TEST_DEBUG" in test_env_setup:
            del test_env_setup["TEST_DEBUG"]
        if "TEST_ARTIFACTS" in test_env_setup:
            test_env_setup["TEST_ARTIFACTS"] = (
                test_env_setup["TEST_ARTIFACTS"] + ".snap"
            )
        if "LOCK_ON_FILE" in test_env_setup:
            del test_env_setup["LOCK_ON_FILE"]
        if "TEST_INVENTORY" in test_env_setup:
            del test_env_setup["TEST_INVENTORY"]
        internal_run_ansible_playbooks(
            test_env_setup,
            inventory,
            ansible_args,
            setup_yml,
            cwd,
            wait_on_qemu=True,
            log_file=log_file,
        )
        # there is still some sort of race condition here even with the
        # wait_on_qemu - can get a kernel panic in the guest if started too
        # soon after this - not sure what's going on, perhaps the OS is
        # still flushing the changes to the qcow2.snap file in the background
        # after the qemu process has exited - so the last resort of the
        # desperate is the sleep with the magic number :-(
        logging.info(
            "Created snapshot %s - sleeping %d seconds to allow disk sync",
            snapfile,
            post_snap_sleep_time,
        )
        time.sleep(post_snap_sleep_time)
        # sync on the host as well
        subprocess.check_call(["/bin/sync"])  # nosec


def split_args_and_playbooks(args_and_playbooks):
    """Split remaining cmd line args into ansible args and playbooks."""
    args = []
    playbooks = []
    if "--" in args_and_playbooks:
        ary = args
    else:
        ary = playbooks
    for item in args_and_playbooks:
        if item == "--":
            ary = playbooks
        else:
            ary.append(item)
    return args, playbooks


def handle_vault(tests_dir, ansible_args, playbooks, test_env):
    """Handle Ansible Vault encrypted variables."""
    vault_pwd_file = os.path.abspath(os.path.join(tests_dir, "vault_pwd"))
    logging.debug("handle_vault: tests_dir [%s] vault_pwd_file [%s]", tests_dir, vault_pwd_file)
    vault_variables_file = os.path.abspath(
        os.path.join(tests_dir, "vars", "vault-variables.yml")
    )
    ev_arg = "--extra-vars=@{}".format(vault_variables_file)
    if os.path.exists(vault_pwd_file) and os.path.exists(vault_variables_file):
        test_env["ANSIBLE_VAULT_PASSWORD_FILE"] = vault_pwd_file
        no_vault_file = os.path.join(tests_dir, "no-vault-variables.txt")
        if os.path.exists(no_vault_file):
            no_vault_tests = set(
                [xx.strip() for xx in open(no_vault_file).readlines()]
            )
            for pb in playbooks:
                pb_basename = os.path.basename(pb)
                if pb_basename in no_vault_tests:
                    if ev_arg in ansible_args:
                        ansible_args.remove(ev_arg)
                        logging.info(
                            "Skipping vault variables because %s is in %s",
                            pb_basename,
                            no_vault_file,
                        )
                        break  # cannot use vault for any pb in this set
                else:
                    if ev_arg not in ansible_args:
                        ansible_args.append(ev_arg)
        elif ev_arg not in ansible_args:
            ansible_args.append(ev_arg)
    else:
        if "ANSIBLE_VAULT_PASSWORD_FILE" in test_env:
            del test_env["ANSIBLE_VAULT_PASSWORD_FILE"]
        if ev_arg in ansible_args:
            ansible_args.remove(ev_arg)
    if ev_arg in ansible_args:
        logging.info("Using vault variables")


class Batch(object):
    """The data for each batch of playbooks."""

    def __init__(self, args, ansible_args, playbooks, setup_playbooks):
        """Init the batch object."""
        self.args = args
        self.ansible_args = ansible_args
        self.playbooks = [os.path.abspath(pb) for pb in playbooks]
        self.setup_playbooks = [os.path.abspath(pb) for pb in setup_playbooks]


def get_batches_from_playbooks_and_args(
    ansible_args,
    playbooks,
    setup_yml,
    cleanup_yml,
    batch_file,
):
    """
    Get the batches to run from the given arguments.

    Each batch has one or more of runqemu args, ansible args, playbooks, setup
    playbooks.  Note that if the batch is for cleanup playbooks, then there
    will be no setup playbooks for that batch.  Every playbook will be
    converted to the absolute path.
    """
    batches = [Batch(None, ansible_args, playbooks, setup_yml)]
    if batch_file or cleanup_yml:
        # for cleanup_yml, the strategy is to insert a one after each playbook
        # in the batch, so that one or more cleanup playbooks are run after
        # each main playbook(s)
        if batch_file:
            batch_arg_parser = get_arg_parser()
            with open(batch_file) as bf:
                for line in bf:
                    args, ansible_args = batch_arg_parser.parse_known_args(
                        shlex.split(line)
                    )
                    ansible_args, playbooks = split_args_and_playbooks(
                        ansible_args
                    )
                    if not ansible_args:
                        ansible_args = batches[0].ansible_args
                    batches.append(
                        Batch(
                            args,
                            ansible_args,
                            playbooks,
                            setup_yml + args.setup_yml,
                        )
                    )
                    if args.cleanup_yml or cleanup_yml:
                        batches.append(
                            Batch(
                                args,
                                ansible_args,
                                args.cleanup_yml + cleanup_yml,
                                [],
                            )
                        )
        elif cleanup_yml:
            batches_with_cleanup = []
            for batch in batches:
                batches_with_cleanup.append(batch)
                batches_with_cleanup.append(
                    Batch(batch.args, batch.ansible_args, cleanup_yml, [])
                )
            batches = batches_with_cleanup
    return batches


def make_batch_file(batch_file, tests_dir, ansible_args):
    if tests_dir is None:
        tests_dir = "tests"
    tests = glob.glob(tests_dir + "/tests_*.yml")
    fmtstr = "--tests-dir {} --log-file {{}} ".format(tests_dir)
    for aarg in ansible_args:
        fmtstr = fmtstr + "{} ".format(aarg)
    fmtstr = fmtstr + "-- {}\n"
    with open(batch_file, "w") as bf:
        for test in tests:
            bfline = fmtstr.format(test + ".log", test)
            bf.write(bfline)


def run_ansible_playbooks(  # noqa: C901
    image,
    setup_yml,
    cleanup_yml,
    test_env,
    debug,
    image_alias,
    collection_path,
    artifacts,
    ansible_args,
    use_snapshot,
    inventory,
    use_ansible_log,
    wait_on_qemu,
    write_inventory,
    erase_old_snapshot,
    post_snap_sleep_time,
    batch_file,
    batch_report,
    log_file,
    tests_dir,
    make_batch,
):
    """Run the given playbooks."""
    test_env.update(dict(os.environ))
    orig_inventory = inventory
    ansible_args, playbooks = split_args_and_playbooks(ansible_args)
    if make_batch:
        batch_file = "batch.txt"
        batch_report = "batch.report"
        make_batch_file(batch_file, tests_dir, ansible_args)
    batches = get_batches_from_playbooks_and_args(
        ansible_args, playbooks, setup_yml, cleanup_yml, batch_file
    )
    batch_inventory = None
    rc = 0
    batch_rc = 0
    if batch_file or cleanup_yml:
        if not write_inventory:
            batch_inventory = tempfile.NamedTemporaryFile(suffix=".yml").name
            write_inventory = batch_inventory
        test_env["LOCK_ON_FILE"] = tempfile.NamedTemporaryFile().name

    test_env["TEST_SUBJECTS"] = image["file"]
    snapfile = test_env["TEST_SUBJECTS"] + ".snap"
    if image_alias:
        test_env["TEST_HOSTALIASES"] = image_alias
    if collection_path:
        test_env["ANSIBLE_COLLECTIONS_PATHS"] = collection_path
    if write_inventory:
        test_env["TEST_INVENTORY"] = write_inventory
    for batch in batches:
        if not batch.playbooks:
            continue  # i.e. user specified playbooks only in batch_file
        if batch.args and batch.args.debug:
            test_env["TEST_DEBUG"] = "true"
        elif debug and not batch_file:
            test_env["TEST_DEBUG"] = "true"
        elif "TEST_DEBUG" in test_env:
            del test_env["TEST_DEBUG"]
        if batch.args and batch.args.artifacts:
            test_env["TEST_ARTIFACTS"] = batch.args.artifacts
        elif artifacts:
            test_env["TEST_ARTIFACTS"] = artifacts
        elif "TEST_ARTIFACTS" not in test_env:
            test_env["TEST_ARTIFACTS"] = "artifacts"
        test_env["TEST_ARTIFACTS"] = os.path.abspath(
            test_env["TEST_ARTIFACTS"]
        )
        if use_ansible_log and "ANSIBLE_LOG_PATH" not in os.environ:
            test_env["ANSIBLE_LOG_PATH"] = os.path.join(
                test_env["TEST_ARTIFACTS"], "ansible.log"
            )
        if not os.path.isdir(test_env["TEST_ARTIFACTS"]):
            os.makedirs(test_env["TEST_ARTIFACTS"])

        if batch.args and batch.args.log_file:
            local_log_file = os.path.abspath(batch.args.log_file)
        elif log_file:
            local_log_file = os.path.abspath(log_file)
        else:
            local_log_file = None

        # the cwd for the playbook process is the directory
        # of the first playbook - so that we can find the
        # provision.fmf, if any - this means we have to use
        # abs paths for the playbooks
        if batch.args and batch.args.tests_dir:
            cwd = batch.args.tests_dir
        elif tests_dir:
            cwd = tests_dir
        else:
            cwd = os.path.dirname(batch.playbooks[0])
        if (
            (batch.args and batch.args.erase_old_snapshot)
            or erase_old_snapshot
        ) and os.path.exists(snapfile):
            os.unlink(snapfile)
        if (batch.args and batch.args.use_snapshot) or use_snapshot:
            test_env["TEST_SUBJECTS"] = snapfile
            refresh_snapshot(
                image["file"],
                snapfile,
                orig_inventory,
                test_env,
                batch.ansible_args,
                batch.setup_playbooks,
                cwd,
                post_snap_sleep_time,
                local_log_file,
            )
            playbooks = batch.playbooks
        else:
            playbooks = batch.setup_playbooks + batch.playbooks
        handle_vault(cwd, batch.ansible_args, playbooks, test_env)
        if local_log_file:
            logging.info("Running playbooks %s", str(playbooks))
        last_rc = rc
        rc = 0
        start_ts = time.time()
        try:
            internal_run_ansible_playbooks(
                test_env,
                inventory,
                batch.ansible_args,
                playbooks,
                cwd,
                wait_on_qemu,
                local_log_file,
                last_rc,
                batch_rc,
            )
            if local_log_file:
                logging.info("Playbook run was successful")
        except subprocess.CalledProcessError as cpe:
            rc = cpe.returncode
            if batch_rc == 0:
                batch_rc = rc
            if local_log_file:
                logging.error("Playbook run failed with error %d", rc)
        if batch_report:
            if batch.args and batch.args.batch_id:
                batch_id_str = " " + batch.args.batch_id
            else:
                batch_id_str = ""
            with open(batch_report, "a") as br:
                br.write(
                    "%d %f %f%s %s\n"
                    % (
                        rc,
                        start_ts,
                        time.time(),
                        batch_id_str,
                        " ".join(playbooks),
                    )
                )
        if batch_inventory:
            inventory = batch_inventory
            if "TEST_INVENTORY" in test_env:
                del test_env["TEST_INVENTORY"]
    stop_qemu(test_env)
    if batch_inventory and os.path.exists(batch_inventory):
        os.unlink(batch_inventory)
    if batch_rc != 0:
        raise Exception("One or more tests failed")


def install_requirements(sourcedir, collection_path, test_env, collection):
    """Install reqs from {meta,tests}/collection-requirements.yml, if any."""
    collection_save_file = None
    force_flag = None
    if collection:
        save_collection = os.path.join(
            collection_path,
            "ansible_collections",
            COLLECTION_NAMESPACE,
            COLLECTION_NAME,
        )
        if os.path.exists(save_collection):
            # ansible-galaxy collection install will overwrite
            # fedora/linux_system_roles
            # so we have to save a copy and restore it later
            collection_save_file = os.path.join(
                collection_path, "collection.save.tar"
            )
            subprocess.check_call(  # nosec
                [
                    "tar",
                    "cfP",
                    collection_save_file,
                    save_collection,
                ]
            )
            force_flag = "--force"
    coll_rqf = os.path.join(sourcedir, "meta", "collection-requirements.yml")
    tests_rqf = os.path.join(sourcedir, "tests", "collection-requirements.yml")
    galaxy_env = {"ANSIBLE_COLLECTIONS_PATHS": collection_path}
    for reqfile in [coll_rqf, tests_rqf]:
        if os.path.isfile(reqfile):
            ag_cmd = [
                "ansible-galaxy",
                "collection",
                "install",
                "-p",
                collection_path,
                "-vv",
                "-r",
                reqfile,
            ]
            if force_flag:
                ag_cmd.append(force_flag)
            subprocess.check_call(  # nosec
                ag_cmd,
                stdout=sys.stdout,
                stderr=sys.stderr,
                env=galaxy_env,
            )
            test_env["ANSIBLE_COLLECTIONS_PATHS"] = collection_path
    if collection_save_file:
        subprocess.check_call(  # nosec
            [
                "tar",
                "xfP",
                collection_save_file,
                "--overwrite",
            ]
        )
        os.unlink(collection_save_file)


def setup_callback_plugins(pretty, profile, profile_task_limit, test_env):
    """Install and configure debug and profile_tasks."""
    if (
        "ANSIBLE_CALLBACK_PLUGINS" in os.environ
        or "ANSIBLE_CALLBACK_WHITELIST" in os.environ
        or "ANSIBLE_STDOUT_CALLBACK" in os.environ
    ):
        return
    if not pretty and not profile:
        return
    callback_plugin_dir = os.path.join(
        os.environ["TOX_WORK_DIR"], "callback_plugins"
    )
    if not os.path.isdir(callback_plugin_dir):
        os.makedirs(callback_plugin_dir)
    galaxy_env = {
        "ANSIBLE_COLLECTIONS_PATHS": os.environ["LSR_TOX_ENV_TMP_DIR"]
    }
    debug_py = os.path.join(callback_plugin_dir, "debug.py")
    profile_py = os.path.join(callback_plugin_dir, "profile_tasks.py")
    if (pretty and not os.path.isfile(debug_py)) or (
        profile and not os.path.isfile(profile_py)
    ):
        subprocess.check_call(  # nosec
            [
                "ansible-galaxy",
                "collection",
                "install",
                "-p",
                os.environ["LSR_TOX_ENV_TMP_DIR"],
                "-vv",
                "ansible.posix",
            ],
            stdout=sys.stdout,
            stderr=sys.stderr,
            env=galaxy_env,
        )
        tmp_debug_py = os.path.join(
            os.environ["LSR_TOX_ENV_TMP_DIR"],
            "ansible_collections",
            "ansible",
            "posix",
            "plugins",
            "callback",
            "debug.py",
        )
        tmp_profile_py = os.path.join(
            os.environ["LSR_TOX_ENV_TMP_DIR"],
            "ansible_collections",
            "ansible",
            "posix",
            "plugins",
            "callback",
            "profile_tasks.py",
        )
        if pretty:
            if not os.path.isfile(debug_py):
                os.rename(tmp_debug_py, debug_py)
        if profile:
            if not os.path.isfile(profile_py):
                os.rename(tmp_profile_py, profile_py)
        shutil.rmtree(
            os.path.join(
                os.environ["LSR_TOX_ENV_TMP_DIR"], "ansible_collections"
            )
        )
    if pretty:
        test_env["ANSIBLE_STDOUT_CALLBACK"] = "debug"
    if profile:
        if is_ansible_env_var_supported("ANSIBLE_CALLBACKS_ENABLED"):
            test_env["ANSIBLE_CALLBACKS_ENABLED"] = "profile_tasks"
        else:
            test_env["ANSIBLE_CALLBACK_WHITELIST"] = "profile_tasks"
        if profile_task_limit > -1:
            val = str(profile_task_limit)
            test_env["PROFILE_TASKS_TASK_OUTPUT_LIMIT"] = val
    test_env["ANSIBLE_CALLBACK_PLUGINS"] = callback_plugin_dir


def runqemu(
    image,
    cache,
    inventory,
    remove_cloud_init=False,
    collection_path=None,
    use_yum_cache=False,
    sourcedir=".",
    pretty=True,
    profile=True,
    profile_task_limit=DEFAULT_PROFILE_TASK_LIMIT,
    debug=False,
    image_alias=None,
    artifacts=None,
    ansible_args=None,
    use_snapshot=False,
    use_ansible_log=False,
    setup_yml=None,
    cleanup_yml=[],
    wait_on_qemu=False,
    write_inventory=None,
    erase_old_snapshot=False,
    post_snap_sleep_time=DEFAULT_POST_SNAP_SLEEP_TIME,
    batch_file=None,
    batch_report=None,
    log_file=None,
    tests_dir=None,
    collection=False,
    make_batch=None,
):
    """Download the image, set up, run playbooks."""
    if write_inventory:
        basename = os.path.basename(write_inventory)
        if basename != "inventory" and os.path.splitext(basename)[1] != ".yml":
            fmtstr = (
                "Write inventory file {} must be named 'inventory' or must "
                "end in '.yml'"
            )
            errmsg = fmtstr.format(write_inventory)
            logging.critical(errmsg)
            raise Exception(errmsg)
    download_image(image, cache)
    pre_setup_yml, post_setup_yml = make_setup_yml(
        image, cache, remove_cloud_init, use_snapshot, use_yum_cache
    )
    local_setup_yml = []
    if pre_setup_yml:
        local_setup_yml.append(pre_setup_yml)
    if setup_yml:
        local_setup_yml.extend(setup_yml)
    if post_setup_yml:
        local_setup_yml.append(post_setup_yml)
    local_cleanup_yml = []
    if cleanup_yml:
        local_cleanup_yml.extend(cleanup_yml)
    if collection_path is None and "TOX_WORK_DIR" in os.environ:
        collection_path = os.environ["TOX_WORK_DIR"]
    test_env = dict(image.get("env", {}))
    # failures in inventory will force ansible-playbook to fail
    test_env["ANSIBLE_INVENTORY_ANY_UNPARSED_IS_FAILED"] = "true"
    if use_yum_cache:
        yum_cache_path = os.path.join(cache, image["name"] + "_yum_cache")
        test_env["TEST_YUM_CACHE_PATHS"] = yum_cache_path
        yum_varlib_path = os.path.join(cache, image["name"] + "_yum_varlib")
        test_env["TEST_YUM_VARLIB_PATHS"] = yum_varlib_path
    install_requirements(sourcedir, collection_path, test_env, collection)
    inventory = get_inventory_script(inventory)
    setup_callback_plugins(pretty, profile, profile_task_limit, test_env)
    if ansible_args is None:
        ansible_args = []
    run_ansible_playbooks(
        image,
        local_setup_yml,
        local_cleanup_yml,
        test_env,
        debug,
        image_alias,
        collection_path,
        artifacts,
        ansible_args,
        use_snapshot,
        inventory,
        use_ansible_log,
        wait_on_qemu,
        write_inventory,
        erase_old_snapshot,
        post_snap_sleep_time,
        batch_file,
        batch_report,
        log_file,
        tests_dir,
        make_batch,
    )


def help_epilog():
    """Additional help for arguments."""
    return """Any remaining arguments are passed directly to
    ansible-playbook - these may be ansible-playbook arguments,
    or one or more playbooks.  If you specify both arguments and
    playbooks, you must separate them by using -- on the command
    line e.g. --become root -- tests_default.yml.  If you do not
    use the --, then the script assumes all arguments are
    playbooks."""


def get_arg_parser():
    """Return the argparse parser for runqemu arguments."""
    parser = argparse.ArgumentParser(epilog=help_epilog())
    parser.add_argument(
        "--config",
        default=os.environ.get(
            "LSR_QEMU_CONFIG",
            os.path.join(
                os.environ["HOME"], ".config", "linux-system-roles.json"
            ),
        ),
        help="Directory with linux-system-roles qemu config file",
    )
    parser.add_argument(
        "--cache",
        default=os.environ.get(
            "LSR_QEMU_CACHE",
            os.path.join(os.environ["HOME"], ".cache", "linux-system-roles"),
        ),
        help="Directory for caching VM images",
    )
    parser.add_argument(
        "--inventory",
        default=os.environ.get(
            "LSR_QEMU_INVENTORY",
            DEFAULT_QEMU_INVENTORY_URL,
        ),
        help=(
            "Inventory to use for VMs - if file, use directly - "
            "if URL, download to tempdir"
        ),
    )
    parser.add_argument(
        "--image-name",
        default=os.environ.get("LSR_QEMU_IMAGE_NAME"),
        help=(
            "Nickname of image (e.g. fedora-34) from config to use for testing"
        ),
    )
    parser.add_argument(
        "--image-file",
        default=os.environ.get("LSR_QEMU_IMAGE_FILE"),
        help="Full path to qcow2 image to use for testing",
    )
    parser.add_argument(
        "--image-alias",
        default=os.environ.get("LSR_QEMU_IMAGE_ALIAS"),
        help=(
            "Alias to use in the inventory instead of the full path.  "
            "Use the value 'BASENAME' to use the basename of the image."
        ),
    )
    parser.add_argument(
        "--artifacts",
        default=os.environ.get("LSR_QEMU_ARTIFACTS"),
        help="Directory for writing qemu artifacts - logs, etc.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=bool(strtobool(os.environ.get("LSR_QEMU_DEBUG", "False"))),
        help="Pass TEST_DEBUG=true to qemu for debugging the VM.",
    )
    parser.add_argument(
        "--collection",
        action="store_true",
        default=bool(
            strtobool(os.environ.get("LSR_QEMU_COLLECTION", "False"))
        ),
        help="Run against a collection instead of a role.",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        default=bool(strtobool(os.environ.get("LSR_QEMU_PRETTY", "True"))),
        help="Pretty print output (like stdout callback debug).",
    )
    parser.add_argument(
        "--profile",
        action="store_true",
        default=bool(strtobool(os.environ.get("LSR_QEMU_PROFILE", "True"))),
        help="Show task profile (like profile_tasks).",
    )
    parser.add_argument(
        "--profile-task-limit",
        default=int(
            os.environ.get(
                "LSR_QEMU_PROFILE_TASK_LIMIT", str(DEFAULT_PROFILE_TASK_LIMIT)
            )
        ),
        type=int,
        help=(
            "Number of tasks to display in profile tasks output (default: 30)."
        ),
    )
    parser.add_argument(
        "--remove-cloud-init",
        action="store_true",
        default=bool(
            strtobool(os.environ.get("LSR_QEMU_REMOVE_CLOUD_INIT", "False"))
        ),
        help="Remove cloud-init from the image before running tests.",
    )
    parser.add_argument(
        "--use-yum-cache",
        action="store_true",
        default=bool(
            strtobool(os.environ.get("LSR_QEMU_USE_YUM_CACHE", "False"))
        ),
        help=(
            "Create a dnf/yum RPM package cache - speed up for multiple runs."
        ),
    )
    parser.add_argument(
        "--use-snapshot",
        action="store_true",
        default=bool(
            strtobool(os.environ.get("LSR_QEMU_USE_SNAPSHOT", "False"))
        ),
        help="Use an image snapshot for multiple runs.",
    )
    parser.add_argument(
        "--setup-yml",
        action="append",
        default=[],
        help="one or more setup.yml to use in addition to config.",
    )
    parser.add_argument(
        "--cleanup-yml",
        action="append",
        default=[],
        help=(
            "one or more cleanup.yml playbooks.  These will be run even "
            "if the main playbooks fail.  The status will be passed to "
            "the playbooks so they can take action depending on if the main "
            "playbooks succeeded or failed."
        ),
    )
    parser.add_argument(
        "--wait-on-qemu",
        action="store_true",
        default=bool(
            strtobool(os.environ.get("LSR_QEMU_WAIT_ON_QEMU", "False"))
        ),
        help="Wait for qemu to exit - not for interactive use.",
    )
    parser.add_argument(
        "--write-inventory",
        default=os.environ.get("LSR_QEMU_WRITE_INVENTORY"),
        help=(
            "write YAML inventory to this file rather than tmp file.  "
            "The file must be named 'inventory' or must end in '.yml'.  "
            "The user is responsible for removing when no longer in use."
        ),
    )
    parser.add_argument(
        "--erase-old-snapshot",
        action="store_true",
        default=bool(
            strtobool(os.environ.get("LSR_QEMU_ERASE_OLD_SNAPSHOT", "False"))
        ),
        help=(
            "Erase any old, existing snapshot.  Use this with --use-snapshot "
            "to ensure snapshot is new."
        ),
    )
    parser.add_argument(
        "--post-snap-sleep-time",
        type=int,
        default=int(os.environ.get("LSR_QEMU_POST_SNAP_SLEEP_TIME", "0")),
        help=(
            "There is a race condition when using snapshot.  If you attempt "
            "to use the snapshot too soon after creation, you will get a "
            "hang, a guest crash, or similar.  This behavior is very platform "
            "dependent.  The only remedy so far is to figure out how much "
            "time to sleep post snap creation."
        ),
    )
    parser.add_argument(
        "--batch-file",
        default=os.environ.get("LSR_QEMU_BATCH_FILE"),
        help=(
            "text file - each line is a list of playbooks to run for each "
            "invocation of ansible-playbook, and an optional log file "
            "to write the output to.  If you are using this, do not use "
            "--setup-yml - instead, write the setup playbooks to each line."
        ),
    )
    parser.add_argument(
        "--batch-report",
        default=os.environ.get("LSR_QEMU_BATCH_REPORT"),
        help=(
            "text file - write the result of each batch to this file - "
            "contents are the batch file, but with the numeric exit code "
            "of the playbook run appended to each line."
        ),
    )
    parser.add_argument(
        "--log-file",
        default=os.environ.get("LSR_QEMU_LOG_FILE"),
        help=(
            "path of file to write Ansible output into.  default is "
            "None which means stdout/stderr."
        ),
    )
    parser.add_argument(
        "--log-level",
        default=os.environ.get("LSR_QEMU_LOG_LEVEL", "warning"),
        help=("log level for Python logging module.  Default is warning."),
    )
    parser.add_argument(
        "--tests-dir",
        default=os.environ.get("LSR_QEMU_TESTS_DIR"),
        help=(
            "path of directory to use as current directory when running "
            "tests.  This is usually the directory where the provision.fmf "
            "is found.  The default is the directory of the first playbook "
            "(setup-yml excluded)."
        ),
    )
    parser.add_argument(
        "--batch-id",
        default=os.environ.get("LSR_QEMU_BATCH_ID"),
        help=(
            "Identifier for each line in the batch file.  This option is "
            "only useful in a batch file.  This is used to identify each "
            "line in the batch file to correlate it with its corresponding "
            "line in the batch report.  For example, if you used this in "
            "your batch file:\n"
            "--batch-id my_test_name -- setup.yml pb.yml cleanup.yml\n"
            "Then your batch report file line for this would be:\n"
            "0 start_ts end_ts my_test_name setup.yml ...."
        ),
    )
    parser.add_argument(
        "--ssh-el6",
        action="store_true",
        default=bool(strtobool(os.environ.get("LSR_QEMU_SSH_EL6", "False"))),
        help=(
            "Use additional SSH arguments and configuration to talk to "
            "an EL6 host."
        ),
    )
    parser.add_argument(
        "--make-batch",
        action="store_true",
        default=bool(strtobool(os.environ.get("LSR_QEMU_MAKE_BATCH", "False"))),
        help=(
            "Create a batch file from all of the tests/tests_*.yml and run it."
        ),
    )
    return parser


def main():
    """Execute the main function."""
    parser = get_arg_parser()
    # any remaining args are assumed to be ansible-playbook args or playbooks
    args, ansible_args = parser.parse_known_args()

    args.ansible_args = ansible_args
    if not args.setup_yml and "LSR_QEMU_SETUP_YML" in os.environ:
        args.setup_yml = os.environ["LSR_QEMU_SETUP_YML"].split(",")
    if not args.cleanup_yml and "LSR_QEMU_CLEANUP_YML" in os.environ:
        args.cleanup_yml = os.environ["LSR_QEMU_CLEANUP_YML"].split(",")
    logging.getLogger().setLevel(getattr(logging, args.log_level.upper()))
    # either image-name or image-file must be given
    if not any([args.image_name, args.image_file]) or all(
        [args.image_name, args.image_file]
    ):
        logging.critical(
            "One, and only one, of --image-name or --image-file must be given."
        )
        sys.exit(1)
    if args.post_snap_sleep_time == 0:
        args.post_snap_sleep_time = DEFAULT_POST_SNAP_SLEEP_TIME
    if not os.path.isdir(args.cache):
        os.makedirs(args.cache)

    prep_el6(args)
    image = get_image_config(args)
    runqemu(
        image,
        args.cache,
        args.inventory,
        remove_cloud_init=args.remove_cloud_init,
        use_yum_cache=args.use_yum_cache,
        pretty=args.pretty,
        profile=args.profile,
        profile_task_limit=args.profile_task_limit,
        debug=args.debug,
        image_alias=args.image_alias,
        artifacts=args.artifacts,
        ansible_args=args.ansible_args,
        use_snapshot=args.use_snapshot,
        use_ansible_log=True,
        setup_yml=args.setup_yml,
        cleanup_yml=args.cleanup_yml,
        wait_on_qemu=args.wait_on_qemu,
        write_inventory=args.write_inventory,
        erase_old_snapshot=args.erase_old_snapshot,
        post_snap_sleep_time=args.post_snap_sleep_time,
        batch_file=args.batch_file,
        batch_report=args.batch_report,
        log_file=args.log_file,
        tests_dir=args.tests_dir,
        collection=args.collection,
        make_batch=args.make_batch,
    )


if __name__ == "__main__":
    main()
