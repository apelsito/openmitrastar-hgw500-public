#!/usr/bin/env python3
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_qtn_w3_qdrv_sequential_bringup.py"
REMOTE = ROOT / "tools/qtn_w3_qdrv_sequential_bringup_remote.sh"
CLOSED = ROOT / "work/mission-state/w3-offline/W3_QDRV_SEQUENTIAL_BRINGUP_GATE.env"
APPROVED = ROOT / "work/mission-state/w3-offline/W3_QDRV_SEQUENTIAL_BRINGUP_GATE.approved.env"
CONTROL = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_control.c"
MODULE = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_module.c"
PRIVATE = ROOT / "work/secrets-backup/20260725-161724-text/mnt__jffs2__wifi_mac_addrs"
POWER = ROOT / "work/hgw500-rootfs-live/squashfs-root/etc/power_tables"


def gate(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text().splitlines()
                if line and "=" in line)


class QdrvSequentialBringupTests(unittest.TestCase):
    def test_gate_pair_and_closed_surfaces(self):
        closed = CLOSED.read_text()
        approved = APPROVED.read_text()
        transformed = closed.replace("W3_QDRV_SEQUENTIAL_BRINGUP_APPROVED=0",
                                     "W3_QDRV_SEQUENTIAL_BRINGUP_APPROVED=1").replace(
            "QDRV_SEQUENTIAL_BRINGUP_NOT_APPROVED", "QDRV_SEQUENTIAL_BRINGUP_ONE_SHOT_APPROVED")
        self.assertEqual(transformed, approved)
        values = gate(CLOSED)
        self.assertEqual(values["W3_QDRV_LOAD_COUNT"], "1")
        self.assertEqual(values["W3_QDRV_COMMAND_COUNT"], "10")
        self.assertEqual(values["W3_VAP_CREATE_COUNT"], "1")
        self.assertEqual(values["W3_NO_RMMOD"], "1")
        for key in ("W3_RF_ENABLE", "W3_WIFI_ENABLE", "W3_VAP_ENABLE", "W3_FLASH_ENABLE"):
            self.assertEqual(values[key], "0")

    def test_source_enforces_exact_sequence(self):
        text = CONTROL.read_text()
        self.assertIn("openmitrastar_sequential_bringup", text)
        self.assertIn("qdrv_sequential_precheck", text)
        self.assertIn("OMQDRVSEQ_ALL_MASK", text)
        self.assertIn("reason=clearsram-order", text)
        self.assertIn("reason=start-order", text)
        self.assertIn("reason=already-started", text)
        self.assertIn("qdrv_sequential_note_success", text)
        self.assertIn("return qdrv_control_set_power_table_checksum", text)
        self.assertIn("openmitrastar_single_vap_create", text)
        self.assertIn("OMQDRVSEQ stage=vap-pass", text)
        self.assertIn("qdrv_openmitrastar_rf_gate_enabled", text)

    def test_shared_params_publishes_low_wire_bus_and_frees_original_dma(self):
        soc = (ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_soc.c").read_text()
        self.assertIn("static dma_addr_t params_dma_handle", soc)
        self.assertIn("static u32 params_wire_bus", soc)
        self.assertIn("virt_to_bus(", soc)
        self.assertIn("wire_bus >= RUBY_MAX_DRAM_SIZE", soc)
        self.assertIn("sizeof(*params_alloc) > RUBY_MAX_DRAM_SIZE - wire_bus", soc)
        self.assertIn("params_alloc_bus = (struct _shared_params_alloc *)(unsigned long)wire_bus", soc)
        self.assertIn("dma_free_coherent(", soc)
        self.assertIn("params_dma_handle);", soc)
        self.assertNotIn("(dma_addr_t)container_of(params_bus", soc)
        self.assertIn("OMQDRVSHM stage=wire-pass", soc)
        self.assertIn("OMQDRVSHM stage=publish-pass", soc)
        remote = REMOTE.read_text()
        self.assertIn("OMQDRVSHM stage=wire-pass", remote)
        self.assertIn("OMQDRVSHM stage=publish-pass", remote)
        self.assertIn("OMQDRVDESC stage=pool-create path=tx", remote)
        self.assertIn("OMQDRVDESC stage=pool-create path=rx", remote)

    def test_remote_loads_once_and_commands_are_exactly_ordered(self):
        text = REMOTE.read_text()
        self.assertEqual(len(re.findall(r"^load qdrv\.ko ", text, re.MULTILINE)), 1)
        calls = re.findall(r'^control_set (?:"([^"]+)"|(\S+)) ([0-9]+) ([\w-]+)$', text, re.MULTILINE)
        commands = [(quoted or bare, int(index), label) for quoted, bare, index, label in calls]
        self.assertEqual([index for _, index, _ in commands], list(range(1, 11)))
        self.assertEqual([label for _, _, label in commands], [
            "firmware-muc", "firmware-fw-no-mu", "firmware-auc", "firmware-dsp",
            "private-mac-redacted", "power-checksum", "checksum-lock", "clearsram", "core-start",
            "vap-create-private-mac",
        ])
        self.assertIn("openmitrastar_sequential_bringup=1", text)
        self.assertIn("openmitrastar_single_vap_create=1", text)
        self.assertIn("openmitrastar_rf_enable=0", text)
        self.assertIn('control_set "start 0 ap wifi0 $private_mac" 10', text)
        self.assertNotRegex(text, re.compile(r"\b(?:ifconfig|ip|iwconfig|iwpriv|hostapd)\b"))

    def test_no_unload_or_forced_recovery_actions(self):
        combined = REMOTE.read_text() + RUNNER.read_text()
        self.assertNotRegex(combined, re.compile(r"(?m)^\s*rmmod\b"))
        self.assertNotIn("uart_sysrq_reboot", combined)
        self.assertNotIn("run_product_rootfs_ram_candidate", combined)
        self.assertIn("waiting for watchdog", RUNNER.read_text())
        self.assertIn("qdrv_left_loaded=1", REMOTE.read_text())

    def test_control_only_exit_fast_path_is_preserved(self):
        text = MODULE.read_text()
        self.assertIn("OMQDRVEXIT stage=enter", text)
        self.assertIn("OMQDRVEXIT stage=stop-skipped reason=control-only resources=0", text)
        self.assertIn("if (qcb && qcb->resources)", text)
        self.assertLess(text.index("if (qcb && qcb->resources)"),
                        text.index('qdrv_control_input(&qdrv_device, "stop", 4)'))

    def test_private_mac_and_power_inputs_are_pinned_without_leak(self):
        secret = PRIVATE.read_text(encoding="ascii").splitlines()[0].strip()
        combined = RUNNER.read_text() + REMOTE.read_text() + CLOSED.read_text() + APPROVED.read_text()
        self.assertNotIn(secret, combined)
        self.assertIn("private_mac=redacted", REMOTE.read_text())
        values = gate(CLOSED)
        table = POWER / "tx_power_QSR1000_es.txt"
        self.assertEqual(hashlib.sha256(table.read_bytes()).hexdigest(), values["W3_POWER_TABLE_SHA256"])
        self.assertEqual(hashlib.md5(table.read_bytes()).hexdigest(), values["W3_POWER_TABLE_MD5"])

    def test_watchdog_uart_irq_and_management_contract(self):
        remote = REMOTE.read_text()
        runner = RUNNER.read_text()
        self.assertIn("OMWDT stage=armed", remote)
        self.assertIn("OMWDT stage=pet first=1", remote)
        for irq in (8, 9, 10):
            self.assertIn(f"hwirq=$irq", remote)
        self.assertIn("capture_topaz_uart.ps1", runner)
        self.assertIn("wait_for_watchdog", runner)
        self.assertIn("management=present", remote)
        self.assertIn("wifi0_not_down", remote)
        self.assertIn("irq_unstable", remote)
        self.assertIn("extra_vap", remote)

    def test_syntax_and_dry_run(self):
        self.assertEqual(subprocess.run([sys.executable, "-m", "py_compile", str(RUNNER)], cwd=ROOT).returncode, 0)
        self.assertEqual(subprocess.run(["wsl.exe", "sh", "-n", "/workspace/user-home/Desktop/MitraStar/tools/qtn_w3_qdrv_sequential_bringup_remote.sh"], cwd=ROOT).returncode, 0)
        dry = subprocess.run([sys.executable, str(RUNNER)], cwd=ROOT, text=True, capture_output=True)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        output = dry.stdout + dry.stderr
        self.assertNotIn(PRIVATE.read_text(encoding="ascii").splitlines()[0].strip(), output)
        self.assertIn("W3_QDRV_SEQUENTIAL_BRINGUP_DRY_RUN_PASS=1", output)


if __name__ == "__main__":
    unittest.main()
