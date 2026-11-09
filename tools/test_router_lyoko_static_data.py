#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import sync_router_lyoko_static_data as sync_static


ROOT = Path(__file__).resolve().parents[1]
SYNC = ROOT / "tools/sync_router_lyoko_static_data.py"
LYOKO = ROOT / "work/mission-state/router-lyoko-v0"
DATA = LYOKO / "rootfs/var/www/lyoko-data"
MANIFEST = LYOKO / "manifest.json"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RouterLyokoStaticDataTests(unittest.TestCase):
    STATIC_NAMES = (
        "index.json",
        "mission-truth.json",
        "event-taxonomy.json",
        "sector-map.json",
        "evidence-bindings.json",
        "telemetry-contract.json",
        "safe-mode.json",
        "goal-audit.json",
        "GOAL_AUDIT.md",
        "aelita-mission-log.jsonl",
        "aelita-dialogue.json",
        "aelita-memory.json",
        "LATEST_MISSION.md",
        "AELITA_REENTRY_CHECKPOINT_20260822.md",
        "control-policy.json",
        "REALTEK_TX_TAXONOMY.md",
    )

    @classmethod
    def setUpClass(cls):
        proc = subprocess.run(
            [sys.executable, str(SYNC), "--check"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr or proc.stdout)

    def test_static_data_files_are_present_and_parseable(self):
        for name in self.STATIC_NAMES:
            self.assertTrue((DATA / name).is_file(), name)
        index = json.loads((DATA / "index.json").read_text(encoding="utf-8"))
        truth = json.loads((DATA / "mission-truth.json").read_text(encoding="utf-8"))
        event_taxonomy = json.loads((DATA / "event-taxonomy.json").read_text(encoding="utf-8"))
        audit = json.loads((DATA / "goal-audit.json").read_text(encoding="utf-8"))
        sector_map = json.loads((DATA / "sector-map.json").read_text(encoding="utf-8"))
        evidence_bindings = json.loads((DATA / "evidence-bindings.json").read_text(encoding="utf-8"))
        telemetry_contract = json.loads((DATA / "telemetry-contract.json").read_text(encoding="utf-8"))
        safe_mode = json.loads((DATA / "safe-mode.json").read_text(encoding="utf-8"))
        policy = json.loads((DATA / "control-policy.json").read_text(encoding="utf-8"))
        aelita_dialogue = json.loads((DATA / "aelita-dialogue.json").read_text(encoding="utf-8"))
        aelita_memory = json.loads((DATA / "aelita-memory.json").read_text(encoding="utf-8"))
        self.assertEqual(index["schema"], "router-lyoko.static-data/v1")
        self.assertEqual(truth["schema"], "router-lyoko.truth/v1")
        self.assertEqual(event_taxonomy["schema"], "router-lyoko.event-taxonomy/v1")
        self.assertEqual(
            event_taxonomy["classification"],
            "STATIC-READONLY-EVENT-TAXONOMY-NO-HARDWARE-PROOF",
        )
        self.assertFalse(event_taxonomy["safety"]["dashboard_executes_commands"])
        self.assertGreaterEqual(len(event_taxonomy["events"]), 5)
        self.assertTrue(all(event.get("next_gate") for event in event_taxonomy["events"]))
        self.assertTrue(any(event["severity"] == "critical" for event in event_taxonomy["events"]))
        self.assertEqual(audit["schema"], "router-lyoko.goal-audit/v1")
        self.assertEqual(sector_map["schema"], "router-lyoko.sector-map/v1")
        self.assertFalse(sector_map["safety"]["executable_control"])
        self.assertGreaterEqual(len(sector_map["sectors"]), 7)
        self.assertGreaterEqual(len(sector_map["towers"]), 5)
        self.assertTrue(all(item.get("current_gate") for item in sector_map["sectors"]))
        self.assertEqual(evidence_bindings["schema"], "router-lyoko.evidence-bindings/v1")
        self.assertEqual(
            evidence_bindings["classification"],
            "STATIC-READONLY-EVIDENCE-BINDINGS-NO-HARDWARE-PROOF",
        )
        self.assertFalse(evidence_bindings["safety"]["dashboard_executes_commands"])
        self.assertTrue(any(item["hardware_proof"] for item in evidence_bindings["bindings"]))
        self.assertTrue(any(not item["hardware_proof"] for item in evidence_bindings["bindings"]))
        self.assertTrue(all(item.get("failure_mode") for item in evidence_bindings["bindings"]))
        self.assertEqual(telemetry_contract["schema"], "router-lyoko.telemetry-contract/v1")
        self.assertEqual(
            telemetry_contract["classification"],
            "STATIC-READONLY-TELEMETRY-CONTRACT-NO-HARDWARE-PROOF",
        )
        self.assertEqual(telemetry_contract["refresh_policy"]["dashboard_auto_refresh_seconds"], 5)
        self.assertFalse(telemetry_contract["safety"]["dashboard_executes_commands"])
        self.assertTrue(any(item["hardware_proof"] for item in telemetry_contract["runtime_fields"]))
        self.assertTrue(any(not item["hardware_proof"] for item in telemetry_contract["runtime_fields"]))
        self.assertEqual(safe_mode["schema"], "router-lyoko.safe-mode/v1")
        self.assertEqual(safe_mode["mode"], "observe_only")
        self.assertFalse(safe_mode["safety"]["dashboard_executes_commands"])
        self.assertEqual(safe_mode["ack_required"], "OPENMITRASTAR_RESUME_AFTER_TX7_HANG_READONLY")
        tx11_steps = [
            step
            for step in safe_mode["operator_sequence"]
            if step["id"] == "tx11-2g-client-gate-plan"
        ]
        self.assertEqual(len(tx11_steps), 1)
        self.assertTrue(tx11_steps[0]["requires_tx11_boot_evidence_json"])
        self.assertIn("Tx11BootEvidenceJson", tx11_steps[0]["display_command"])
        self.assertIn("w2-tx11-green-boot-controls-boot-evidence-latest.json", tx11_steps[0]["display_command"])
        self.assertFalse(audit["achieved"])
        self.assertEqual(policy["schema"], "router-lyoko.control-policy/v1")
        self.assertEqual(aelita_dialogue["schema"], "router-lyoko.aelita-dialogue/v1")
        self.assertEqual(
            aelita_dialogue["classification"],
            "STATIC-READONLY-DIALOGUE-CATALOG-NO-HARDWARE-PROOF",
        )
        self.assertFalse(aelita_dialogue["writes_device_now"])
        self.assertGreaterEqual(len(aelita_dialogue["lines"]), 5)
        self.assertTrue(all(line.get("condition") for line in aelita_dialogue["lines"]))
        self.assertTrue(all(line.get("source") for line in aelita_dialogue["lines"]))
        self.assertEqual(aelita_memory["schema"], "router-lyoko.aelita-memory/v1")
        self.assertEqual(
            aelita_memory["classification"],
            "STAGED-PERSISTENT-MEMORY-CONTRACT-NO-HARDWARE-PROOF",
        )
        self.assertFalse(aelita_memory["storage"]["writes_device_now"])
        self.assertGreaterEqual(len(aelita_memory["memory_slots"]), 4)
        self.assertTrue(aelita_memory["current_state"]["hardware_blocked"])
        events = [
            json.loads(line)
            for line in (DATA / "aelita-mission-log.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[-1]["classification"], "LAB-SIDE-MEMORY-NO-DEVICE-WRITE")
        reentry = (DATA / "AELITA_REENTRY_CHECKPOINT_20260822.md").read_text(encoding="utf-8")
        self.assertIn("OFFLINE-CHECKPOINT-NO-COM3-NO-FLASH-NO-REBOOT", reentry)
        self.assertIn("OMPOSTTX7_RECOVERY_PASS=1", reentry)
        self.assertIn("Tx11BootEvidenceJson", reentry)
        self.assertIn("w2-tx11-green-boot-controls-boot-evidence-latest.json", reentry)
        self.assertIn("NO_CLIENT", reentry)

    def test_static_data_is_manifested_with_exact_hashes(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        files = manifest["files"]
        for name in self.STATIC_NAMES:
            rel = f"rootfs/var/www/lyoko-data/{name}"
            self.assertIn(rel, files)
            path = LYOKO / Path(*rel.split("/"))
            self.assertEqual(path.stat().st_size, files[rel]["bytes"], rel)
            self.assertEqual(sha256_file(path), files[rel]["sha256"], rel)

    def test_sync_dry_run_does_not_modify_overlay_copy(self):
        before_manifest = sha256_file(MANIFEST)
        before_index = sha256_file(DATA / "index.json")
        proc = subprocess.run(
            [sys.executable, str(SYNC), "--dry-run"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(json.loads(proc.stdout)["dry_run"])
        self.assertEqual(before_manifest, sha256_file(MANIFEST))
        self.assertEqual(before_index, sha256_file(DATA / "index.json"))

    def test_sync_check_fails_closed_on_stale_source_copy(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            data_dir = tmp / "data"
            data_dir.mkdir()
            manifest = tmp / "manifest.json"
            sha256sums = tmp / "SHA256SUMS"
            generated = {
                "mission-truth.json": b'{"schema":"router-lyoko.truth/v1"}\n',
                "goal-audit.json": b'{"schema":"router-lyoko.goal-audit/v1"}\n',
            }
            for name, payload in generated.items():
                (data_dir / name).write_bytes(payload)
            (data_dir / "mission-truth.json").write_bytes(b'{"schema":"stale"}\n')
            manifest.write_text(
                json.dumps(
                    {
                        "files": {
                            "rootfs/var/www/lyoko-data/mission-truth.json": {
                                "bytes": 18,
                                "sha256": "stale",
                            },
                            "rootfs/var/www/lyoko-data/goal-audit.json": {
                                "bytes": len(generated["goal-audit.json"]),
                                "sha256": hashlib.sha256(generated["goal-audit.json"]).hexdigest(),
                            },
                        }
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            sha256sums.write_text("stale  rootfs/var/www/lyoko-data/mission-truth.json\n", encoding="utf-8")

            mismatches = sync_static.find_static_drift(
                generated,
                data_dir=data_dir,
                manifest_path=manifest,
                sha256sums_path=sha256sums,
            )

        kinds = {item["kind"] for item in mismatches}
        self.assertIn("served_file_drift", kinds)
        self.assertIn("manifest_drift", kinds)
        self.assertIn("sha256sums_drift", kinds)

    def test_sync_check_mode_does_not_modify_overlay_copy(self):
        before_manifest = sha256_file(MANIFEST)
        before_truth = sha256_file(DATA / "mission-truth.json")
        proc = subprocess.run(
            [sys.executable, str(SYNC), "--check"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        report = json.loads(proc.stdout)
        self.assertTrue(report["check"])
        self.assertFalse(report.get("mismatches"))
        self.assertEqual(before_manifest, sha256_file(MANIFEST))
        self.assertEqual(before_truth, sha256_file(DATA / "mission-truth.json"))


if __name__ == "__main__":
    unittest.main()
