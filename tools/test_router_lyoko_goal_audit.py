from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "tools/audit_router_lyoko_goal.py"


def run_audit(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(AUDIT), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_current_goal_is_incomplete_and_uses_current_chain() -> None:
    proc = run_audit()
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    assert doc["schema"] == "router-lyoko.goal-audit/v2"
    assert doc["achieved"] is False
    assert doc["status"] in {"BLOCKED", "PARTIAL"}
    assert doc["summary"]["installed_firmware"] == "lyoko-foundation-1.0-f170"
    assert doc["summary"]["latest_generic_candidate"] == "F213"
    assert doc["summary"]["latest_private_candidate"] == "F214"
    assert doc["summary"]["recovery_candidate"] == "F194"
    assert doc["summary"]["next_gate"]["id"] == "recovery"


def test_objective_coverage_and_safety_are_explicit() -> None:
    doc = json.loads(run_audit().stdout)
    assert all(doc["objective_coverage"].values())
    assert doc["safety"]["normal_write_target"] == "mtd4/linux_live"
    assert doc["safety"]["logical_mtd6_is_not_physical"] is True
    assert all(value is False for value in doc["safety"]["audit_hardware_actions"].values())
    ids = {item["id"] for item in doc["requirements"]}
    assert {
        "boot", "rootfs", "recovery", "radio2", "radio5", "dfs", "web",
        "packages", "storage", "vlan", "igmp", "hardware", "soak", "museum",
    } <= ids


def test_fail_if_incomplete_returns_2() -> None:
    proc = run_audit("--fail-if-incomplete")
    assert proc.returncode == 2
    assert '"achieved": false' in proc.stdout


def test_write_outputs_json_and_markdown() -> None:
    with tempfile.TemporaryDirectory() as directory:
        json_out = Path(directory) / "goal.json"
        md_out = Path(directory) / "goal.md"
        proc = run_audit("--write", "--json-out", str(json_out), "--md-out", str(md_out))
        assert proc.returncode == 0, proc.stderr
        assert json.loads(json_out.read_text(encoding="utf-8"))["schema"] == "router-lyoko.goal-audit/v2"
        markdown = md_out.read_text(encoding="utf-8")
        assert "Router-Lyoko Goal Audit" in markdown
        assert "F213" in markdown and "F214" in markdown and "F194" in markdown


def test_source_contains_no_hardware_mutation_commands() -> None:
    source = AUDIT.read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "saveenv", "bootm", "COM3", "ssh "):
        assert forbidden not in source
