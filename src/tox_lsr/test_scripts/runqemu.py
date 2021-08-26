#!/usr/bin/env python
"""Launch qemu tests."""

import argparse
import errno
import glob
import json
import logging
import os
import shlex
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


def make_setup_yml(image):
    """Make a temp setup.yml to setup the VM."""
    setup_yml = tempfile.NamedTemporaryFile(
        prefix="lsr_setup_", suffix=".yml", mode="w", delete=False
    )
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

    yaml.safe_dump(setup_plays, setup_yml.file)
    setup_yml.file.close()
    return setup_yml.name


def run_test_playbooks(args, image, setup_yml):
    """Run the test playbooks."""
    testenv = {
        "TEST_SUBJECTS": image["file"],
    }
    if args.debug:
        testenv["TEST_DEBUG"] = "true"
    if args.image_alias:
        testenv["TEST_HOSTALIASES"] = args.image_alias
    testenv.update(dict(os.environ))
    for playbook_pattern in args.playbook:
        playbooks = glob.glob(playbook_pattern)
        if not playbooks:
            playbooks = glob.glob("tests/" + playbook_pattern)
        for playbook in playbooks:
            playbook_dir = os.path.dirname(playbook)
            if not playbook_dir:
                playbook_dir = os.getcwd()
            if args.artifacts:
                testenv["TEST_ARTIFACTS"] = args.artifacts
            else:
                testenv["TEST_ARTIFACTS"] = os.path.join(
                    playbook_dir, "artifacts"
                )
            if "ANSIBLE_LOG_PATH" not in os.environ:
                testenv["ANSIBLE_LOG_PATH"] = os.path.join(
                    testenv["TEST_ARTIFACTS"], "ansible.log"
                )
                os.makedirs(testenv["TEST_ARTIFACTS"], exist_ok=True)

            subprocess.check_call(  # nosec
                [
                    "ansible-playbook",
                    "-vv",
                    f"--inventory={args.inventory}",
                    setup_yml,
                    playbook,
                ],
                env=testenv,
                cwd=playbook_dir,
            )


def main():
    """Execute the main function."""
    parser = argparse.ArgumentParser()
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
            "/usr/share/ansible/inventory/standard-inventory-qcow2",
        ),
        help="Inventory to use for VMs",
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
        "playbook",
        nargs="+",
        default=shlex.split(os.environ.get("LSR_QEMU_PLAYBOOKS", "")),
        help=(
            "Test playbook or playbooks to run.  You can specify a glob "
            "wildcard e.g. tests/tests_feature*.yml.  If you do not specify "
            "the directory, the playbooks will be looked for in the 'tests/' "
            "directory."
        ),
    )
    args = parser.parse_args()

    # either image-name or image-file must be given
    if not any([args.image_name, args.image_file]) or all(
        [args.image_name, args.image_file]
    ):
        logging.critical(
            "One, and only one, of --image-name or --image-file must be given."
        )
        sys.exit(1)
    os.makedirs(args.cache, exist_ok=True)

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

    try:
        setup_yml = make_setup_yml(image)
        run_test_playbooks(args, image, setup_yml)
    finally:
        os.unlink(setup_yml)


if __name__ == "__main__":
    main()
