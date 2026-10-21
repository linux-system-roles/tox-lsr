"""Tests for the shared collection installer."""

from __future__ import print_function

import io
import json
import os
import sys
import time
import types

try:
    import pytest
except ImportError as exc:
    print("Failed to import pytest:", exc)
    raise

pytest.importorskip("yaml")


SCRIPT = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "src",
    "tox_lsr",
    "test_scripts",
    "collection-cache.py",
)
try:
    import importlib.util
except ImportError:
    import imp  # pylint: disable=deprecated-module

    cache = imp.load_source("collection_cache", SCRIPT)
else:
    spec = importlib.util.spec_from_file_location("collection_cache", SCRIPT)
    cache = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cache)


def manifest(base, name, version):
    """Create a minimal installed Galaxy collection."""
    path = os.path.join(base, "ansible_collections", *name.split("."))
    os.makedirs(path)
    with io.open(
        os.path.join(path, "MANIFEST.json"), "w", encoding="utf-8"
    ) as stream:
        json.dump({"collection_info": {"version": version}}, stream)


def test_installed_collections_are_reused(tmpdir, monkeypatch):
    """Requirements from separate roles should need no Galaxy call."""
    base = str(tmpdir)
    manifest(base, "ansible.posix", "2.1.0")
    requirements = tmpdir.join("requirements.yml")
    requirements.write(
        "collections:\n  - name: ansible.posix\n"
        "    version: '>=2.1.0,<2.2.0'\n"
    )
    calls = []
    monkeypatch.setattr(cache.subprocess, "check_call", calls.append)
    cache.install(base, [str(requirements)], [], [])
    cache.install(base, [str(requirements)], [], [])
    assert not calls  # nosec B101


def test_missing_and_wrong_version_install(tmpdir, monkeypatch):
    """Only an absent or incompatible collection is installed."""
    base = str(tmpdir)
    manifest(base, "ansible.posix", "1.0.0")
    calls = []
    monkeypatch.setattr(
        cache.subprocess,
        "check_output",
        lambda *args, **kwargs: b"  name: ANSIBLE_COLLECTIONS_PATH\n",
    )
    monkeypatch.setattr(
        cache.subprocess,
        "check_call",
        lambda cmd, **kwargs: calls.append((cmd, kwargs["env"])),
    )
    cache.install(
        base, [], ["ansible.posix>=2.1.0,<2.2.0", "community.general"], []
    )
    assert calls[0][0][-2:] == [
        "--force",
        "ansible.posix:>=2.1.0,<2.2.0",
    ]  # nosec B101
    assert calls[1][0][-1] == "community.general"  # nosec B101
    for _, env in calls:
        assert env["ANSIBLE_COLLECTIONS_PATH"] == base  # nosec B101
        assert "ANSIBLE_COLLECTIONS_PATHS" not in env  # nosec B101
        scan_sys_path = env["ANSIBLE_COLLECTIONS_SCAN_SYS_PATH"]
        assert scan_sys_path == "false"  # nosec B101


def test_old_ansible_galaxy_uses_collections_paths(tmpdir, monkeypatch):
    """The installer selects the legacy Ansible variable when needed."""
    monkeypatch.setattr(
        cache.subprocess,
        "check_output",
        lambda *args, **kwargs: b"  name: ANSIBLE_COLLECTIONS_PATHS\n",
    )
    monkeypatch.setenv("ANSIBLE_COLLECTIONS_PATH", "/other")
    env = cache.galaxy_environment(str(tmpdir))
    assert env["ANSIBLE_COLLECTIONS_PATHS"] == str(tmpdir)  # nosec B101
    assert "ANSIBLE_COLLECTIONS_PATH" not in env  # nosec B101


def test_excluded_local_collection(tmpdir, monkeypatch):
    """The local build is never replaced by a cached Galaxy copy."""
    calls = []
    monkeypatch.setattr(cache.subprocess, "check_call", calls.append)
    cache.install(
        str(tmpdir),
        [],
        ["fedora.linux_system_roles"],
        ["fedora.linux_system_roles"],
    )
    assert not calls  # nosec B101


