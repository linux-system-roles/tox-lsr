#!/usr/bin/env python
"""Launch qemu tests."""

import argparse
import errno
import json
import logging
import os
import shutil
import subprocess  # nosec
import sys
import tempfile
import traceback
import urllib.parse
import urllib.request
from distutils.util import strtobool

import productmd.compose
import yaml

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
    with urllib.request.urlopen(url) as url_response:  # nosec
        return url_response.getheader(metadata_key)


def get_inventory_script(args):
    """Get inventory script if URL, or set local path."""
    if args.inventory.startswith("http"):
        inventory_tempfile = os.path.join(
            os.environ["TOX_WORK_DIR"], "standard-inventory-qcow2"
        )
        try:
            with urllib.request.urlopen(  # nosec
                args.inventory  # nosec
            ) as url_response:  # nosec
                with open(inventory_tempfile, "wb") as inf:
                    shutil.copyfileobj(url_response, inf)
            os.chmod(inventory_tempfile, 0o777)  # nosec
            args.inventory = inventory_tempfile
        except Exception:  # pylint: disable=broad-except
            logging.warning(traceback.format_exc())
            args.inventory = DEFAULT_QEMU_INVENTORY


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

    original_name = os.path.basename(urllib.parse.urlparse(url).path)
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


def get_url(image):
    """Get the url to use to download the given image."""
    source = image.get("source")
    if source:
        return source
    compose_url = image.get("compose")
    if compose_url:
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
    else:
        logging.error(
            "neither source nor compose specified" "in image %s", image["name"]
        )


def get_image(images, image_name):
    """Get the image config for the given image_name, or None."""
    for image in images:
        if image["name"] == image_name:
            return image
    return None


def make_setup_yml(image, args):
    """Make a setup.yml to setup the VM.  Keep in cache."""
    setup_yml = os.path.join(args.cache, image["name"] + "_setup.yml")
    inventory_fail_msg = "ERROR: Inventory is empty, tests did not run"
    fail_localhost = {
        "name": "Fail when only localhost is available",
        "hosts": "localhost",
        "gather_facts": False,
        "tasks": [
            {"debug": {"var": "groups"}},
            {
                "fail": {"msg": inventory_fail_msg},
                "when": ['groups["all"] == []'],
            },
        ],
    }
    setup_plays = [fail_localhost]
    if "setup" in image:
        if isinstance(image["setup"], str):
            play = {
                "name": "Setup",
                "hosts": "all",
                "become": True,
                "gather_facts": False,
                "tasks": [{"raw": image["setup"]}],
            }
            setup_plays.append(play)
        else:
            setup_plays.extend(image["setup"])

    with open(setup_yml, "w") as syf:
        yaml.safe_dump(setup_plays, syf)
    return setup_yml


def get_image_config(args):
    """Get the image to use."""
    images = {}

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
        image_url = get_url(image)
        if not image_url:
            logging.critical(
                "Could not determine download URL for %s from %s.",
                args.image_name,
                str(image),
            )
            sys.exit(1)
        image_path = fetch_image(image_url, args.cache, image["name"])
        if not image_path:
            logging.critical(
                "Could not download image %s from URL %s.",
                args.image_name,
                image_url,
            )
            sys.exit(1)
        image["file"] = image_path
    else:
        image = {
            "name": os.path.basename(args.image_file),
            "file": args.image_file,
        }
    return image


