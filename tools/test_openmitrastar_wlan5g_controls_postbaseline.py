#!/usr/bin/env python3

import hashlib
import json
import pathlib
import subprocess
import tarfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD = ROOT / "tools/build_openmitrastar_wlan5g_controls_postbaseline.sh"
RUNNER = ROOT / "tools/run_openmitrastar_wlan5g_controls_postbaseline.py"
ARTIFACT = ROOT / "outputs/kernel-port/hgw500-controls-5g-postbaseline-20260819"
BASELINE = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-qdrv-sequential-20260819"
BASELINE_QDRV = BASELINE / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko"
BASELINE_SHA = "32956592ad32a6eadf12632e84495acaa18dd668184959c23acee0b8d0e31000"


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module_hashes(path: pathlib.Path) -> dict[str, str]:
    rows = path.read_text(encoding="utf-8").splitlines()[1:]
    return {row.split("\t")[0]: row.split("\t")[1] for row in rows}


class Wlan5gPostbaselineTests(unittest.TestCase):
    def test_approved_baseline_is_immutable(self):
        self.assertEqual(sha256(BASELINE_QDRV), BASELINE_SHA)

    def test_build_script_is_offline_and_pins_all_preimages(self):
        text = BUILD.read_text(encoding="utf-8")
        for marker in (
            "baseline_qdrv_sha=32956592",
            "recovery_preimage_sha=244abf7b",
            "dts_preimage_sha=69718c1f",
            "qdrv_vap_preimage_sha=c65d0190",
            "qdrv_wlan_hrflags_sha=8ddbd4e8",
            "OMQDRVHR stage=deferred reason=no-vap",
            "W1_HARDWARE_EXECUTED=0",
            "W1_FLASH_WRITES=0",
        ):
            self.assertIn(marker, text)
        for forbidden in ("bootm ", "tftp ", "paramiko", "pyserial", "/dev/tty"):
            self.assertNotIn(forbidden, text.lower())

    def test_runner_has_no_execute_or_hardware_path(self):
        text = RUNNER.read_text(encoding="utf-8")
        self.assertNotIn("--execute", text)
        self.assertNotIn("serial.Serial", text)
        self.assertNotIn("paramiko", text)
        self.assertIn("W1_LED5G_CONTROLS_POSTBASELINE_DRY_RUN_PASS=1", text)

    def test_manifest_is_fail_closed(self):
        manifest = json.loads((ARTIFACT / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["classification"], "OFFLINE-POSTBASELINE-NO-HARDWARE-NO-FLASH")
        self.assertEqual(manifest["execution"], {
            "hardware_executed": False,
            "com3_opened": False,
            "network_mutated": False,
            "flash_writes": 0,
        })
        self.assertTrue(manifest["baseline"]["immutable"])
        self.assertEqual(manifest["baseline"]["qdrv_sha256"], BASELINE_SHA)

    def test_only_qdrv_module_changes(self):
        before = module_hashes(BASELINE / "module-manifest.tsv")
        after = module_hashes(ARTIFACT / "module-manifest.tsv")
        self.assertEqual(set(before), set(after))
        self.assertEqual(len(after), 25)
        changed = [name for name in after if after[name] != before[name]]
        self.assertEqual(changed, ["qdrv/qdrv.ko"])

    def test_hrflags_and_led_markers_coexist(self):
        qdrv = ARTIFACT / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko"
        data = qdrv.read_bytes()
        for marker in (
            b"OMQDRVHR stage=deferred reason=no-vap",
            b"OMQDRVLED stage=vnet-start carrier=off",
            b"OMQDRVLED stage=ap-state carrier=%s",
        ):
            self.assertIn(marker, data)

    def test_rootfs_archive_contains_postbaseline_qdrv(self):
        qdrv = ARTIFACT / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko"
        with tarfile.open(ARTIFACT / "quantenna-rootfs-overlay.tar.gz", "r:gz") as bundle:
            archived = bundle.extractfile(
                "./lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko"
            )
            self.assertIsNotNone(archived)
            self.assertEqual(hashlib.sha256(archived.read()).hexdigest(), sha256(qdrv))

    def test_dry_run_runner_passes(self):
        completed = subprocess.run(
            ["python", str(RUNNER), "--json"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertIn("W1_LED5G_CONTROLS_POSTBASELINE_DRY_RUN_PASS=1", completed.stdout)


if __name__ == "__main__":
    unittest.main()
