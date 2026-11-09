#!/usr/bin/env python3

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import verify_router_lyoko_aelita_memory as guard


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "verify_router_lyoko_aelita_memory.py"
DATA = ROOT / "work/mission-state/router-lyoko-v0/rootfs/var/www/lyoko-data"


def run_guard(data_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--data-dir", str(data_dir)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def copy_data_dir(tmp: Path) -> Path:
    dst = tmp / "lyoko-data"
    shutil.copytree(DATA, dst)
    return dst


def rewrite_index_for(data_dir: Path, name: str) -> None:
    path = data_dir / name
    payload = path.read_bytes()
    index_path = data_dir / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    index["files"][name] = {
        "bytes": len(payload),
        "sha256": guard.sha256_bytes(payload),
    }
    index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class RouterLyokoAelitaMemoryGuardTests(unittest.TestCase):
    def test_current_aelita_memory_passes(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["classification"], "READONLY-AELITA-MEMORY-GUARD-NO-HARDWARE")
        self.assertFalse(report["summary"]["writes_device_now"])
        self.assertTrue(report["summary"]["hardware_blocked"])

    def test_rejects_device_write_enabled_memory(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = copy_data_dir(Path(td))
            memory_path = data_dir / "aelita-memory.json"
            memory = json.loads(memory_path.read_text(encoding="utf-8"))
            memory["storage"]["writes_device_now"] = True
            memory_path.write_text(json.dumps(memory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            rewrite_index_for(data_dir, "aelita-memory.json")

            proc = run_guard(data_dir)
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            self.assertIn("device_write_enabled", {finding["kind"] for finding in report["findings"]})

    def test_rejects_static_dialogue_hardware_claim(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = copy_data_dir(Path(td))
            dialogue_path = data_dir / "aelita-dialogue.json"
            dialogue = json.loads(dialogue_path.read_text(encoding="utf-8"))
            dialogue["lines"][0]["hardware_claim"] = True
            dialogue["lines"][0]["source"] = "AELITA_REENTRY_CHECKPOINT_20260822.md"
            dialogue_path.write_text(json.dumps(dialogue, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            rewrite_index_for(data_dir, "aelita-dialogue.json")

            proc = run_guard(data_dir)
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            self.assertIn("static_dialogue_hardware_claim", {finding["kind"] for finding in report["findings"]})

    def test_rejects_mission_log_chain_break(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = copy_data_dir(Path(td))
            log_path = data_dir / "aelita-mission-log.jsonl"
            events = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            events[1]["previous_hash"] = "0" * 64
            events[1]["event_hash"] = guard.event_hash(events[1])
            log_path.write_text(
                "\n".join(json.dumps(event, sort_keys=True, ensure_ascii=False) for event in events) + "\n",
                encoding="utf-8",
            )
            rewrite_index_for(data_dir, "aelita-mission-log.jsonl")

            proc = run_guard(data_dir)
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            self.assertIn("mission_log_chain_break", {finding["kind"] for finding in report["findings"]})

    def test_rejects_latest_mission_that_does_not_match_last_event(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = copy_data_dir(Path(td))
            latest_path = data_dir / "LATEST_MISSION.md"
            log_path = data_dir / "aelita-mission-log.jsonl"
            events = [
                json.loads(line)
                for line in log_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            current_hash = events[-1]["event_hash"]
            latest = latest_path.read_text(encoding="utf-8")
            latest = latest.replace(
                f"Event hash: `{current_hash}`",
                "Event hash: `0000000000000000000000000000000000000000000000000000000000000000`",
            )
            latest_path.write_text(latest, encoding="utf-8")
            rewrite_index_for(data_dir, "LATEST_MISSION.md")

            proc = run_guard(data_dir)
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            self.assertIn("latest_mission_hash_mismatch", {finding["kind"] for finding in report["findings"]})

    def test_rejects_unindexed_memory_slot_source(self):
        with tempfile.TemporaryDirectory() as td:
            data_dir = copy_data_dir(Path(td))
            memory_path = data_dir / "aelita-memory.json"
            memory = json.loads(memory_path.read_text(encoding="utf-8"))
            memory["memory_slots"].append(
                {
                    "id": "phantom",
                    "label": "Phantom memory",
                    "source": "not-in-index.json",
                    "state": "staged",
                    "summary": "This should not be accepted as evidence.",
                }
            )
            memory_path.write_text(json.dumps(memory, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            rewrite_index_for(data_dir, "aelita-memory.json")

            proc = run_guard(data_dir)
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            self.assertIn("memory_slot_unindexed_source", {finding["kind"] for finding in report["findings"]})


if __name__ == "__main__":
    unittest.main()