def run_ansible_playbooks(args, image, setup_yml, test_env):
    """Run the given playbooks."""
    test_env["TEST_SUBJECTS"] = image["file"]
    if args.debug:
        test_env["TEST_DEBUG"] = "true"
    if args.image_alias:
        test_env["TEST_HOSTALIASES"] = args.image_alias
    if args.collection:
        test_env["ANSIBLE_COLLECTIONS_PATHS"] = args.collection_base_path
    test_env.update(dict(os.environ))

    if args.artifacts:
        test_env["TEST_ARTIFACTS"] = args.artifacts
    else:
        test_env["TEST_ARTIFACTS"] = "artifacts"
    test_env["TEST_ARTIFACTS"] = os.path.abspath(test_env["TEST_ARTIFACTS"])
    if "ANSIBLE_LOG_PATH" not in os.environ:
        test_env["ANSIBLE_LOG_PATH"] = os.path.join(
            test_env["TEST_ARTIFACTS"], "ansible.log"
        )
    os.makedirs(test_env["TEST_ARTIFACTS"], exist_ok=True)

    ansible_args = []
    playbooks = []
    if "--" in args.ansible_args:
        ary = ansible_args
    else:
        ary = playbooks
    for item in args.ansible_args:
        if item == "--":
            ary = playbooks
        else:
            ary.append(item)

    # the cwd for the playbook process is the directory
    # of the first playbook - so that we can find the
    # provision.fmf, if any - this means we have to use
    # abs paths for the playbooks
    playbooks = [os.path.abspath(pth) for pth in playbooks]
    cwd = os.path.dirname(playbooks[0])
    subprocess.check_call(  # nosec
        [
            "ansible-playbook",
            "-vv",
            f"--inventory={args.inventory}",
        ]
        + ansible_args
        + [setup_yml]
        + playbooks,
        env=test_env,
        cwd=cwd,
    )


def install_requirements(args, test_env):
    """Install reqs from meta/requirements.yml, if any."""
    if os.path.isfile("meta/requirements.yml"):
        subprocess.check_call(  # nosec
            [
                "ansible-galaxy",
                "collection",
                "install",
                "-p",
                args.collection_base_path,
                "-vv",
                "-r",
                "meta/requirements.yml",
            ],
        )
        test_env["ANSIBLE_COLLECTIONS_PATHS"] = args.collection_base_path


def setup_callback_plugins(args, test_env):
    """Install and configure debug and profile_tasks."""
    if args.pretty or args.profile:
        callback_plugin_dir = os.path.join(
            os.environ["TOX_WORK_DIR"], "callback_plugins"
        )
        os.makedirs(callback_plugin_dir, exist_ok=True)
        debug_py = os.path.join(callback_plugin_dir, "debug.py")
        profile_py = os.path.join(callback_plugin_dir, "profile_tasks.py")
        if (args.pretty and not os.path.isfile(debug_py)) or (
            args.profile and not os.path.isfile(profile_py)
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
            if args.pretty:
                if not os.path.isfile(debug_py):
                    os.rename(tmp_debug_py, debug_py)
            if args.profile:
                if not os.path.isfile(profile_py):
                    os.rename(tmp_profile_py, profile_py)
            shutil.rmtree(
                os.path.join(
                    os.environ["LSR_TOX_ENV_TMP_DIR"], "ansible_collections"
                )
            )
        if args.pretty:
            test_env["ANSIBLE_STDOUT_CALLBACK"] = "debug"
        if args.profile:
            test_env["ANSIBLE_CALLBACKS_ENABLED"] = "profile_tasks"
            test_env["ANSIBLE_CALLBACK_WHITELIST"] = "profile_tasks"
        test_env["ANSIBLE_CALLBACK_PLUGINS"] = callback_plugin_dir


def help_epilog():
    """Additional help for arguments."""
    return """Any remaining arguments are passed directly to
    ansible-playbook - these may be ansible-playbook arguments,
    or one or more playbooks.  If you specify both arguments and
    playbooks, you must separate them by using -- on the command
    line e.g. --become root -- tests_default.yml.  If you do not
    use the --, then the script assumes all arguments are
    playbooks."""


def main():
    """Execute the main function."""
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
    # any remaining args are assumed to be ansible-playbook args or playbooks
    args, ansible_args = parser.parse_known_args()
    args.ansible_args = ansible_args

    # either image-name or image-file must be given
    if not any([args.image_name, args.image_file]) or all(
        [args.image_name, args.image_file]
    ):
        logging.critical(
            "One, and only one, of --image-name or --image-file must be given."
        )
        sys.exit(1)
    os.makedirs(args.cache, exist_ok=True)

    image = get_image_config(args)
    setup_yml = make_setup_yml(image, args)
    args.collection_base_path = os.environ["TOX_WORK_DIR"]
    test_env = image.get("env", {})
    install_requirements(args, test_env)
    get_inventory_script(args)
    setup_callback_plugins(args, test_env)
    run_ansible_playbooks(args, image, setup_yml, test_env)


if __name__ == "__main__":
    main()
