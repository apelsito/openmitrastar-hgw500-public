#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "work/mission-state/router-lyoko-v0"
MANIFEST = OVERLAY / "manifest.json"
CGI = OVERLAY / "rootfs/var/www/api/lyoko"
JS = OVERLAY / "rootfs/var/www/lyoko.js"


FORBIDDEN = (
    "saveenv",
    "fw_setenv",
    "mtd_write ",
    "flashcp",
    "/dev/mtd",
    "dd if=",
    "dd of=",
    "insmod ",
    "rmmod ",
    "modprobe ",
    "reboot",
    "halt",
    "poweroff",
    "ifconfig br0 ",
    "ip addr add",
    "ip link set",
    "call_qcsapi ",
    "qweconfig set",
    "hostapd_cli ",
)


class RouterLyokoOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_manifest_hashes_and_sizes_match_files(self):
        for rel, meta in self.manifest["files"].items():
            path = OVERLAY / rel
            self.assertTrue(path.is_file(), rel)
            data = path.read_bytes()
            self.assertEqual(len(data), meta["bytes"], rel)
            self.assertEqual(hashlib.sha256(data).hexdigest(), meta["sha256"], rel)

    def test_overlay_is_declared_read_only(self):
        self.assertEqual(
            self.manifest["classification"],
            "READ-ONLY-LAB-OVERLAY-NO-FLASH",
        )
        for guard, value in self.manifest["guards"].items():
            self.assertFalse(value, guard)

    def test_no_forbidden_control_surface(self):
        text = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore")
            for path in (OVERLAY / "rootfs").rglob("*")
            if path.is_file()
        )
        for token in FORBIDDEN:
            self.assertNotIn(token, text, token)

    def test_cgi_shell_syntax_and_json_shape(self):
        if not shutil.which("wsl.exe"):
            self.skipTest("WSL unavailable")
        data_dir = "/workspace/user-home/Desktop/MitraStar/work/mission-state/router-lyoko-v0/rootfs/var/www/lyoko-data"
        cmd = (
            "cd /workspace/user-home/Desktop/MitraStar && "
            "sh -n work/mission-state/router-lyoko-v0/rootfs/var/www/api/lyoko && "
            f"LYOKO_DATA_DIR={data_dir} "
            "sh work/mission-state/router-lyoko-v0/rootfs/var/www/api/lyoko | "
            "sed '1,/^$/d'"
        )
        proc = subprocess.run(
            ["wsl.exe", "-e", "sh", "-lc", cmd],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["persona"]["name"], "Aelita")
        self.assertIn("bridge", payload["sectors"])
        self.assertEqual(
            payload["mission_data"]["classification"],
            "STATIC-READONLY-SNAPSHOT-NO-HARDWARE-PROOF",
        )
        self.assertTrue(payload["mission_data"]["mission_truth"]["present"])
        self.assertTrue(payload["mission_data"]["event_taxonomy"]["present"])
        self.assertGreater(payload["mission_data"]["mission_truth"]["bytes"], 0)
        self.assertTrue(payload["mission_data"]["goal_audit"]["present"])
        self.assertTrue(payload["mission_data"]["safe_mode"]["present"])
        self.assertTrue(payload["mission_data"]["aelita_mission_log"]["present"])
        self.assertTrue(payload["mission_data"]["aelita_dialogue"]["present"])
        self.assertTrue(payload["mission_data"]["aelita_memory"]["present"])
        self.assertTrue(payload["mission_data"]["evidence_bindings"]["present"])
        self.assertTrue(payload["mission_data"]["telemetry_contract"]["present"])
        self.assertTrue(payload["mission_data"]["control_policy"]["present"])
        self.assertEqual(payload["telemetry"]["classification"], "RUNTIME-OBSERVE-ONLY-NO-CONTROL")
        self.assertIsInstance(payload["telemetry"]["captured_at_epoch"], int)
        self.assertFalse(payload["telemetry"]["static_snapshot_is_hardware_proof"])
        self.assertEqual(payload["runtime_status"]["schema"], "router-lyoko.runtime-status/v1")
        self.assertIn("clients", payload["runtime_status"]["coverage"])
        self.assertIn("wlan0", payload["runtime_status"]["clients"])
        self.assertFalse(payload["runtime_status"]["recovery"]["flash_write_enabled"])
        self.assertEqual(payload["runtime_towers"]["schema"], "router-lyoko.runtime-towers/v1")
        self.assertFalse(payload["runtime_towers"]["control_surface_exposed"])
        self.assertIn("ssh", payload["runtime_towers"]["towers"])
        self.assertEqual(payload["runtime_towers"]["towers"]["ssh"]["service"], "dropbear")
        self.assertFalse(payload["runtime_towers"]["towers"]["ssh"]["control_enabled"])
        self.assertFalse(payload["runtime_towers"]["towers"]["ssh"]["writes_device"])
        self.assertEqual(payload["runtime_events"]["schema"], "router-lyoko.runtime-events/v1")
        self.assertFalse(payload["runtime_events"]["raw_logs_exposed"])
        self.assertIn("dmesg_tail_classified", payload["runtime_events"]["sources"])
        self.assertTrue(payload["runtime_events"]["events"])
        event_ids = {event["id"] for event in payload["runtime_events"]["events"]}
        self.assertIn("bridge.emac_polling_fallback", event_ids)
        self.assertIn("quantenna.muc_memory_fault", event_ids)
        self.assertFalse(payload["guards"]["mtd_write"])

    def test_javascript_syntax(self):
        if not shutil.which("node"):
            self.skipTest("node unavailable")
        proc = subprocess.run(
            ["node", "--check", str(JS)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout)

    def test_dashboard_mounts_goal_audit(self):
        html = (OVERLAY / "rootfs/var/www/lyoko.html").read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        self.assertIn('id="goal-audit"', html)
        self.assertIn("/lyoko-data/goal-audit.json", js)
        self.assertIn("renderGoalAudit", js)
        self.assertIn("m7_open_items", js)

    def test_dashboard_mounts_sector_map(self):
        html = (OVERLAY / "rootfs/var/www/lyoko.html").read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        self.assertIn('id="sector-map"', html)
        self.assertIn("/lyoko-data/sector-map.json", js)
        self.assertIn("renderSectorMap", js)
        self.assertIn("current_gate", js)
        self.assertIn("real_component", js)

    def test_dashboard_mounts_reentry_checkpoint(self):
        html = (OVERLAY / "rootfs/var/www/lyoko.html").read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        css = (OVERLAY / "rootfs/var/www/lyoko.css").read_text(encoding="utf-8")
        self.assertIn('id="reentry-checkpoint"', html)
        self.assertIn("/lyoko-data/AELITA_REENTRY_CHECKPOINT_20260822.md", js)
        self.assertIn("renderReentryCheckpoint", js)
        self.assertIn("NO_CLIENT", js)
        self.assertIn(".reentry-panel", css)

    def test_dashboard_mounts_mission_history(self):
        html = (OVERLAY / "rootfs/var/www/lyoko.html").read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        css = (OVERLAY / "rootfs/var/www/lyoko.css").read_text(encoding="utf-8")
        self.assertIn('id="mission-history"', html)
        self.assertIn("/lyoko-data/aelita-mission-log.jsonl", js)
        self.assertIn("renderMissionHistory", js)
        self.assertIn("summary?.next_gate", js)
        self.assertIn(".history-panel", css)

    def test_dashboard_mounts_aelita_memory_contract(self):
        html = (OVERLAY / "rootfs/var/www/lyoko.html").read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        css = (OVERLAY / "rootfs/var/www/lyoko.css").read_text(encoding="utf-8")
        self.assertIn('id="aelita-memory-contract"', html)
        self.assertIn("/lyoko-data/aelita-memory.json", js)
        self.assertIn("renderAelitaMemoryContract", js)
        self.assertIn("Memoria versionada", js)
        self.assertIn(".memory-contract-panel", css)

    def test_dashboard_mounts_aelita_dialogue_catalog(self):
        html = (OVERLAY / "rootfs/var/www/lyoko.html").read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        css = (OVERLAY / "rootfs/var/www/lyoko.css").read_text(encoding="utf-8")
        self.assertIn('id="aelita-dialogue"', html)
        self.assertIn("/lyoko-data/aelita-dialogue.json", js)
        self.assertIn("renderAelitaDialogue", js)
        self.assertIn("chooseDialogue", js)
        self.assertIn("hardware_claim", js)
        self.assertIn(".dialogue-panel", css)

    def test_dashboard_mounts_evidence_bindings(self):
        html = (OVERLAY / "rootfs/var/www/lyoko.html").read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        css = (OVERLAY / "rootfs/var/www/lyoko.css").read_text(encoding="utf-8")
        self.assertIn('id="evidence-bindings"', html)
        self.assertIn("/lyoko-data/evidence-bindings.json", js)
        self.assertIn("renderEvidenceBindings", js)
        self.assertIn("hardware_proof", js)
        self.assertIn(".evidence-panel", css)

    def test_dashboard_mounts_event_taxonomy(self):
        html = (OVERLAY / "rootfs/var/www/lyoko.html").read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        css = (OVERLAY / "rootfs/var/www/lyoko.css").read_text(encoding="utf-8")
        self.assertIn('id="event-taxonomy"', html)
        self.assertIn("/lyoko-data/event-taxonomy.json", js)
        self.assertIn("renderEventTaxonomy", js)
        self.assertIn("activeXanaEvents", js)
        self.assertIn("xana.quantenna.misaligned_access", js)
        self.assertIn(".event-panel", css)

    def test_dashboard_mounts_runtime_telemetry_pulse(self):
        html = (OVERLAY / "rootfs/var/www/lyoko.html").read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        css = (OVERLAY / "rootfs/var/www/lyoko.css").read_text(encoding="utf-8")
        self.assertIn('id="telemetry-pulse"', html)
        self.assertIn('id="telemetry-contract"', html)
        self.assertIn("/lyoko-data/telemetry-contract.json", js)
        self.assertIn("renderRuntimePulse", js)
        self.assertIn("AUTO_REFRESH_SECONDS", js)
        self.assertIn("static_snapshot_is_hardware_proof", js)
        self.assertIn(".telemetry-panel", css)
        self.assertIn("@keyframes pulse", css)

    def test_dashboard_mounts_runtime_status_coverage(self):
        html = (OVERLAY / "rootfs/var/www/lyoko.html").read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        css = (OVERLAY / "rootfs/var/www/lyoko.css").read_text(encoding="utf-8")
        bindings = json.loads((OVERLAY / "evidence-bindings.json").read_text(encoding="utf-8"))
        binding_ids = {binding["id"] for binding in bindings["bindings"]}
        self.assertIn('id="runtime-status"', html)
        self.assertIn("renderRuntimeStatus", js)
        self.assertIn("runtime_status", js)
        self.assertIn("wlan0_clients", js)
        self.assertIn("destructive_actions_allowed", js)
        self.assertIn(".runtime-status-panel", css)
        self.assertIn("live.runtime_status", binding_ids)

    def test_dashboard_mounts_runtime_recovery_guards(self):
        html = (OVERLAY / "rootfs/var/www/lyoko.html").read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        css = (OVERLAY / "rootfs/var/www/lyoko.css").read_text(encoding="utf-8")
        bindings = json.loads((OVERLAY / "evidence-bindings.json").read_text(encoding="utf-8"))
        binding_ids = {binding["id"] for binding in bindings["bindings"]}
        self.assertIn('id="runtime-recovery"', html)
        self.assertIn("renderRuntimeRecovery", js)
        self.assertIn("runtime_recovery", js)
        self.assertIn("hardware_recovery_proven_current_boot", js)
        self.assertIn("device_can_self_recover", js)
        self.assertIn(".runtime-recovery-panel", css)
        self.assertIn("live.runtime_recovery", binding_ids)

    def test_dashboard_mounts_runtime_towers_contract(self):
        html = (OVERLAY / "rootfs/var/www/lyoko.html").read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        bindings = json.loads((OVERLAY / "evidence-bindings.json").read_text(encoding="utf-8"))
        binding_ids = {binding["id"] for binding in bindings["bindings"]}
        self.assertIn('id="runtime-towers"', html)
        self.assertIn("renderRuntimeTowers", js)
        self.assertIn("runtime_towers", js)
        self.assertIn("control_surface_exposed", js)
        self.assertIn("writes_device", js)
        self.assertIn("live.runtime_towers", binding_ids)

    def test_dashboard_mounts_runtime_events_summary(self):
        html = (OVERLAY / "rootfs/var/www/lyoko.html").read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        css = (OVERLAY / "rootfs/var/www/lyoko.css").read_text(encoding="utf-8")
        bindings = json.loads((OVERLAY / "evidence-bindings.json").read_text(encoding="utf-8"))
        binding_ids = {binding["id"] for binding in bindings["bindings"]}
        self.assertIn('id="runtime-events"', html)
        self.assertIn("renderRuntimeEvents", js)
        self.assertIn("runtime_events", js)
        self.assertIn("raw_logs_exposed", js)
        self.assertIn("quantenna.muc_memory_fault", js)
        self.assertIn(".runtime-events-panel", css)
        self.assertIn("live.runtime_events", binding_ids)

    def test_dashboard_mounts_aelita_alerts_without_control(self):
        html = (OVERLAY / "rootfs/var/www/lyoko.html").read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        css = (OVERLAY / "rootfs/var/www/lyoko.css").read_text(encoding="utf-8")
        self.assertIn('id="aelita-alerts"', html)
        self.assertIn("renderAelitaAlerts", js)
        self.assertIn("PHYSICAL_POWER_CYCLE_REQUIRED", js)
        self.assertIn("NO_CLIENT", js)
        self.assertIn("Misaligned Access", js)
        self.assertIn(".alert-panel", css)

    def test_dashboard_mounts_lab_console_as_read_only_text(self):
        html = (OVERLAY / "rootfs/var/www/lyoko.html").read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        css = (OVERLAY / "rootfs/var/www/lyoko.css").read_text(encoding="utf-8")
        self.assertIn('id="lab-console"', html)
        self.assertIn("renderLabConsole", js)
        self.assertIn("/lyoko-data/safe-mode.json", js)
        self.assertIn("renderSafeModeContract", js)
        self.assertIn("operator_sequence", js)
        self.assertIn("safe-mode.json", js)
        self.assertIn("OPENMITRASTAR_RESUME_AFTER_TX7_HANG_READONLY", js)
        self.assertIn("collect_w2_tx11_boot_evidence.ps1", js)
        self.assertIn("run_w2_2g_tx11_gate.ps1", js)
        self.assertIn("Tx11BootEvidenceJson", js)
        self.assertIn("w2-tx11-green-boot-controls-boot-evidence-latest.json", js)
        self.assertIn("tx11_boot_evidence_json", js)
        self.assertIn("mutaciones", js)
        self.assertIn(".lab-panel", css)


if __name__ == "__main__":
    unittest.main()
