#!/usr/bin/env python3
"""Produce source-bound OFFLINE F320 executor proof; never run a hardware gate."""
from datetime import datetime, timezone
import json
import subprocess
import sys
import f320_campaign_contract as gate


def main():
    output = gate.ROOT / "outputs/preflight" / ("f320-campaign-qualification-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"))
    output.mkdir(parents=True, exist_ok=False)
    sources = {p: gate.sha(gate.ROOT / p) for p in gate.SOURCES}
    images = gate.inspect_all()
    tests = output / "tests.xml"
    process = subprocess.run([sys.executable, "-m", "pytest", "tools/test_f320_campaign.py", "-q",
                              "--junitxml", str(tests)], cwd=gate.ROOT, capture_output=True, text=True, timeout=180)
    (output / "tests.stdout.log").write_text(process.stdout, encoding="utf-8")
    (output / "tests.stderr.log").write_text(process.stderr, encoding="utf-8")
    if process.returncode:
        print(process.stdout + process.stderr)
        raise SystemExit(f"Qualification FAILED; preserved evidence: {output}")
    if sources != {p: gate.sha(gate.ROOT / p) for p in gate.SOURCES} or images != gate.inspect_all():
        raise SystemExit("Inputs changed during qualification; NO-GO")
    report = dict(schema="openmitrastar.f320-campaign-qualification/v1", status="PASS_OFFLINE",
                  generated_at=datetime.now(timezone.utc).isoformat(), hardware_actions=False,
                  physical_acceptance="NOT_RUN", required_ack=gate.ACK, images=images, sources=sources,
                  tests_xml_sha256=gate.sha(tests),
                  limitations=["Synthetic board/SSH/UART failures; not physical safety proof",
                               "Exact authorization, power-cycle availability and fresh identity/lease still required",
                               "TFTP-only; ambiguous write and CPU halt never automatically retried"])
    path = output / "result.json"
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    gate.verify_qualification(path, images)
    print(json.dumps({"status": "PASS_OFFLINE", "result": str(path), "hardware_actions": False}))


if __name__ == "__main__":
    main()