def test_local_collection_requirement_only_changes_cache(tmpdir, monkeypatch):
    """A local role collection requirement does not create a tox copy."""
    base = str(tmpdir.join("cache"))
    local_path = str(tmpdir.join("local"))
    monkeypatch.setenv("TOX_WORK_DIR", local_path)
    monkeypatch.setenv("TOXINIDIR", str(tmpdir.join("timesync")))
    calls = []
    monkeypatch.setattr(
        cache.subprocess,
        "check_output",
        lambda *args, **kwargs: b"name: ANSIBLE_COLLECTIONS_PATH\n",
    )

    def check_call(cmd, **kwargs):
        calls.append(cmd)
        assert kwargs["env"]["ANSIBLE_COLLECTIONS_PATH"] == base  # nosec B101
        manifest(base, "fedora.linux_system_roles", "2.5.0")

    monkeypatch.setattr(cache.subprocess, "check_call", check_call)
    cache.install(base, [], ["fedora.linux_system_roles:2.5.0"], [])
    assert calls[0][-1] == "fedora.linux_system_roles:2.5.0"  # nosec B101
    assert len(calls) == 1  # nosec B101
    assert not os.path.exists(local_path)  # nosec B101
    calls[:] = []
    cache.install(base, [], ["fedora.linux_system_roles:2.5.0"], [])
    assert not calls  # nosec B101
    assert not os.path.exists(local_path)  # nosec B101


def test_force_removes_cached_collection_before_install(tmpdir, monkeypatch):
    """Forced refresh starts from an empty collection directory."""
    base = str(tmpdir)
    manifest(base, "ansible.posix", "2.1.0")
    collection_dir = tmpdir.join("ansible_collections", "ansible", "posix")
    collection_dir.join("stale.txt").write("stale")
    monkeypatch.setattr(
        cache.subprocess,
        "check_output",
        lambda *args, **kwargs: b"name: ANSIBLE_COLLECTIONS_PATH\n",
    )
    calls = []

    def check_call(cmd, **kwargs):
        calls.append(cmd)
        assert kwargs["env"]["ANSIBLE_COLLECTIONS_PATH"] == base  # nosec B101
        assert not os.path.exists(str(collection_dir))  # nosec B101
        manifest(base, "ansible.posix", "2.1.0")

    monkeypatch.setattr(cache.subprocess, "check_call", check_call)
    cache.install(base, [], ["ansible.posix:2.1.0"], [], force=True)
    assert len(calls) == 1  # nosec B101
    assert calls[0][-1] == "ansible.posix:2.1.0"  # nosec B101
    assert "--force" not in calls[0]  # nosec B101
    assert not collection_dir.join("stale.txt").exists()  # nosec B101


def test_force_refresh_does_not_change_local_copy(tmpdir, monkeypatch):
    """Forced cache refresh also leaves the role checkout alone."""
    base = str(tmpdir.join("cache"))
    manifest(base, "fedora.linux_system_roles", "2.5.0")
    local_path = tmpdir.join("local", "ansible_collections", "fedora")
    local_path.ensure(dir=True)
    marker = local_path.join("keep")
    marker.write("keep")
    monkeypatch.setenv("TOX_WORK_DIR", str(tmpdir.join("local")))
    monkeypatch.setenv("TOXINIDIR", str(tmpdir.join("timesync")))
    monkeypatch.setattr(
        cache.subprocess,
        "check_output",
        lambda *args, **kwargs: b"name: ANSIBLE_COLLECTIONS_PATH\n",
    )
    calls = []

    def check_call(cmd, **kwargs):
        calls.append(cmd)
        assert kwargs["env"]["ANSIBLE_COLLECTIONS_PATH"] == base  # nosec B101
        manifest(base, "fedora.linux_system_roles", "2.5.0")

    monkeypatch.setattr(cache.subprocess, "check_call", check_call)
    cache.install(
        base, [], ["fedora.linux_system_roles:2.5.0"], [], force=True
    )
    assert len(calls) == 1  # nosec B101
    assert marker.read() == "keep"  # nosec B101


def test_stale_collection_installs_newer_version(tmpdir, monkeypatch):
    """A stale cache entry upgrades only after Galaxy reports a newer one."""
    base = str(tmpdir)
    manifest(base, "ansible.posix", "2.1.0")
    manifest_path = tmpdir.join(
        "ansible_collections", "ansible", "posix", "MANIFEST.json"
    )
    old = time.time() - 8 * 86400
    os.utime(str(manifest_path), (old, old))
    monkeypatch.setenv("LSR_COLLECTIONS_UPDATE_INTERVAL_DAYS", "7")
    monkeypatch.setattr(cache, "latest_allowed_version", lambda *args: "2.1.1")
    monkeypatch.setattr(
        cache.subprocess,
        "check_output",
        lambda *args, **kwargs: b"name: ANSIBLE_COLLECTIONS_PATH\n",
    )
    calls = []
    monkeypatch.setattr(
        cache.subprocess,
        "check_call",
        lambda cmd, **kwargs: calls.append(cmd),
    )
    cache.install(base, [], ["ansible.posix"], [])
    assert calls[0][-1] == "ansible.posix:2.1.1"  # nosec B101
    assert os.path.isfile(
        cache.check_marker(base, "ansible.posix")
    )  # nosec B101


