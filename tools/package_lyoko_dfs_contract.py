"""Package a reproducible source overlay; never build or install firmware."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "versions/lyoko-dfs-contract-v1"
FILES = ("README.md", "overlay/usr/sbin/om-dfs-status", "overlay/usr/sbin/om-radarctl", "overlay/usr/sbin/om-qtnctl")
BASELINE = ROOT / "versions/lyoko-foundation-7.0.0-f316-radar-native/overlay/usr/sbin/om-qtnctl"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-results", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    suites = ET.parse(args.test_results).getroot().iter("testsuite")
    totals = {name: 0 for name in ("tests", "failures", "errors", "skipped")}
    for suite in suites:
        for name in totals:
            totals[name] += int(suite.get(name, 0))
    if not totals["tests"] or totals["failures"] or totals["errors"] or totals["skipped"]:
        raise SystemExit("all supplied offline tests must pass without skips")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    stream = io.BytesIO()
    records = []
    with gzip.GzipFile(fileobj=stream, mode="wb", filename="", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for name in FILES:
                content = (SOURCE / name).read_bytes()
                info = tarfile.TarInfo(name)
                info.size = len(content)
                info.mode = 0o755 if name.startswith("overlay/") else 0o644
                info.mtime = 0
                archive.addfile(info, io.BytesIO(content))
                records.append({"path": name, "bytes": len(content), "sha256": digest(content), "mode": oct(info.mode)})
    packed = stream.getvalue()
    artifact = args.output_dir / "lyoko-dfs-contract-v1.source-overlay.tar.gz"
    artifact.write_bytes(packed)
    with tarfile.open(artifact, "r:gz") as archive:
        for record in records:
            member = archive.extractfile(record["path"])
            if member is None or digest(member.read()) != record["sha256"]:
                raise SystemExit("source archive readback failed")
    manifest = {
        "schema": "openmitrastar.lyoko-dfs-source-overlay/v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "OFFLINE_SOURCE_ONLY_PASS",
        "artifact": {"path": artifact.name, "bytes": len(packed), "sha256": digest(packed)},
        "source_files": records,
        "qtnctl_baseline_sha256": digest(BASELINE.read_bytes()),
        "test_results": {"path": str(args.test_results.resolve()), "sha256": digest(args.test_results.read_bytes()), **totals},
        "authority": {"firmware_image": False, "flash_supported": False, "installed": False, "hardware_actions_performed": False},
        "physical_gates": {"f315_shadow_acquisition": "NOT_RUN", "f316_dfs_cac_radar_nop": "NOT_RUN", "new_overlay_installed": "NOT_RUN"},
    }
    (args.output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii")
    (args.output_dir / "SHA256SUMS").write_text(f"{digest(packed)}  {artifact.name}\n", encoding="ascii")
    print(json.dumps(manifest, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
