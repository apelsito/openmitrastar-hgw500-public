#!/usr/bin/env python3

import pathlib
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
OM_SSH = ROOT / "work/mission-state/w4-rootfs-product/rootfs/usr/sbin/om-ssh"
OPTIONS = ROOT / "work/ssh-emulation/dropbear-ramssh-multiuser-noatomic-localoptions.h"
RUNNER = ROOT / "tools/run_product_rootfs_ram_candidate.ps1"
BUILDER = ROOT / "work/mission-state/w4-rootfs-product/scripts/build_product_rootfs.sh"
README = ROOT / "work/mission-state/w4-rootfs-product/README.md"
BINARY = "/home/user/openmitrastar-ssh-lab/dropbear-arc-multiuser-noatomic/dropbearmulti"


class ProductDropbearCliTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.om_ssh = OM_SSH.read_text(encoding="utf-8")
        cls.options = OPTIONS.read_text(encoding="utf-8")
        cls.runner = RUNNER.read_text(encoding="utf-8")
        cls.builder = BUILDER.read_text(encoding="utf-8")
        cls.readme = README.read_text(encoding="utf-8")

    def test_key_only_and_root_only_are_compile_time(self):
        self.assertIn("#define DROPBEAR_SVR_PASSWORD_AUTH 0", self.options)
        self.assertIn("#define DROPBEAR_SVR_PUBKEY_AUTH 1", self.options)
        self.assertIn("#define DROPBEAR_OPENMITRASTAR_ROOT_ONLY 1", self.options)

    def test_launch_uses_only_supported_security_flags(self):
        launch = next(line for line in self.om_ssh.splitlines() if "dropbearmulti dropbear -" in line)
        for supported in (" -j ", " -k ", " -D ", " -p ", " -r ", " -P "):
            self.assertIn(supported, launch)
        for unsupported in (" -E ", " -s ", " -g "):
            self.assertNotIn(unsupported, launch)

    def test_current_arc_binary_server_help_matches_launch(self):
        wsl = shutil.which("wsl.exe") or shutil.which("wsl")
        if not wsl:
            self.skipTest("WSL unavailable")
        result = subprocess.run(
            [wsl, "strings", BINARY], text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout)
        text = result.stdout
        self.assertIn("Dropbear SSH multi-purpose v%s", text)
        self.assertIn("-j\t\tDisable local port/stream forwarding", text)
        self.assertIn("-k\t\tDisable remote port/stream forwarding", text)
        self.assertIn("-D\t\tDirectory containing authorized_keys file", text)
        self.assertIn("(Syslog support not compiled in, using stderr)", text)
        self.assertNotIn("-E\t\tLog to standard error", text)
        self.assertNotIn("-s\t\tDisable password logins", text)
        self.assertNotIn("-g\t\tDisable password logins for root", text)

    def test_runner_rejects_stale_product_rootfs(self):
        self.assertIn("ProductManifestPath", self.runner)
        self.assertIn("Manifest.source_rootfs.sha256", self.runner)
        self.assertIn("Product RAM candidate is stale", self.runner)

    def test_getinfo_exposes_non_secret_build_identity(self):
        cgi = (ROOT / "work/mission-state/w4-rootfs-product/rootfs/usr/libexec/openmitrastar/om-oem-cgi").read_text(encoding="utf-8")
        release = (ROOT / "work/mission-state/w4-rootfs-product/rootfs/etc/openmitrastar/release").read_text(encoding="utf-8")
        self.assertIn("OPENMITRASTAR_BUILD_ID", release)
        self.assertIn("OPENMITRASTAR_BOOTSTRAP_AUTHORIZED_KEY_FINGERPRINT", release)
        self.assertIn("build_id", cgi)
        self.assertIn("bootstrap_authorized_key_fingerprint", cgi)

    def test_build_can_pin_expected_authorized_key_fingerprint(self):
        self.assertIn("OM_EXPECTED_AUTHORIZED_KEY_FINGERPRINT", self.builder)
        self.assertIn("authorized key fingerprint mismatch", self.builder)
        self.assertIn("/workspace/user-home/.ssh/id_ed25519.pub", self.readme)
        self.assertIn("SHA256:pBtUFbtw8ud9gGKqhXj3kBz2rhNv6syDjb7lvGwSoBc", self.readme)


if __name__ == "__main__":
    unittest.main()