def test_stale_collection_without_update_is_not_checked_again(
    tmpdir, monkeypatch
):
    """A successful check starts a new interval without a download."""
    base = str(tmpdir)
    manifest(base, "ansible.posix", "2.1.0")
    manifest_path = tmpdir.join(
        "ansible_collections", "ansible", "posix", "MANIFEST.json"
    )
    old = time.time() - 8 * 86400
    os.utime(str(manifest_path), (old, old))
    monkeypatch.setenv("LSR_COLLECTIONS_UPDATE_INTERVAL_DAYS", "7")
    checks = []
    monkeypatch.setattr(
        cache,
        "latest_allowed_version",
        lambda *args: checks.append(args),
    )
    calls = []
    monkeypatch.setattr(cache.subprocess, "check_call", calls.append)
    cache.install(base, [], ["ansible.posix"], [])
    cache.install(base, [], ["ansible.posix"], [])
    assert len(checks) == 1  # nosec B101
    assert not calls  # nosec B101


def test_exact_pin_does_not_check_galaxy(tmpdir, monkeypatch):
    """An exact requirement cannot be upgraded beyond its pin."""
    base = str(tmpdir)
    manifest(base, "ansible.posix", "2.1.0")
    monkeypatch.setenv("LSR_COLLECTIONS_UPDATE_INTERVAL_DAYS", "0")
    monkeypatch.setattr(
        cache,
        "latest_allowed_version",
        lambda *args: pytest.fail("exact pin checked Galaxy"),
    )
    cache.install(base, [], ["ansible.posix:2.1.0"], [])


def test_zero_interval_checks_fresh_collection(tmpdir, monkeypatch):
    """A zero day interval checks even a recently installed collection."""
    base = str(tmpdir)
    manifest(base, "ansible.posix", "2.1.0")
    monkeypatch.setenv("LSR_COLLECTIONS_UPDATE_INTERVAL_DAYS", "0")
    checks = []
    monkeypatch.setattr(
        cache, "latest_allowed_version", lambda *args: checks.append(args)
    )
    cache.install(base, [], ["ansible.posix"], [])
    assert len(checks) == 1  # nosec B101


def test_update_interval_requires_whole_days(monkeypatch):
    """Fractional and negative intervals are rejected."""
    monkeypatch.setenv("LSR_COLLECTIONS_UPDATE_INTERVAL_DAYS", "0.5")
    with pytest.raises(ValueError):
        cache.update_interval_seconds()
    monkeypatch.setenv("LSR_COLLECTIONS_UPDATE_INTERVAL_DAYS", "-1")
    with pytest.raises(ValueError):
        cache.update_interval_seconds()


def test_failed_lookup_is_retried(tmpdir, monkeypatch):
    """A network error leaves the cache in place and keeps its check due."""
    base = str(tmpdir)
    manifest(base, "ansible.posix", "2.1.0")
    monkeypatch.setenv("LSR_COLLECTIONS_UPDATE_INTERVAL_DAYS", "0")
    checks = []

    def fail_check(*args):
        checks.append(args)
        raise IOError("Galaxy unavailable")

    monkeypatch.setattr(cache, "latest_allowed_version", fail_check)
    cache.install(base, [], ["ansible.posix"], [])
    cache.install(base, [], ["ansible.posix"], [])
    assert len(checks) == 2  # nosec B101
    assert not os.path.exists(
        cache.check_marker(base, "ansible.posix")
    )  # nosec B101


def test_galaxy_versions_are_paginated_and_constrained(monkeypatch):
    """Select the newest version allowed by the requirement."""
    ansible = types.ModuleType("ansible")
    ansible.__version__ = "2.19.0"
    monkeypatch.setitem(sys.modules, "ansible", ansible)
    pages = [
        {"data": [{"version": "2.2.0"}], "links": {"next": "next"}},
        {
            "data": [
                {"version": "2.1.3-beta.1"},
                {"version": "2.1.2", "requires_ansible": ">=99.0.0"},
                {"version": "2.1.1"},
                {"version": "2.1.0"},
            ],
            "links": {"next": None},
        },
    ]
    monkeypatch.setattr(
        cache,
        "urlopen",
        lambda *args, **kwargs: io.BytesIO(json.dumps(pages.pop(0)).encode()),
    )
    latest = cache.latest_allowed_version(
        "ansible.posix", "2.1.0", ">=2.1.0,<2.2.0"
    )
    assert latest == "2.1.1"  # nosec B101
