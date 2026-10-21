#!/usr/bin/env python
"""Install missing collection requirements in a cache shared by roles."""

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess  # nosec B404
import sys
import time

try:
    from urllib.request import urlopen
except ImportError:
    from urllib2 import urlopen

import yaml

string_types = (type(""), type(b"".decode("utf-8")))
GALAXY_VERSIONS_URL = (
    "https://galaxy.ansible.com/api/v3/plugin/ansible/content/published/"
    "collections/index/{namespace}/{collection}/versions/"
)


def cache_path():
    """Return the base path used by Ansible (parent of ansible_collections)."""
    return os.path.expanduser(
        os.environ.get("LSR_COLLECTIONS_CACHE", "~/.cache/linux-system-roles")
    )


def galaxy_environment(base):
    """Use only the cache for Galaxy's installed-collection search."""
    output = subprocess.check_output(  # nosec
        ["ansible-config", "list"], stderr=subprocess.STDOUT
    )
    if not isinstance(output, string_types):
        output = output.decode("utf-8")
    path_var = "ANSIBLE_COLLECTIONS_PATHS"
    if re.search(r"name: ANSIBLE_COLLECTIONS_PATH\s*$", output, re.M):
        path_var = "ANSIBLE_COLLECTIONS_PATH"
    env = os.environ.copy()
    env.pop("ANSIBLE_COLLECTIONS_PATH", None)
    env.pop("ANSIBLE_COLLECTIONS_PATHS", None)
    env[path_var] = base
    env["ANSIBLE_COLLECTIONS_SCAN_SYS_PATH"] = "false"
    return env


def installed_version(base, name):
    """Read the version only from a complete Galaxy installation."""
    parts = name.split(".")
    if len(parts) != 2:
        return None
    manifest = os.path.join(
        base, "ansible_collections", parts[0], parts[1], "MANIFEST.json"
    )
    try:
        with open(manifest) as stream:
            return json.load(stream)["collection_info"]["version"]
    except (IOError, ValueError, KeyError):
        return None


def update_interval_seconds():
    """Return the interval between remote version checks."""
    days = int(os.environ.get("LSR_COLLECTIONS_UPDATE_INTERVAL_DAYS", "7"))
    if days < 0:
        raise ValueError("LSR_COLLECTIONS_UPDATE_INTERVAL_DAYS must be >= 0")
    return days * 86400


def check_marker(base, name):
    """Return the file recording the last successful remote check."""
    return os.path.join(base, ".collection-checks", name)


def check_is_due(base, name, interval, now):
    """Decide whether a cached collection needs a Galaxy version check."""
    manifest = os.path.join(base, "ansible_collections", *name.split("."))
    manifest = os.path.join(manifest, "MANIFEST.json")
    marker = check_marker(base, name)
    checked = os.path.getmtime(marker if os.path.isfile(marker) else manifest)
    return now - checked >= interval


def record_check(base, name, now):
    """Record a successful Galaxy version check."""
    marker = check_marker(base, name)
    directory = os.path.dirname(marker)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    with open(marker, "a"):
        pass
    os.utime(marker, (now, now))


def newer_version(candidate, current):
    """Compare collection versions, including prerelease identifiers."""
    try:
        from packaging.version import Version

        candidate_version = Version(candidate)
        return (
            not candidate_version.is_prerelease
            and candidate_version > Version(current)
        )
    except ImportError:
        if not re.match(r"^\d+(?:\.\d+)*$", candidate):
            return False
        if not re.match(r"^\d+(?:\.\d+)*$", current):
            return False
        left = tuple(int(part) for part in candidate.split("."))
        right = tuple(int(part) for part in current.split("."))
        length = max(len(left), len(right))
        return left + (0,) * (length - len(left)) > right + (0,) * (
            length - len(right)
        )
    except ValueError:
        return False


def latest_allowed_version(name, current, constraint):
    """Find a newer allowed version from Galaxy's paginated API."""
    try:
        from ansible import __version__ as ansible_version
    except ImportError:
        ansible_version = None
    namespace, collection = name.split(".")
    url = (
        GALAXY_VERSIONS_URL.format(namespace=namespace, collection=collection)
        + "?limit=100&offset={}"
    )
    offset = 0
    latest = None
    while True:
        response = urlopen(url.format(offset), timeout=10)  # nosec B310
        try:
            data = json.load(response)
        finally:
            response.close()
        versions = data.get("data", [])
        for item in versions:
            candidate = item.get("version")
            if not candidate or not newer_version(candidate, current):
                continue
            if not version_matches(candidate, constraint):
                continue
            requires_ansible = item.get("requires_ansible")
            if (
                ansible_version
                and requires_ansible
                and not version_matches(ansible_version, requires_ansible)
            ):
                continue
            if not latest or newer_version(candidate, latest):
                latest = candidate
        if not data.get("links", {}).get("next") or not versions:
            return latest
        offset += len(versions)


def is_exact_version(constraint):
    """Exact pins have no newer allowed version."""
    return bool(constraint and re.match(r"^(?:==)?\d+(?:\.\d+)*$", constraint))


def update_for_cached_collection(base, name, current, constraint, interval):
    """Return a newer version when the periodic Galaxy check finds one."""
    if is_exact_version(constraint) or not check_is_due(
        base, name, interval, time.time()
    ):
        return None
    try:
        latest = latest_allowed_version(name, current, constraint)
    except (IOError, ValueError, KeyError) as exc:
        sys.stderr.write(
            "Could not check Galaxy for {}: {}\n".format(name, exc)
        )
        return None
    if not latest:
        record_check(base, name, time.time())
    return latest


