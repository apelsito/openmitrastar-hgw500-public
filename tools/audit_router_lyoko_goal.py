#!/usr/bin/env python3
"""Audit the complete Lyoko objective from current, durable evidence only."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
OBJECTIVE = ROOT / "docs/LYOKO_LIBERATION_PRINCIPLE.md"
CURRENT_STATE = ROOT / "work/mission-state/CURRENT_STATE.json"
OUT_JSON = ROOT / "work/mission-state/ROUTER_LYOKO_GOAL_AUDIT_CURRENT.json"
OUT_MD = ROOT / "work/mission-state/ROUTER_LYOKO_GOAL_AUDIT_CURRENT.md"


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def latest_release_report() -> Path:
    reports = list(ROOT.glob("outputs/release-readiness/**/report.json"))
    if not reports:
        raise FileNotFoundError("no release-readiness report found")
    return max(reports, key=lambda path: path.stat().st_mtime)


def relative(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def objective_coverage(text: str) -> dict[str, bool]:
    terms = {
        "target_hgw500": "HGW-500BNA-QCv2",
        "linux_510": "Linux 5.10",
        "squashfs": "SquashFS",
        "realtek": "Realtek",
        "quantenna": "Quantenna",
        "three_ui_modes": "Normal, Advanced y Developer",
        "packages_arc700": "ARC700",
        "recovery": "recovery",
        "dfs": "DFS",
        "multicast": "multicast",
        "vlan": "VLAN",
        "museum": "docs/museum/",
        "normal_write_boundary": "mtd4/linux_live",
    }
    return {key: needle in text for key, needle in terms.items()}


def overall_status(requirements: list[dict[str, Any]]) -> str:
    statuses = {str(item.get("status", "UNKNOWN")) for item in requirements}
    if "BLOCKED" in statuses:
        return "BLOCKED"
    if statuses & {"NOT_RUN", "PARTIAL", "UNKNOWN"}:
        return "PARTIAL"
    return "PROVEN"


def choose_next_gate(requirements: list[dict[str, Any]]) -> dict[str, str]:
    for desired in ("BLOCKED", "NOT_RUN", "PARTIAL"):
        for item in requirements:
            if item.get("status") == desired:
                return {
                    "id": str(item.get("id", "unknown")),
                    "status": desired,
                    "action": str(item.get("next_action", "No action recorded.")),
                }
    return {"id": "none", "status": "PROVEN", "action": "No remaining gate."}


def build_audit() -> dict[str, Any]:
    objective_text = OBJECTIVE.read_text(encoding="utf-8")
    coverage = objective_coverage(objective_text)
    if not all(coverage.values()):
        missing = sorted(key for key, present in coverage.items() if not present)
        raise RuntimeError(f"durable objective is incomplete: {missing}")

    current = load_json(CURRENT_STATE)
    report_path = latest_release_report()
    release = load_json(report_path)
    requirements = release.get("requirements", [])
    if not requirements:
        raise RuntimeError("release-readiness report contains no requirements")

    installed = str(current.get("physical", {}).get("firmware", "UNKNOWN"))
    generic = current.get("candidates", {}).get("generic", {})
    device = current.get("candidates", {}).get("device_bound", {})
    recovery = current.get("recovery", {}).get("candidate", {})
    status = overall_status(requirements)
    final_candidate_installed = installed in {str(generic.get("version")), str(device.get("version"))}
    release_ready = release.get("release_ready") is True
    achieved = bool(release_ready and final_candidate_installed and all(coverage.values()))
    next_gate = choose_next_gate(requirements)

    return {
        "schema": "router-lyoko.goal-audit/v2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "classification": "EVIDENCE_BASED_NO_HARDWARE_ACTION",
        "objective_source": relative(OBJECTIVE),
        "current_state_source": relative(CURRENT_STATE),
        "release_readiness_source": relative(report_path),
        "objective_coverage": coverage,
        "achieved": achieved,
        "status": "COMPLETE" if achieved else status,
        "summary": {
            "installed_firmware": installed,
            "latest_generic_candidate": generic.get("version"),
            "latest_private_candidate": device.get("version"),
            "recovery_candidate": recovery.get("version"),
            "final_candidate_installed": final_candidate_installed,
            "release_ready": release_ready,
            "release_counts": release.get("counts", {}),
            "next_gate": next_gate,
        },
        "requirements": requirements,
        "safety": {
            "normal_write_target": "mtd4/linux_live",
            "protected_normal_iteration": ["mtd0", "mtd1", "mtd2", "mtd3", "mtd5"],
            "logical_mtd6_is_not_physical": True,
            "audit_hardware_actions": {"uart": False, "reboot": False, "flash": False, "radio_mutation": False},
        },
        "completion_rule": (
            "Complete only when every release requirement is PASS, the final device-bound image is installed, "
            "recovery and return-to-live are physically proven, and the long dual-radio gates pass."
        ),
    }


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Router-Lyoko Goal Audit",
        "",
        f"Generated: `{payload['generated_at']}`",
        f"Status: **{payload['status']}**",
        f"Achieved: **{payload['achieved']}**",
        "",
        "## Current Chain",
        "",
        f"- Installed: `{summary['installed_firmware']}`.",
        f"- Generic candidate: `{summary['latest_generic_candidate']}`.",
        f"- Device-bound candidate: `{summary['latest_private_candidate']}`.",
        f"- Recovery candidate: `{summary['recovery_candidate']}`.",
        f"- Final candidate installed: `{summary['final_candidate_installed']}`.",
        "",
        "## Next Gate",
        "",
        f"- `{summary['next_gate']['id']}` / `{summary['next_gate']['status']}`: {summary['next_gate']['action']}",
        "",
        "## Requirements",
        "",
        "| Requirement | Status | Next action |",
        "|---|---|---|",
    ]
    for item in payload["requirements"]:
        lines.append(f"| {item['title']} | `{item['status']}` | {item['next_action']} |")
    lines.extend([
        "",
        "## Safety",
        "",
        "- Normal iteration writes only `mtd4/linux_live`.",
        "- `mtd0`, `mtd1`, `mtd2`, `mtd3` and `mtd5` remain protected.",
        "- This audit performs no UART, reboot, flash or radio mutation.",
        "",
        "## Completion Rule",
        "",
        payload["completion_rule"],
        "",
    ])
    return "\n".join(lines)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path, default=OUT_JSON)
    parser.add_argument("--md-out", type=Path, default=OUT_MD)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--fail-if-incomplete", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    payload = build_audit()
    if args.write:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 2 if args.fail_if_incomplete and not payload["achieved"] else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
