#!/usr/bin/env python3
"""Fail-closed proof that a real TX7 client run specifically justifies TX8."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


TX7_SHA256 = "d547524667d3c1f59b4a4dbf891c1271fe837ee3b5649682a6095492a45781a3"
TX7_BYTES = 4_330_928


def resolved_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("gate_result", type=Path)
    parser.add_argument("--fault-log", type=Path)
    args = parser.parse_args()

    checks: list[dict[str, object]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"id": name, "ok": bool(ok), "detail": detail})

    gate_path = args.gate_result.resolve()
    evidence_dir = gate_path.parent
    run_manifest_path = evidence_dir / "run-manifest.json"
    check("gate.exists", gate_path.is_file(), str(gate_path))
    check("run_manifest.exists", run_manifest_path.is_file(), str(run_manifest_path))
    if not gate_path.is_file() or not run_manifest_path.is_file():
        result = {"schema": "openmitrastar.w2-tx7-for-tx8-proof/v1", "ok": False, "checks": checks}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 1

    gate = json.loads(gate_path.read_text(encoding="utf-8-sig"))
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8-sig"))
    summary_path = Path(str(gate.get("input", "")))
    if not summary_path.is_absolute():
        summary_path = (Path.cwd() / summary_path).resolve()
    check("summary.under_evidence", resolved_under(summary_path, evidence_dir), str(summary_path))
    check("summary.exists", summary_path.is_file(), str(summary_path))
    summary = json.loads(summary_path.read_text(encoding="utf-8-sig")) if summary_path.is_file() else {}

    image = run_manifest.get("image", {})
    check("manifest.schema", run_manifest.get("schema") == "openmitrastar.w2-candidate-live-gate-run/v1", str(run_manifest.get("schema")))
    check("manifest.classification.tx7", run_manifest.get("classification") == "RAM-ONLY-TX7-NO-FLASH-READ-ONLY-SSH", str(run_manifest.get("classification")))
    check("manifest.image.sha", image.get("sha256") == TX7_SHA256, str(image.get("sha256")))
    check("manifest.image.bytes", image.get("bytes") == TX7_BYTES, str(image.get("bytes")))
    for field in ("uart_opened", "module_reload", "reboot", "flash"):
        check(f"manifest.{field}.false", run_manifest.get(field) is False, repr(run_manifest.get(field)))

    check("gate.schema", gate.get("schema") == "openmitrastar.w2-2g-live-traffic-evaluation/v1", str(gate.get("schema")))
    check("gate.pass.false", gate.get("pass") is False, repr(gate.get("pass")))
    check("gate.status.client_failure", gate.get("status") == "FAIL", str(gate.get("status")))
    check("gate.not_no_client", gate.get("status") not in {"NO_CLIENT", "NO_AUTH"}, str(gate.get("status")))
    check("summary.associated", summary.get("association_observed") is True, repr(summary.get("association_observed")))
    check("summary.authorized", summary.get("authorization_observed") is True, repr(summary.get("authorization_observed")))
    check("summary.fatal", int(summary.get("fatal_markers_during_run", 0)) > 0, str(summary.get("fatal_markers_during_run")))
    check("summary.flash.false", summary.get("flash") is False, repr(summary.get("flash")))
    check("summary.mutations.false", summary.get("mutations") is False, repr(summary.get("mutations")))

    fault_observed = summary.get("rx_unaligned_fault_observed") is True
    fault_detail = "summary.rx_unaligned_fault_observed=true" if fault_observed else ""
    if args.fault_log:
        fault_path = args.fault_log.resolve()
        check("fault_log.exists", fault_path.is_file(), str(fault_path))
        text = fault_path.read_text(encoding="utf-8", errors="replace") if fault_path.is_file() else ""
        misaligned = bool(re.search(r"Misaligned (?:Access|r/w)", text, re.IGNORECASE))
        efa = bool(re.search(r"EFA:\s*0x86f900a9\b", text, re.IGNORECASE))
        fault_observed = fault_observed or (misaligned and efa)
        fault_detail = f"fault_log={fault_path} misaligned={misaligned} efa={efa}"
    check("fault.rx_unaligned_exact", fault_observed, fault_detail or "no exact RX-unaligned proof")

    failed = [item["id"] for item in checks if not item["ok"]]
    result = {
        "schema": "openmitrastar.w2-tx7-for-tx8-proof/v1",
        "ok": not failed,
        "status": "TX8_JUSTIFIED_BY_TX7_CLIENT_RX_UNALIGNED" if not failed else "TX8_LOCKED",
        "gate_result": str(gate_path),
        "failed_checks": failed,
        "checks": checks,
        "hardware_actions": False,
        "flash": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
