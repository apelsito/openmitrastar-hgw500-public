#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"

STATIC_TESTS = [
    "test_evaluate_w2_2g_live_traffic.py",
    "test_monitor_2g_live_traffic.py",
    "test_openmitrastar_tool_security.py",
    "test_package_router_lyoko_overlay.py",
    "test_post_tx7_recovery_gate.py",
    "test_post_tx7_recovery_result_verifier.py",
    "test_preflight_post_tx7_resume_offline.py",
    "test_qdrv_v89_beacon_wire_layout.py",
    "test_qtn_beacon_v89_wire.py",
    "test_qtn_beacon_wire_preflight.py",
    "test_qtn_w3_tx7_client_traffic.py",
    "test_resume_post_tx7_5g_hang.py",
    "test_resume_post_tx7_result_verifier.py",
    "test_rtl8192ee_mgmt_trace_budget.py",
    "test_rtl8192ee_mgmt_frame_fields.py",
    "test_rtl8192ee_mgmt_txbd_split.py",
    "test_w2_tx12_mgmt_trace.py",
    "test_w2_tx13_mgmt_trace.py",
    "test_w2_tx17_beacon_aperture.py",
    "test_w2_tx17_ram_boot.py",
    "test_w2_tx18_single_variable.py",
    "test_w2_tx18_ram_boot.py",
    "test_w2_tx9_gate.py",
]


def suite_paths() -> list[Path]:
    selected = {TOOLS / name for name in STATIC_TESTS}
    selected.update(TOOLS.glob("test_router_lyoko_*.py"))
    return sorted(selected, key=lambda path: path.name)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the current Router-Lyoko/post-TX7 offline suite only. "
            "This avoids vendored source tests and superseded flash-candidate checks."
        )
    )
    parser.add_argument("--list", action="store_true", help="Print the selected test files and exit.")
    parser.add_argument("--json", action="store_true", help="Emit a compact JSON summary after pytest.")
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER, help="Extra arguments passed after pytest file list.")
    args = parser.parse_args(argv)

    tests = suite_paths()
    missing = [path for path in tests if not path.is_file()]
    if args.list:
        report = {
            "schema": "router-lyoko.current-offline-suite/v1",
            "classification": "READONLY-OFFLINE-TEST-SUITE-NO-HARDWARE",
            "test_count": len(tests),
            "tests": [str(path.relative_to(ROOT)).replace("\\", "/") for path in tests],
            "missing": [str(path.relative_to(ROOT)).replace("\\", "/") for path in missing],
            "excluded_scope": [
                "work/sources vendored tests",
                "superseded flash-candidate hash gates",
                "historical Q1/Q2/Q3/W5 product artifact tests",
            ],
        }
        print(json.dumps(report, indent=2, ensure_ascii=False))
        print("OMROUTER_LYOKO_CURRENT_OFFLINE_SUITE_LIST_PASS=1" if not missing else "OMROUTER_LYOKO_CURRENT_OFFLINE_SUITE_LIST_PASS=0")
        return 0 if not missing else 2

    if missing:
        for path in missing:
            print(f"OMROUTER_LYOKO_CURRENT_OFFLINE_SUITE_MISSING {path}", file=sys.stderr)
        return 2

    extra = args.pytest_args
    if extra and extra[0] == "--":
        extra = extra[1:]
    cmd = [sys.executable, "-m", "pytest", *[str(path) for path in tests], *(extra or ["-q"])]
    proc = subprocess.run(cmd, cwd=ROOT, text=True, check=False)
    if args.json:
        print(
            json.dumps(
                {
                    "schema": "router-lyoko.current-offline-suite-result/v1",
                    "classification": "READONLY-OFFLINE-TEST-SUITE-NO-HARDWARE",
                    "test_count": len(tests),
                    "returncode": proc.returncode,
                    "ok": proc.returncode == 0,
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    print(
        "OMROUTER_LYOKO_CURRENT_OFFLINE_SUITE_PASS=1"
        if proc.returncode == 0
        else "OMROUTER_LYOKO_CURRENT_OFFLINE_SUITE_PASS=0"
    )
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
