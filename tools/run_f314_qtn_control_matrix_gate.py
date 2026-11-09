#!/usr/bin/env python3
"""Exercise every F314 writable Quantenna control with exact rollback."""

from pathlib import Path

import run_f313_qtn_control_matrix_gate as gate


gate.EXPECTED_VERSION = "lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device"
gate.RELEASE = "f314"
gate.EXPECTED_WRITABLE = [
    "ssid", "ssid_broadcast", "client_isolation", "wmm", "short_gi",
    "beacon_interval", "dtim_period", "retry_count", "ldpc", "forty_only",
    "ba_control", "ba_max", "ampdu_density", "multicast_rate",
]
gate.DEFAULT_KNOWN_HOSTS = (
    Path.home()
    / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f314-device-bound/known_hosts.f314"
)
gate.DEFAULT_OUTPUT_DIR = gate.ROOT / "outputs/f3-certification/f314-qtn-control-matrix"


if __name__ == "__main__":
    raise SystemExit(gate.main())
