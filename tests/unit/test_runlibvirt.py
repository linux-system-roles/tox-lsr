#                                                         -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
#
"""Tests for per-hostname libvirt memory and vCPU settings."""

import os
import sys

try:
    from unittest2 import TestCase
except (ImportError, AttributeError):
    from unittest import TestCase

try:
    from unittest.mock import patch
except ImportError:
    from mock import patch

_SCRIPT_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        "..",
        "src",
        "tox_lsr",
        "test_scripts",
    )
)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

try:
    import runlibvirt  # isort: skip
except ImportError:
    runlibvirt = None

# Unit tests exercise the provisioner's internal methods directly.
# pylint: disable=protected-access


class _FakeNetwork(object):
    """Libvirt network stub that returns a fixed XML description."""

    def __init__(self, domain):
        """Store the DNS domain to advertise."""
        self.domain = domain

    def XMLDesc(self, unused_flags):  # pylint: disable=invalid-name
        """Return network XML containing an address and domain."""
        return (
            "<network><ip address='192.168.50.1' netmask='255.255.255.0'/>"
            "<domain name='" + str(self.domain) + "'/></network>"
        )


class _Args(object):
    """Argument stand-in for resolve_run_config."""

    def __init__(self, **kwargs):
        """Store the CLI fields used by hostname resource resolution."""
        self.hostnames = kwargs.get("hostnames", [])
        self.num_vms = kwargs.get("num_vms", 1)
        self.hostname_prefix = kwargs.get("hostname_prefix", "vm")
        self.memory = kwargs.get("memory", None)
        self.vcpus = kwargs.get("vcpus", None)


