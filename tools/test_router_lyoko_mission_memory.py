#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RECORDER = ROOT / "tools/record_router_lyoko_mission.py"
TRUTH = ROOT / "work/mission-state/router-lyoko-v0/mission-truth.json"


def run_recorder(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RECORDER), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class RouterLyokoMissionMemoryTests(unittest.TestCase):
    def test_recorder_outputs_lab_side_event_without_writes_by_default(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "memory.jsonl"
            latest = Path(td) / "LATEST.md"
            proc = run_recorder(
                "--truth",
                str(TRUTH),
                "--log",
                str(log),
                "--latest-md",
                str(latest),
                "--timestamp",
                "2026-08-21T00:00:00+00:00",
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads(proc.stdout)
            event = report["event"]
            self.assertEqual(event["classification"], "LAB-SIDE-MEMORY-NO-DEVICE-WRITE")
            self.assertFalse(event["safety"]["device_write"])
            self.assertFalse(log.exists())
            self.assertFalse(latest.exists())

    def test_recorder_write_is_idempotent_for_same_event(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "memory.jsonl"
            latest = Path(td) / "LATEST.md"
            args = [
                "--truth",
                str(TRUTH),
                "--log",
                str(log),
                "--latest-md",
                str(latest),
                "--timestamp",
                "2026-08-21T00:00:00+00:00",
                "--write",
            ]
            first = run_recorder(*args)
            second = run_recorder(*args)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line]
            self.assertEqual(len(lines), 1)
            self.assertIn("Aelita mission memory", latest.read_text(encoding="utf-8"))

    def test_recorder_chains_distinct_events(self):
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "memory.jsonl"
            latest = Path(td) / "LATEST.md"
            base_args = ["--truth", str(TRUTH), "--log", str(log), "--latest-md", str(latest), "--write"]
            first = run_recorder(*base_args, "--timestamp", "2026-08-21T00:00:00+00:00")
            second = run_recorder(*base_args, "--timestamp", "2026-08-21T00:01:00+00:00")
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            events = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]
            self.assertEqual(len(events), 2)
            self.assertEqual(events[1]["previous_hash"], events[0]["event_hash"])

    def test_recorder_rejects_secret_like_truth(self):
        with tempfile.TemporaryDirectory() as td:
            truth = json.loads(TRUTH.read_text(encoding="utf-8"))
            truth["gates"][0]["evidence"][0]["claim"] = "password=supersecret"
            truth_path = Path(td) / "truth.json"
            truth_path.write_text(json.dumps(truth), encoding="utf-8")
            proc = run_recorder("--truth", str(truth_path))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("possible secret", proc.stderr)


if __name__ == "__main__":
    unittest.main()