def version_matches(installed, constraint):  # noqa: C901
    """Check Galaxy version constraints, including ranges and wildcards."""
    if not installed:
        return False
    if not constraint or constraint == "*":
        return True
    if re.match(r"^\d", constraint):
        constraint = "==" + constraint
    try:
        from packaging.specifiers import SpecifierSet

        return SpecifierSet(constraint).contains(installed, prereleases=True)
    except ImportError:
        # Ansible 2.9 environments may not include packaging. Galaxy versions
        # are numeric in the usual requirements; be conservative otherwise.
        match = re.match(r"^\d+(?:\.\d+)*$", installed)
        if not match:
            return False
        current = tuple(int(part) for part in installed.split("."))
        for item in constraint.split(","):
            item = item.strip()
            match = re.match(
                r"^(>=|<=|==|!=|>|<|~=)?(\d+(?:\.\d+)*)(\.\*)?$", item
            )
            if not match:
                return False
            operator, version, wildcard = match.groups()
            target = tuple(int(part) for part in version.split("."))
            length = max(len(current), len(target))
            left = current + (0,) * (length - len(current))
            right = target + (0,) * (length - len(target))
            if wildcard:
                equal = current[: len(target)] == target
            else:
                equal = left == right
            if operator in (None, "==") and not equal:
                return False
            if operator == "!=" and equal:
                return False
            if operator == ">=" and left < right:
                return False
            if operator == ">" and left <= right:
                return False
            if operator == "<=" and left > right:
                return False
            if operator == "<" and left >= right:
                return False
            if operator == "~=" and (
                left < right or current[: len(target) - 1] != target[:-1]
            ):
                return False
        return True
    except ValueError:
        return False


def requirements(files, collections):
    """Yield named Galaxy requirements from files and command arguments."""
    for item in collections:
        match = re.match(r"^([A-Za-z0-9_]+\.[A-Za-z0-9_]+)(.*)$", item)
        if not match:
            raise ValueError("Unsupported collection requirement: " + item)
        name, version = match.groups()
        version = version.lstrip(":")
        yield name, version or None
    for path in files:
        if not os.path.isfile(path):
            continue
        with open(path) as stream:
            data = yaml.safe_load(stream) or {}
        for item in data.get("collections", []):
            if isinstance(item, string_types):
                match = re.match(
                    r"^([A-Za-z0-9_]+\.[A-Za-z0-9_]+)(?::(.*))?$", item
                )
                if match:
                    yield match.group(1), match.group(2)
                else:
                    yield item, None
            elif isinstance(item, dict):
                yield item.get("name"), item.get("version")


def ensure_collection(base, name, version, interval, force, galaxy_env):
    """Reuse or install one requirement, returning the Galaxy environment."""
    current = installed_version(base, name)
    if not force and version_matches(current, version):
        latest = update_for_cached_collection(
            base, name, current, version, interval
        )
        if not latest:
            sys.stdout.write(
                "Using cached collection {} {}\n".format(name, current)
            )
            return galaxy_env
        version = latest
    spec = name + (":" + version if version else "")
    cmd = ["ansible-galaxy", "collection", "install", "-p", base]
    collection_dir = os.path.join(
        base, "ansible_collections", *name.split(".")
    )
    if galaxy_env is None:
        galaxy_env = galaxy_environment(base)
    if force and os.path.isdir(collection_dir):
        shutil.rmtree(collection_dir)
    elif os.path.isdir(collection_dir):
        cmd.append("--force")
    cmd.append(spec)
    sys.stdout.write("Installing collection {} in {}\n".format(spec, base))
    sys.stdout.flush()
    subprocess.check_call(cmd, env=galaxy_env)  # nosec B603
    record_check(base, name, time.time())
    return galaxy_env


def install(base, files, collections, excluded, force=False):
    """Check under a lock before asking Galaxy to install anything."""
    interval = update_interval_seconds()
    if not os.path.isdir(base):
        try:
            os.makedirs(base)
        except OSError:
            if not os.path.isdir(base):
                raise
    with open(os.path.join(base, ".collection-install.lock"), "a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        galaxy_env = None
        seen_specs = set()
        for name, version in requirements(files, collections):
            if not name or name in excluded:
                continue
            if (name, version) in seen_specs:
                continue
            seen_specs.add((name, version))
            # Paths and SCM URLs have no stable namespace/name to look up.
            if not re.match(r"^[A-Za-z0-9_]+\.[A-Za-z0-9_]+$", name):
                raise ValueError("Unsupported collection requirement: " + name)
            galaxy_env = ensure_collection(
                base, name, version, interval, force, galaxy_env
            )


def main():
    """Parse CLI arguments and install any missing requirements."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--requirements", action="append", default=[])
    parser.add_argument("--collection", action="append", default=[])
    parser.add_argument("--exclude", action="append", default=[])
    parser.add_argument(
        "--force",
        action="store_true",
        help="Remove named cached collections before installing them",
    )
    args = parser.parse_args()
    install(
        cache_path(),
        args.requirements,
        args.collection,
        args.exclude,
        args.force,
    )


if __name__ == "__main__":
    main()