# pylint: disable-next=too-many-public-methods
class RunlibvirtResourcesTestCase(TestCase):
    """Per-hostname memory and vCPU configuration."""

    def setUp(self):
        """Skip when runlibvirt cannot be imported, and clear env overrides."""
        if runlibvirt is None:
            self.skipTest("runlibvirt dependencies are not installed")
        self._env = patch.dict(os.environ, {}, clear=False)
        self._env.start()
        os.environ.pop("LSR_LIBVIRT_MEMORY", None)
        os.environ.pop("LSR_LIBVIRT_VCPUS", None)
        os.environ.pop("LSR_LIBVIRT_DNS_DOMAIN", None)
        self.addCleanup(self._env.stop)

    def test_defaults_for_plain_hostnames(self):
        """Plain hostnames use the global memory and vCPU defaults."""
        hostnames, memory, vcpus = runlibvirt.resolve_run_config(
            _Args(hostnames=["server,client"])
        )
        self.assertEqual(["server", "client"], hostnames)
        self.assertEqual(runlibvirt.DEFAULT_MEMORY_MIB, memory)
        self.assertEqual(runlibvirt.DEFAULT_VCPUS, vcpus)

    def test_resources_embedded_in_hostnames(self):
        """hostname[:memory[:vcpus]] sets resources for that host only."""
        hostnames, memory, vcpus = runlibvirt.resolve_run_config(
            _Args(hostnames=["server:4096:4, client::1"])
        )
        self.assertEqual(["server", "client"], hostnames)
        self.assertEqual(
            {"*": runlibvirt.DEFAULT_MEMORY_MIB, "server": 4096}, memory
        )
        self.assertEqual(
            {"*": runlibvirt.DEFAULT_VCPUS, "server": 4, "client": 1}, vcpus
        )

    def test_memory_and_vcpus_flags_override_hostnames(self):
        """HOST=VALUE flags override resources embedded in --hostnames."""
        hostnames, memory, vcpus = runlibvirt.resolve_run_config(
            _Args(
                hostnames=["server:1024:1", "client"],
                memory=["3072", "server=4096"],
                vcpus=["client=4"],
            )
        )
        self.assertEqual(["server", "client"], hostnames)
        self.assertEqual({"*": 3072, "server": 4096}, memory)
        self.assertEqual({"*": 2, "server": 1, "client": 4}, vcpus)

    def test_generated_names_accept_per_host_flags(self):
        """--memory and --vcpus can target names produced by --num-vms."""
        hostnames, memory, vcpus = runlibvirt.resolve_run_config(
            _Args(num_vms=2, memory=["vm01=4096"], vcpus=["vm02=8"])
        )
        self.assertEqual(["vm01", "vm02"], hostnames)
        self.assertEqual(
            {"*": runlibvirt.DEFAULT_MEMORY_MIB, "vm01": 4096}, memory
        )
        self.assertEqual({"*": runlibvirt.DEFAULT_VCPUS, "vm02": 8}, vcpus)

    def test_unknown_hostname_is_rejected(self):
        """A resource for a hostname that will not be created is an error."""
        with self.assertRaises(ValueError):
            runlibvirt.resolve_run_config(
                _Args(hostnames=["server"], memory=["client=1024"])
            )

    def test_invalid_embedded_memory_is_rejected(self):
        """Memory and vCPU counts must be positive integers."""
        with self.assertRaises(ValueError):
            runlibvirt.resolve_run_config(_Args(hostnames=["server:0"]))
        with self.assertRaises(ValueError):
            runlibvirt.resolve_run_config(_Args(hostnames=["server:2048:2:1"]))

    def test_duplicate_hostname_is_rejected(self):
        """Resource syntax does not bypass duplicate hostname checks."""
        with self.assertRaises(ValueError):
            runlibvirt.resolve_run_config(
                _Args(hostnames=["server:2048,server:4096"])
            )

    def test_environment_sets_default_and_per_host_values(self):
        """LSR_LIBVIRT_MEMORY and LSR_LIBVIRT_VCPUS use the same syntax."""
        os.environ["LSR_LIBVIRT_MEMORY"] = "1024,server=8192"
        os.environ["LSR_LIBVIRT_VCPUS"] = "server=4"
        hostnames, memory, vcpus = runlibvirt.resolve_run_config(
            _Args(hostnames=["server,client"])
        )
        self.assertEqual(["server", "client"], hostnames)
        self.assertEqual({"*": 1024, "server": 8192}, memory)
        self.assertEqual({"*": runlibvirt.DEFAULT_VCPUS, "server": 4}, vcpus)

    def test_hostname_resources_override_environment(self):
        """Values in --hostnames win over LSR_LIBVIRT_MEMORY and VCPUS."""
        os.environ["LSR_LIBVIRT_MEMORY"] = "1024,server=8192"
        os.environ["LSR_LIBVIRT_VCPUS"] = "4,server=8"
        hostnames, memory, vcpus = runlibvirt.resolve_run_config(
            _Args(hostnames=["server:4096:2,client"])
        )
        self.assertEqual(["server", "client"], hostnames)
        self.assertEqual({"*": 1024, "server": 4096}, memory)
        self.assertEqual({"*": 4, "server": 2}, vcpus)

    def test_cli_replaces_environment(self):
        """Passing --memory replaces LSR_LIBVIRT_MEMORY entirely."""
        os.environ["LSR_LIBVIRT_MEMORY"] = "1024,server=8192"
        _hostnames, memory, _vcpus = runlibvirt.resolve_run_config(
            _Args(hostnames=["server"], memory=["4096"])
        )
        self.assertEqual(4096, memory)

    def test_narrow_host_resource_keeps_one_host(self):
        """Snapshot provisioning keeps the default and the first hostname."""
        value = {"*": 2048, "server": 4096, "client": 1024}
        self.assertEqual(
            {"*": 2048, "server": 4096},
            runlibvirt.narrow_host_resource(value, "server"),
        )
        self.assertEqual(
            2048, runlibvirt.narrow_host_resource({"*": 2048}, "server")
        )
        self.assertEqual(8, runlibvirt.narrow_host_resource(8, "server"))

    def test_split_host_resource_rejects_unknown_and_bool(self):
        """Mappings must name real hosts and use positive integers."""
        with self.assertRaises(ValueError):
            runlibvirt.split_host_resource(
                {"nope": 1}, 2048, "memory", ["server"]
            )
        with self.assertRaises(ValueError):
            runlibvirt.split_host_resource(True, 2048, "memory", ["server"])

    def _provisioner(self, **kwargs):
        """Return a provisioner without opening a libvirt connection."""
        original = runlibvirt.libvirt
        if original is None:
            runlibvirt.libvirt = object()
            self.addCleanup(setattr, runlibvirt, "libvirt", original)
        params = {
            "image_path": __file__,
            "hostnames": ["server", "client"],
            # Fixed paths used by the provisioner configuration tests.
            "cache": "/tmp",  # nosec B108
            "artifacts": "/tmp",  # nosec B108
            "session_id": "abcd",
        }
        params.update(kwargs)
        return runlibvirt.LibvirtProvisioner(**params)

    def test_per_host_values_survive_fmf_default(self):
        """provision.fmf changes the default memory, not per-host values."""
        provisioner = self._provisioner(
            memory_mib={"*": 2048, "server": 4096},
            vcpus={"*": 2, "client": 1},
        )

        def fake_fmf(path, default=None, tests_dir=None):
            del tests_dir
            if path == ["qemu", "m"]:
                return "3072"
            return default

        with patch.object(runlibvirt, "fmf_get", side_effect=fake_fmf):
            provisioner._apply_fmf_config()
        self.assertEqual(4096, provisioner._memory_for_host("server"))
        self.assertEqual(3072, provisioner._memory_for_host("client"))
        self.assertEqual(2, provisioner._vcpus_for_host("server"))
        self.assertEqual(1, provisioner._vcpus_for_host("client"))
        xml = provisioner._domain_xml(
            "dom",
            "/disk.qcow2",
            "/cidata.iso",
            "52:54:00:00:00:01",
            memory_mib=provisioner._memory_for_host("server"),
            vcpu_count=provisioner._vcpus_for_host("client"),
        )
        self.assertIn("<memory unit='MiB'>4096</memory>", xml)
        self.assertIn("<vcpu placement='static'>1</vcpu>", xml)

    def test_parser_accepts_per_host_resources(self):
        """The CLI accepts both hostname suffixes and HOST=VALUE flags."""
        parser = runlibvirt.get_arg_parser()
        args, extra = parser.parse_known_args(
            [
                "--hostnames",
                "server:1024:1,client",
                "--memory",
                "3072",
                "--memory",
                "server=4096",
                "--vcpus",
                "client=4",
            ]
        )
        hostnames, memory, vcpus = runlibvirt.resolve_run_config(args)
        self.assertEqual([], extra)
        self.assertEqual(["server", "client"], hostnames)
        self.assertEqual({"*": 3072, "server": 4096}, memory)
        self.assertEqual({"*": 2, "server": 1, "client": 4}, vcpus)

    def test_normalize_dns_domain(self):
        """DNS domains are hostnames, and a trailing dot is removed."""
        self.assertIsNone(runlibvirt.normalize_dns_domain(None))
        self.assertIsNone(runlibvirt.normalize_dns_domain("  "))
        self.assertEqual(
            "example.test",
            runlibvirt.normalize_dns_domain(" example.test. "),
        )
        with self.assertRaises(ValueError):
            runlibvirt.normalize_dns_domain("not_a_domain")

    def test_explicit_dns_domain_is_kept(self):
        """A passed-in domain is used instead of the generated name."""
        provisioner = self._provisioner(
            dns_domain="lab.example", session_id="abcd"
        )
        provisioner._plan_network()
        self.assertEqual("lab.example", provisioner.dns_domain)
        self.assertTrue(provisioner.dns_domain_explicit)

    def test_generated_dns_domain(self):
        """The session id is used when no DNS domain is given."""
        provisioner = self._provisioner(session_id="abcd")
        provisioner._plan_network()
        self.assertEqual("lsr-abcd.test", provisioner.dns_domain)
        self.assertFalse(provisioner.dns_domain_explicit)

    def test_existing_network_domain_without_override(self):
        """An existing libvirt network supplies the domain by default."""
        provisioner = self._provisioner(session_id="abcd")
        provisioner.network_name = "default"
        provisioner.network = _FakeNetwork("lab.example")
        provisioner._plan_network()
        provisioner._parse_existing_network()
        self.assertEqual("lab.example", provisioner.dns_domain)

    def test_explicit_domain_overrides_existing_network(self):
        """--dns-domain wins over the domain on an existing network."""
        provisioner = self._provisioner(
            dns_domain="custom.test", session_id="abcd"
        )
        provisioner.network_name = "default"
        provisioner.network = _FakeNetwork("lab.example")
        with self.assertLogs(level="WARNING") as logs:
            provisioner._parse_existing_network()
        self.assertEqual("custom.test", provisioner.dns_domain)
        self.assertIn("lab.example", logs.output[0])
        self.assertIn("custom.test", logs.output[0])

    def test_parser_accepts_dns_domain(self):
        """--dns-domain is accepted and validated."""
        parser = runlibvirt.get_arg_parser()
        args, extra = parser.parse_known_args(
            ["--dns-domain", "example.test."]
        )
        self.assertEqual([], extra)
        self.assertEqual(
            "example.test", runlibvirt.normalize_dns_domain(args.dns_domain)
        )
