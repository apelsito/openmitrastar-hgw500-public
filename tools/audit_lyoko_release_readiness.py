#!/usr/bin/env python3
"""Generate a live, evidence-backed Lyoko release-readiness matrix."""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KEY = Path.home() / ".ssh/id_ed25519"
KNOWN_HOSTS = (
    Path.home()
    / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f276-device-bound/known_hosts.f276"
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


def latest(pattern: str) -> Path | None:
    paths = [path for path in ROOT.glob(pattern) if path.is_file()]
    return max(paths, key=lambda path: path.stat().st_mtime) if paths else None


def tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def live_status(host: str) -> dict[str, object]:
    if not tcp_open(host, 22):
        return {"reachable": False}
    remote = r'''
printf 'KERNEL='; uname -r
printf 'FIRMWARE='; sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release 2>/dev/null | head -n 1
printf 'BOOT_STATE='; cat /run/openmitrastar/boot-state 2>/dev/null || true
printf 'RADIO2='; /usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status 2>/dev/null | sed -n 's/^state=//p'
printf 'RADIO5='; cat /run/openmitrastar/radio5g/state 2>/dev/null || true
printf 'ROOTFS='; awk '$2=="/" {print $3":"$4;exit}' /proc/mounts
printf 'FATAL='; dmesg | grep -Eic 'MuC:.*exception|MuC has halted|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV' || true
'''
    ssh = Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"
    ssh_args = [
        ssh, "-i", str(KEY), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=yes", "-o", "LogLevel=ERROR",
    ]
    if KNOWN_HOSTS.is_file():
        ssh_args.extend(("-o", f"UserKnownHostsFile={KNOWN_HOSTS}"))
    proc = subprocess.run(
        [*ssh_args, f"root@{host}", remote],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    values: dict[str, str] = {}
    for line in proc.stdout.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return {"reachable": proc.returncode == 0, **values}


def requirement(identifier: str, title: str, status: str, evidence: list[str], next_action: str) -> dict[str, object]:
    return {
        "id": identifier,
        "title": title,
        "status": status,
        "evidence": evidence,
        "next_action": next_action,
    }


def summarize(requirements: list[dict[str, object]]) -> dict[str, object]:
    counts = {status: 0 for status in ("PASS", "PARTIAL", "BLOCKED", "NOT_RUN")}
    for item in requirements:
        counts[str(item["status"])] += 1
    return {
        "counts": counts,
        "release_ready": counts["PARTIAL"] == 0 and counts["BLOCKED"] == 0 and counts["NOT_RUN"] == 0,
    }


def museum_manifest_valid(path: Path) -> bool:
    manifest = load_json(path)
    entries = manifest.get("entries", [])
    if manifest.get("schema") != "openmitrastar.museum-manifest/v1" or not entries:
        return False
    for entry in entries:
        artifact = path.parent / str(entry.get("file", ""))
        if not artifact.is_file():
            return False
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != entry.get("sha256"):
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    f276_flash_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f276-device-bound/flash-one-shot-20260903T120357Z/result.json"
    f276_gate_path = ROOT / "outputs/postflash/f276-device-20260903T120347Z/status.json"
    f276_visibility_path = ROOT / "outputs/postflash/f276-dual-radio-visibility-20260903/summary.json"
    f276_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f276-device-bound/manifest.json"
    f282_flash_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f282-device-bound/flash-one-shot-20260903T190439Z/result.json"
    f282_gate_path = ROOT / "outputs/postflash/f282-device-20260903T190429Z/status.json"
    f282_restart_path = ROOT / "outputs/postflash/f282-qtn-step-hostapd-restart-same-20260903T191052Z/result.json"
    f282_visibility_path = ROOT / "outputs/postflash/f282-aelita-visibility-20260903T191200Z/result.json"
    f282_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f282-device-bound/manifest.json"
    f285_flash_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f285-device-bound/flash-one-shot-20260903T195336Z/result.json"
    f285_gate_path = ROOT / "outputs/postflash/f285-device-20260903T195327Z/status.json"
    f285_material_path = ROOT / "outputs/postflash/f285-qtn-material-client-window-20260903T200100Z/result.json"
    f285_visibility_path = ROOT / "outputs/postflash/f285-material-aelita-scan-20260903T200115Z/result.json"
    f285_assoc_path = ROOT / "outputs/f3-certification/f285-material-aelita-20260903/sanitized-association-result.json"
    f285_radio5_traffic_path = ROOT / "outputs/f3-certification/f285-5g-aelita-traffic-20260903/result-reconciled-20260903T204757Z.json"
    f285_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f285-device-bound/manifest.json"
    f286_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f286-device-bound/manifest.json"
    f287_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f287-device-bound/manifest.json"
    f288_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f288-device-bound/manifest.json"
    f288_flash_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f288-device-bound/flash-one-shot-20260903T230137Z/result.json"
    f288_gate_path = ROOT / "outputs/postflash/f289-device-20260903T230128Z/status.json"
    f288_radio2_paths = [
        ROOT / f"outputs/f3-certification/f288-emac-rx-fault-20260903/realtek-run-{run}/summary.json"
        for run in range(1, 4)
    ]
    f288_radio2_evaluation_path = ROOT / "outputs/f3-certification/f288-emac-rx-fault-20260903/f288-evaluation.json"
    f288_radio5_path = ROOT / "outputs/f3-certification/f288-emac-rx-fault-20260903/quantenna-sanity/result-20260903T223740Z.json"
    f289_rejection_path = ROOT / "outputs/f3-certification/f289-rejected-20260903/result.json"
    f290_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f290-device-bound/manifest.json"
    f290_flash_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f290-device-bound/flash-one-shot-20260904T000933Z/result.json"
    f290_gate_path = ROOT / "outputs/postflash/f290-device-20260904T000924Z/status.json"
    f290_radio2_paths = [
        ROOT / f"outputs/f3-certification/f290-emac-restart-context-20260903/realtek-run-{run}/summary.json"
        for run in range(1, 4)
    ]
    f290_radio2_evaluation_path = ROOT / "outputs/f3-certification/f290-emac-restart-context-20260903/f290-evaluation.json"
    f290_radio5_path = ROOT / "outputs/f3-certification/f290-emac-restart-context-20260903/quantenna-sanity/result-20260903T234303Z.json"
    f291_rejection_path = ROOT / "outputs/f3-certification/f291-rejected-20260904/result.json"
    f292_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f292-device-bound/manifest.json"
    f292_flash_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f292-device-bound/flash-one-shot-20260904T003353Z/result.json"
    f292_gate_path = ROOT / "outputs/postflash/f292-device-20260904T003344Z/status.json"
    f293_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f293-device-bound/manifest.json"
    f294_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f294-device-bound/manifest.json"
    f294_frontend_path = ROOT / "outputs/frontend/f294-hw-rx-ui-browser-20260904/result.json"
    f295_store_protection_path = ROOT / "outputs/kernel-port/f295-store-protection-observer-20260904/manifest.json"
    f296_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f296-device-bound/manifest.json"
    f296_frontend_path = ROOT / "outputs/frontend/f296-store-protection-ui-browser-20260904/result.json"
    f297_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f297-device-bound/manifest.json"
    f297_preflight_path = ROOT / "outputs/preflight/f297-multicast-20260904T020051Z/plan.json"
    f298_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f298-device-bound/manifest.json"
    f298_frontend_path = ROOT / "outputs/frontend/f298-capability-truth-browser-20260904/result.json"
    f300_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f300-device-bound/manifest.json"
    f300_flash_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f300-device-bound/flash-one-shot-20260904T104208Z/result.json"
    f300_gate_path = ROOT / "outputs/postflash/f300-device-20260904T104158Z/status.json"
    f300_evaluation_path = ROOT / "outputs/campaign/f300-flash-test-20260904T101541Z/physical/f300-evaluation.json"
    f300_radio5_path = ROOT / "outputs/campaign/f300-flash-test-20260904T101541Z/physical/quantenna-sanity/result-20260904T103640Z.json"
    f300_reconciliation_path = ROOT / "outputs/campaign/f300-flash-test-20260904T101541Z/f300-promotion-reconciled-20260904T104515Z.json"
    f301_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f301-device-bound/manifest.json"
    f301_flash_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f301-device-bound/flash-one-shot-20260904T120441Z/result.json"
    f301_gate_path = ROOT / "outputs/postflash/f301-device-20260904T120430Z/status.json"
    f301_campaign_path = ROOT / "outputs/f3-certification/f301-integrated-regression-20260904T121108Z/campaign.json"
    f301_radio2_path = ROOT / "outputs/f3-certification/f301-integrated-regression-20260904T121108Z/realtek-run-1/summary.json"
    f301_radio5_path = ROOT / "outputs/f3-certification/f301-integrated-regression-20260904T121108Z/quantenna-sanity/result-20260904T122134Z.json"
    f301_reconciliation_path = ROOT / "outputs/campaign/f301-flash-test-20260904T120428Z/f301-promotion-reconciled-20260904T122134Z.json"
    f301_multicast_preflight_path = ROOT / "outputs/preflight/f301-multicast-igmp-20260904T124628Z/plan.json"
    f301_vlan_preflight_path = ROOT / "outputs/preflight/f301-vlan4090-final-20260904T132000Z/plan.json"
    f301_dfs_plan_path = ROOT / "outputs/preflight/f301-dfs-es-plan-20260904T125020Z/plan.json"
    f301_store_preflight_path = ROOT / "outputs/preflight/f301-store-protection-probe-20260904T130201Z/plan.json"
    f302_radar_manifest_path = ROOT / "outputs/kernel-port/f302-radar-native-fail-closed-v8-20260904/manifest.json"
    f303_radar_manifest_path = ROOT / "outputs/kernel-port/f303-oem-radar-re-20260904/manifest.json"
    f307_radar_replay_manifest_path = ROOT / "outputs/kernel-port/f307-radar-replay-20260904/manifest.json"
    f308_radar_observer_manifest_path = ROOT / "outputs/kernel-port/f308-radar-observer-v2-20260904/manifest.json"
    f301_soak_checkpoint_path = latest("outputs/soak/f301-sequential-dual-radio-6h-resume*/checkpoint.json")
    f306_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f306-device-bound/manifest.json"
    f306_preflight_path = ROOT / "outputs/preflight/f306-unified-product-final-20260904T160638Z/plan.json"
    f306_soak_plan_path = ROOT / "outputs/preflight/f306-soak-24h-20260904T162651Z/plan.json"
    f293_soak_plan_path = ROOT / "outputs/preflight/f293-sequential-soak-resumable-20260904T023221Z/plan.json"
    f287_flash_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f287-device-bound/flash-one-shot-20260903T213311Z/result.json"
    f287_gate_path = ROOT / "outputs/postflash/f287-device-20260903T213301Z/status.json"
    f287_radio2_paths = [
        ROOT / f"outputs/f3-certification/f287-emac-napi256-20260903/realtek-run-{run}/summary.json"
        for run in range(1, 4)
    ]
    f287_radio2_evaluation_path = ROOT / "outputs/f3-certification/f287-emac-napi256-20260903/f287-evaluation.json"
    f287_radio5_path = ROOT / "outputs/f3-certification/f287-emac-napi256-20260903/quantenna-sanity/result-20260903T215601Z.json"
    f277_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f277-device-bound/manifest.json"
    f278_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f278-device-bound/manifest.json"
    f279_store_module_path = ROOT / "outputs/kernel-port/f279-qtn-topaz-store-mtd-20260903/manifest.json"
    f279_store_init_path = ROOT / "outputs/storage/f279-f277-store-init-final-20260903/transaction.json"
    f279_store_update_path = ROOT / "outputs/storage/f279-f278-store-preserving-update-final-20260903/transaction.json"
    f280_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f280-device-bound/manifest.json"
    museum_manifest_path = ROOT / "docs/museum/manifest.json"
    f219_flash_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f222-device-bound/flash-one-shot-20260902T080852Z/result.json"
    f219_gate_path = ROOT / "outputs/postflash/f222-device-20260902T080842Z/status.json"
    f222_packages_path = ROOT / "outputs/postflash/f222-packages-20260902T080842Z/status.json"
    f292_packages_path = ROOT / "outputs/postflash/f292-packages-current-20260904T020411Z/status.json"
    f292_package_lifecycle_path = ROOT / "outputs/postflash/f292-package-lifecycle-20260904T022342Z/status.json"
    radio2_path = ROOT / "outputs/f3-certification/f219-realtek-2g-physical-r3/summary.json"
    radio2_evaluation_path = ROOT / "outputs/f3-certification/f219-realtek-2g-napi128-evaluation.json"
    f285_radio2_paths = [
        ROOT / f"outputs/f3-certification/f285-realtek-2g-current-r{run}-20260903/summary.json"
        for run in range(1, 4)
    ]
    f285_radio2_evaluation_path = ROOT / "outputs/f3-certification/f285-realtek-2g-current-evaluation-20260903.json"
    radio5_path = ROOT / "outputs/f3-certification/qtn-5g-f219-32m-buffered-20260901T230840Z/evaluation-20260902-010841.json"
    current_state_path = ROOT / "work/mission-state/CURRENT_STATE.json"
    recovery_evidence_path = ROOT / "outputs/recovery/mtd3-current-evidence-20260901/result.json"
    f194_path = ROOT / "work/mission-state/q3-recovery-f194-linux510-safety-slot/build/manifest.json"
    f172_path = ROOT / "work/mission-state/q3-persistent-composite-f172-emac-napi128-from-f171/build/manifest.json"
    f174_path = ROOT / "work/mission-state/q3-persistent-composite-f174-lyoko-package-base-from-f173/build/manifest.json"
    f176_path = ROOT / "work/mission-state/q3-persistent-composite-f176-lyoko-package-ui-from-f174/build/manifest.json"
    f177_path = ROOT / "work/mission-state/q3-persistent-composite-f177-lyoko-package-manager-from-f176/build/manifest.json"
    f179_path = ROOT / "work/mission-state/q3-persistent-composite-f179-integrated-napi-package-manager/build/manifest.json"
    f180_path = ROOT / "work/mission-state/q3-persistent-composite-f180-storage-readonly-probe/build/manifest.json"
    f181_path = ROOT / "outputs/kernel-port/f181-spi-readonly-probe-20260901/manifest.json"
    f182_path = ROOT / "work/mission-state/q3-persistent-composite-f182-spi-probe-boot/build/manifest.json"
    f184_path = ROOT / "work/mission-state/q3-persistent-composite-f184-integrated-capabilities/build/manifest.json"
    f189_path = ROOT / "work/mission-state/q3-persistent-composite-f189-multicast-igmp-from-f188/build/manifest.json"
    f195_path = ROOT / "work/mission-state/q3-persistent-composite-f195-package-hardening-from-f192/build/manifest.json"
    f205_path = ROOT / "work/mission-state/q3-persistent-composite-f205-runtime-signature-from-f203/build/manifest.json"
    f207_path = ROOT / "work/mission-state/q3-persistent-composite-f207-storage-readonly-probe-from-f205/build/manifest.json"
    f213_path = ROOT / "work/mission-state/q3-persistent-composite-f213-movistar-f1-ui-from-f209/build/manifest.json"
    f219_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f222-device-bound/manifest.json"
    f223_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f223-device-bound/manifest.json"
    f224_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f224-device-bound/manifest.json"
    f225_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f225-device-bound/manifest.json"
    f226_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f226-device-bound/manifest.json"
    f227_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f227-device-bound/manifest.json"
    f228_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f228-device-bound/manifest.json"
    f229_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f229-device-bound/manifest.json"
    f230_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f230-device-bound/manifest.json"
    f231_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f231-device-bound/manifest.json"
    f232_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f232-device-bound/manifest.json"
    f233_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f233-device-bound/manifest.json"
    f234_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f234-device-bound/manifest.json"
    f235_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f235-device-bound/manifest.json"
    f236_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f236-device-bound/manifest.json"
    f237_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f237-device-bound/manifest.json"
    f238_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f238-device-bound/manifest.json"
    f239_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f239-device-bound/manifest.json"
    f240_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f240-device-bound/manifest.json"
    f241_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f241-device-bound/manifest.json"
    f242_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f242-device-bound/manifest.json"
    f243_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f243-device-bound/manifest.json"
    f244_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f244-device-bound/manifest.json"
    f245_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f245-device-bound/manifest.json"
    f246_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f246-device-bound/manifest.json"
    f247_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f247-device-bound/manifest.json"
    f248_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f248-device-bound/manifest.json"
    f249_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f249-device-bound/manifest.json"
    f250_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f250-device-bound/manifest.json"
    f251_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f251-device-bound/manifest.json"
    f252_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f252-device-bound/manifest.json"
    f253_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f253-device-bound/manifest.json"
    f254_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f254-device-bound/manifest.json"
    f255_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f255-device-bound/manifest.json"
    f256_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f256-device-bound/manifest.json"
    f257_path = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f257-device-bound/manifest.json"
    f213_browser_path = ROOT / "outputs/frontend/f213-movistar-f1-ui-browser-20260901/result.json"
    f211_store_path = ROOT / "outputs/storage/f211-lyoko-store-v1-20260901/manifest.json"
    f212_update_path = ROOT / "outputs/storage/f212-store-preserving-update-20260901/result.json"
    f175_path = ROOT / "outputs/kernel-port/f175-network-capabilities-config-20260901/manifest.json"
    network_path = latest("outputs/certification/network-capabilities-f*/audit.json")
    network_preflight_path = latest("outputs/certification/network-traffic-preflight-*/preflight.json")

    flash = load_json(f285_flash_path)
    gate = load_json(f285_gate_path)
    visibility = load_json(f276_visibility_path)
    current_visibility = load_json(f285_visibility_path)
    f276 = load_json(f276_path)
    f282 = load_json(f282_path)
    f282_restart = load_json(f282_restart_path)
    f285 = load_json(f285_path)
    f285_material = load_json(f285_material_path)
    f285_assoc = load_json(f285_assoc_path)
    f285_radio5_traffic = load_json(f285_radio5_traffic_path)
    f286 = load_json(f286_path)
    f287 = load_json(f287_path)
    f288 = load_json(f288_path)
    f288_flash = load_json(f288_flash_path)
    f288_gate = load_json(f288_gate_path)
    f288_radio2_runs = [load_json(path) for path in f288_radio2_paths]
    f288_radio2_evaluation = load_json(f288_radio2_evaluation_path)
    f288_radio5 = load_json(f288_radio5_path)
    f289_rejection = load_json(f289_rejection_path)
    f290 = load_json(f290_path)
    f290_flash = load_json(f290_flash_path)
    f290_gate = load_json(f290_gate_path)
    f290_radio2_runs = [load_json(path) for path in f290_radio2_paths]
    f290_radio2_evaluation = load_json(f290_radio2_evaluation_path)
    f290_radio5 = load_json(f290_radio5_path)
    f291_rejection = load_json(f291_rejection_path)
    f292 = load_json(f292_path)
    f292_flash = load_json(f292_flash_path)
    f292_gate = load_json(f292_gate_path)
    f293 = load_json(f293_path)
    f294 = load_json(f294_path)
    f294_frontend = load_json(f294_frontend_path)
    f295_store_protection = load_json(f295_store_protection_path)
    f296 = load_json(f296_path)
    f296_frontend = load_json(f296_frontend_path)
    f297 = load_json(f297_path)
    f297_preflight = load_json(f297_preflight_path)
    f298 = load_json(f298_path)
    f298_frontend = load_json(f298_frontend_path)
    f300 = load_json(f300_path)
    f300_flash = load_json(f300_flash_path)
    f300_gate = load_json(f300_gate_path)
    f300_evaluation = load_json(f300_evaluation_path)
    f300_radio5 = load_json(f300_radio5_path)
    f300_reconciliation = load_json(f300_reconciliation_path)
    f301 = load_json(f301_path)
    f301_flash = load_json(f301_flash_path)
    f301_gate = load_json(f301_gate_path)
    f301_campaign = load_json(f301_campaign_path)
    f301_radio2 = load_json(f301_radio2_path)
    f301_radio5 = load_json(f301_radio5_path)
    f301_reconciliation = load_json(f301_reconciliation_path)
    f301_multicast_preflight = load_json(f301_multicast_preflight_path)
    f301_vlan_preflight = load_json(f301_vlan_preflight_path)
    f301_dfs_plan = load_json(f301_dfs_plan_path)
    f301_store_preflight = load_json(f301_store_preflight_path)
    f302_radar_manifest = load_json(f302_radar_manifest_path)
    f303_radar_manifest = load_json(f303_radar_manifest_path)
    f307_radar_replay_manifest = load_json(f307_radar_replay_manifest_path)
    f308_radar_observer_manifest = load_json(f308_radar_observer_manifest_path)
    f301_soak_checkpoint = load_json(f301_soak_checkpoint_path) if f301_soak_checkpoint_path else {}
    f306 = load_json(f306_path)
    f306_preflight = load_json(f306_preflight_path)
    f306_soak_plan = load_json(f306_soak_plan_path)
    f293_soak_plan = load_json(f293_soak_plan_path)
    f287_flash = load_json(f287_flash_path)
    f287_gate = load_json(f287_gate_path)
    f287_radio2_runs = [load_json(path) for path in f287_radio2_paths]
    f287_radio2_evaluation = load_json(f287_radio2_evaluation_path)
    f287_radio5 = load_json(f287_radio5_path)
    f277 = load_json(f277_path)
    f278 = load_json(f278_path)
    f279_store_module = load_json(f279_store_module_path)
    f279_store_init = load_json(f279_store_init_path)
    f279_store_update = load_json(f279_store_update_path)
    f280 = load_json(f280_path)
    radio2 = load_json(radio2_path)
    radio2_evaluation = load_json(radio2_evaluation_path)
    f285_radio2_runs = [load_json(path) for path in f285_radio2_paths]
    f285_radio2_evaluation = load_json(f285_radio2_evaluation_path)
    radio5 = load_json(radio5_path)
    current_state = load_json(current_state_path)
    recovery_evidence = load_json(recovery_evidence_path)
    f194 = load_json(f194_path)
    f172 = load_json(f172_path)
    f174 = load_json(f174_path)
    f176 = load_json(f176_path)
    f177 = load_json(f177_path)
    f179 = load_json(f179_path)
    f180 = load_json(f180_path)
    f181 = load_json(f181_path)
    f182 = load_json(f182_path)
    f184 = load_json(f184_path)
    f189 = load_json(f189_path)
    f195 = load_json(f195_path)
    f205 = load_json(f205_path)
    f207 = load_json(f207_path)
    f213 = load_json(f213_path)
    f219 = load_json(f219_path)
    f223 = load_json(f223_path)
    f224 = load_json(f224_path)
    f225 = load_json(f225_path)
    f226 = load_json(f226_path)
    f227 = load_json(f227_path)
    f228 = load_json(f228_path)
    f229 = load_json(f229_path)
    f230 = load_json(f230_path)
    f231 = load_json(f231_path)
    f232 = load_json(f232_path)
    f233 = load_json(f233_path)
    f234 = load_json(f234_path)
    f235 = load_json(f235_path)
    f236 = load_json(f236_path)
    f237 = load_json(f237_path)
    f238 = load_json(f238_path)
    f239 = load_json(f239_path)
    f240 = load_json(f240_path)
    f241 = load_json(f241_path)
    f242 = load_json(f242_path)
    f243 = load_json(f243_path)
    f244 = load_json(f244_path)
    f245 = load_json(f245_path)
    f246 = load_json(f246_path)
    f247 = load_json(f247_path)
    f248 = load_json(f248_path)
    f249 = load_json(f249_path)
    f250 = load_json(f250_path)
    f251 = load_json(f251_path)
    f252 = load_json(f252_path)
    f253 = load_json(f253_path)
    f254 = load_json(f254_path)
    f255 = load_json(f255_path)
    f256 = load_json(f256_path)
    f257 = load_json(f257_path)
    f222_packages = load_json(f222_packages_path)
    f292_packages = load_json(f292_packages_path)
    f292_package_lifecycle = load_json(f292_package_lifecycle_path)
    f213_browser = load_json(f213_browser_path)
    f211_store = load_json(f211_store_path)
    f212_update = load_json(f212_update_path)
    f175 = load_json(f175_path)
    network = load_json(network_path) if network_path else {}
    network_preflight = load_json(network_preflight_path) if network_preflight_path else {}
    live = live_status(args.host)

    protected = flash.get("protected_partitions", {}).get("status") == "PASS"
    base_gate = gate.get("status") == "PASS"
    expected_firmware = "lyoko-foundation-6.6.1-f301-f300-capability-truth-device"
    installed_current = live.get("reachable") is True and live.get("FIRMWARE") == expected_firmware
    installed_flash = f301_flash
    installed_gate = f301_gate
    historical_visibility_pass = (
        visibility.get("radio2", {}).get("client_visible") is True
        and visibility.get("radio5", {}).get("client_visible") is True
        and visibility.get("fatal_count") == 0
    )
    current_visibility_pass = (
        current_visibility.get("radio2", {}).get("client_visible") is True
        and current_visibility.get("radio5", {}).get("client_visible") is True
        and current_visibility.get("fatal_count") == 0
    )
    current_tx_ready = (
        current_visibility.get("radio2", {}).get("router_ap_ready") is True
        and current_visibility.get("radio5", {}).get("router_ap_ready") is True
        and int(current_visibility.get("radio2", {}).get("tx_packet_delta") or 0) > 0
        and int(current_visibility.get("radio5", {}).get("tx_packet_delta") or 0) > 0
    )
    radio2_pass = radio2.get("controller_download", {}).get("pass") is True and radio2.get("controller_upload", {}).get("pass") is True
    current_radio2_pass = bool(
        len(f285_radio2_runs) == 3
        and all(
            run.get("controller_download", {}).get("pass") is True
            and int(run.get("controller_download", {}).get("bytes") or 0) >= 32 * 1024 * 1024
            and run.get("controller_upload", {}).get("pass") is True
            and int(run.get("controller_upload", {}).get("bytes") or 0) >= 32 * 1024 * 1024
            and run.get("router_health_gate", {}).get("pass") is True
            and run.get("execution_error") is None
            for run in f285_radio2_runs
        )
    )
    f287_radio2_pass = bool(
        len(f287_radio2_runs) == 3
        and all(
            run.get("controller_download", {}).get("pass") is True
            and int(run.get("controller_download", {}).get("bytes") or 0) >= 32 * 1024 * 1024
            and run.get("controller_upload", {}).get("pass") is True
            and int(run.get("controller_upload", {}).get("bytes") or 0) >= 32 * 1024 * 1024
            and run.get("router_health_gate", {}).get("pass") is True
            and run.get("execution_error") is None
            for run in f287_radio2_runs
        )
    )
    f287_radio5_pass = (
        f287_radio5.get("status") == "PASS"
        and f287_radio5.get("download", {}).get("pass") is True
        and f287_radio5.get("upload", {}).get("pass") is True
        and f287_radio5.get("router", {}).get("status") == "PASS"
    )
    f288_radio2_pass = bool(
        len(f288_radio2_runs) == 3
        and all(
            run.get("controller_download", {}).get("pass") is True
            and int(run.get("controller_download", {}).get("bytes") or 0) >= 32 * 1024 * 1024
            and run.get("controller_upload", {}).get("pass") is True
            and int(run.get("controller_upload", {}).get("bytes") or 0) >= 32 * 1024 * 1024
            and run.get("router_health_gate", {}).get("pass") is True
            and run.get("execution_error") is None
            for run in f288_radio2_runs
        )
    )
    f288_radio5_pass = (
        f288_radio5.get("status") == "PASS"
        and f288_radio5.get("download", {}).get("pass") is True
        and f288_radio5.get("upload", {}).get("pass") is True
        and f288_radio5.get("router", {}).get("status") == "PASS"
    )
    f290_radio2_pass = bool(
        len(f290_radio2_runs) == 3
        and all(
            run.get("controller_download", {}).get("pass") is True
            and int(run.get("controller_download", {}).get("bytes") or 0) >= 32 * 1024 * 1024
            and run.get("controller_upload", {}).get("pass") is True
            and int(run.get("controller_upload", {}).get("bytes") or 0) >= 32 * 1024 * 1024
            and run.get("router_health_gate", {}).get("pass") is True
            and run.get("execution_error") is None
            for run in f290_radio2_runs
        )
    )
    f290_radio5_pass = (
        f290_radio5.get("status") == "PASS"
        and f290_radio5.get("download", {}).get("pass") is True
        and f290_radio5.get("upload", {}).get("pass") is True
        and f290_radio5.get("router", {}).get("status") == "PASS"
    )
    f300_radio2_pass = (
        f300_evaluation.get("status") == "PASS"
        and f300_evaluation.get("gates", {}).get("transport") == "PASS"
        and f300_evaluation.get("gates", {}).get("safety") == "PASS"
        and f300_evaluation.get("gates", {}).get("performance") == "PASS"
        and f300_evaluation.get("gates", {}).get("early_restart") == "PASS"
    )
    f300_radio5_pass = (
        f300_radio5.get("status") == "PASS"
        and f300_radio5.get("download", {}).get("pass") is True
        and f300_radio5.get("upload", {}).get("pass") is True
        and int(f300_radio5.get("soak", {}).get("disconnects") or 0) == 0
        and f300_radio5.get("router", {}).get("status") == "PASS"
    )
    f301_radio2_pass = (
        f301_campaign.get("status") == "PASS"
        and f301_radio2.get("controller_download", {}).get("pass") is True
        and f301_radio2.get("controller_upload", {}).get("pass") is True
        and f301_radio2.get("router_health_gate", {}).get("pass") is True
    )
    f301_radio5_pass = (
        f301_campaign.get("status") == "PASS"
        and f301_radio5.get("status") == "PASS"
        and f301_radio5.get("download", {}).get("pass") is True
        and f301_radio5.get("upload", {}).get("pass") is True
        and int(f301_radio5.get("soak", {}).get("disconnects") or 0) == 0
    )
    radio5_pass = radio5.get("status") == "PASS" and all(radio5.get("directions", {}).values())
    radio5_assoc_pass = (
        f285_assoc.get("status") == "PASS"
        and f285_assoc.get("association", {}).get("status") == "PASS"
        and f285_assoc.get("association", {}).get("band") == "5 GHz"
        and str(f285_assoc.get("association", {}).get("channel")) == "36"
        and f285_assoc.get("association", {}).get("router_ping") is True
        and f285_assoc.get("client_restore", {}).get("status") == "PASS"
        and f285_assoc.get("router_restore", {}).get("status") == "PASS"
    )
    current_radio5_traffic_pass = (
        f285_radio5_traffic.get("status") == "PASS"
        and f285_radio5_traffic.get("download", {}).get("pass") is True
        and int(f285_radio5_traffic.get("download", {}).get("bytes") or 0) >= 32 * 1024 * 1024
        and f285_radio5_traffic.get("upload", {}).get("pass") is True
        and int(f285_radio5_traffic.get("upload", {}).get("bytes") or 0) >= 32 * 1024 * 1024
        and int(f285_radio5_traffic.get("soak", {}).get("requested_seconds") or 0) >= 120
        and int(f285_radio5_traffic.get("soak", {}).get("disconnects") or 0) == 0
        and f285_radio5_traffic.get("router", {}).get("status") == "PASS"
    )
    f307_radar_replay_pass = (
        f307_radar_replay_manifest.get("status") == "PASS"
        and f307_radar_replay_manifest.get("classification") == "OFFLINE_DETERMINISTIC_REPLAY_ONLY"
        and f307_radar_replay_manifest.get("classification_algorithm") == "NOT_IMPLEMENTED"
        and f307_radar_replay_manifest.get("physical_rf_detection_proven") is False
        and f307_radar_replay_manifest.get("flash_candidate_produced") is False
    )
    f308_radar_observer_pass = (
        f308_radar_observer_manifest.get("status") == "PASS"
        and f308_radar_observer_manifest.get("classification") == "OFFLINE_BOUNDED_READ_ONLY_OBSERVER_NOT_A_DETECTOR"
        and f308_radar_observer_manifest.get("behavior", {}).get("backend_ready") is False
        and f308_radar_observer_manifest.get("behavior", {}).get("rf_register_writes") == 0
        and f308_radar_observer_manifest.get("safety", {}).get("module_loaded") is False
    )
    web_offline_pass = f213_browser.get("status") == "PASS"
    museum_pass = museum_manifest_valid(museum_manifest_path)
    requirements = [
        requirement("boot", "Persistent Linux 5.10 boot from mtd4", "PASS" if installed_flash.get("status") == "PASS" and installed_flash.get("protected_partitions", {}).get("status") == "PASS" and installed_gate.get("status") == "PASS" and installed_current else "PARTIAL", [str(f301_flash_path), str(f301_gate_path.relative_to(ROOT)), "live SSH read-only gate"], "Run three cold boots on the final release candidate."),
        requirement("rootfs", "Exact SquashFS rootfs_live window and immutable mounts", "PASS" if all(installed_gate.get("checks", {}).get(key) for key in ("root_squashfs_ro", "rootfs_window", "store_window", "run_tmpfs", "tmp_tmpfs", "persist_ro")) else "PARTIAL", [str(f301_gate_path.relative_to(ROOT)), "docs/museum/f165-full-rootfs-window.md"], "Keep the split layout in every later image."),
        requirement("recovery", "Independent Linux 5.10 recovery in mtd3", "BLOCKED" if recovery_evidence.get("recovery_ready") is not True else "PASS", [str(recovery_evidence_path.relative_to(ROOT)), str(f194_path.relative_to(ROOT)), str(f285_flash_path)], "Provision and cold-boot a verified safety-slot image in a separately authorized recovery campaign."),
        requirement("radio_visibility", "Physical radio visibility and client association", "PASS" if historical_visibility_pass and current_tx_ready and radio5_assoc_pass else "PARTIAL", [str(f285_assoc_path.relative_to(ROOT)), str(f285_visibility_path.relative_to(ROOT)), str(f276_visibility_path.relative_to(ROOT)), "docs/OPENMITRASTAR_F285_CURRENT_STATE.md"], "Keep the sanitized F285 association evidence and repeat visibility only when the radio stack changes."),
        requirement("radio2", "2.4 GHz WPA2 bidirectional traffic on current image", "PASS" if f301_radio2_pass and f301_reconciliation.get("installed") is True else "PARTIAL", [str(f301_radio2_path.relative_to(ROOT)), str(f301_campaign_path.relative_to(ROOT)), str(f300_evaluation_path.relative_to(ROOT))], "Use the F300 three-run datapath baseline plus the F301 current-image regression for later comparisons."),
        requirement("radio2_perf", "2.4 GHz optimized datapath", "PASS" if f300_radio2_pass else "PARTIAL", [str(f300_evaluation_path.relative_to(ROOT)), "docs/OPENMITRASTAR_F299_PHYSICAL_RESULT.md", str(f290_radio2_evaluation_path.relative_to(ROOT))], "Run a prolonged F300 soak and inspect whether the two-sample recovery remains stable under repeated stalls."),
        requirement("radio5", "5 GHz WPA2 bidirectional traffic on current image", "PASS" if f301_radio5_pass and f301_reconciliation.get("installed") is True else "PARTIAL", [str(f301_radio5_path.relative_to(ROOT)), str(f301_campaign_path.relative_to(ROOT)), str(f300_radio5_path.relative_to(ROOT))], "Keep the F301 5 GHz gate as the current product baseline and repeat it after shared-EMAC changes."),
        requirement("radio_control", "Transactional 2.4 and 5 GHz control", "PARTIAL" if f285_material.get("status") == "PASS" and radio5_assoc_pass else "BLOCKED", ["docs/OPENMITRASTAR_F267_CURRENT_STATE.md", "docs/OPENMITRASTAR_F285_CURRENT_STATE.md", str(f285_path), str(f285_material_path.relative_to(ROOT)), str(f285_assoc_path.relative_to(ROOT)), str(f286_path)], "SSID material apply and client association pass; F286 fixes restore readback convergence, then channel and bandwidth remain isolated gates."),
        requirement("dfs", "Spain DFS CAC and radar handling", "BLOCKED" if f301_dfs_plan.get("selected_gate", {}).get("eligibility") == "BLOCKED_DFS_RADAR_BACKEND_UNAVAILABLE" else "PARTIAL", [str(f301_dfs_plan_path.relative_to(ROOT)), str(f302_radar_manifest_path.relative_to(ROOT)), str(f303_radar_manifest_path.relative_to(ROOT)), str(f307_radar_replay_manifest_path.relative_to(ROOT)), str(f308_radar_observer_manifest_path.relative_to(ROOT)), "docs/OPENMITRASTAR_F301_DFS_REGULATORY_AUDIT.md", "docs/OPENMITRASTAR_F303_OEM_RADAR_RE.md", "docs/OPENMITRASTAR_F307_RADAR_REPLAY.md", "docs/OPENMITRASTAR_F308_RADAR_OBSERVER.md"], "Package F308 disabled in a later versioned mtd4 diagnostic image, verify its fail-closed observer on a non-DFS channel, then feed sanitized OEM oracle captures into F307 before reconstructing the pulse classifier." if f307_radar_replay_pass and f308_radar_observer_pass else "Repair and verify the offline F307/F308 radar contracts before any hardware observation."),
        requirement("web", "Authenticated unified Developer console and API v1", "PASS" if f301_reconciliation.get("gates", {}).get("authenticated_login") == "PASS" and f301_reconciliation.get("gates", {}).get("dashboard") == "PASS" and f301_reconciliation.get("gates", {}).get("authenticated_api") == "PASS" and f301_reconciliation.get("gates", {}).get("live_asset_hashes") == "PASS" else "PARTIAL", [str(f301_reconciliation_path.relative_to(ROOT)), str(f301_gate_path.relative_to(ROOT)), str(f298_frontend_path.relative_to(ROOT))], "Use F301 as the current web/API baseline and keep all future UI changes tied to live asset hashes."),
        requirement("packages", "Signed ARC700/uClibc IPK lifecycle", "PASS" if f292_package_lifecycle.get("status") == "PASS" and all(f292_package_lifecycle.get("checks", {}).get(key) for key in ("verify", "install", "exec", "remove", "mtd5_unchanged", "no_fatal")) and f292_packages.get("status") == "PASS" and f292_packages.get("checks", {}).get("gate_disabled_after") is True and gate.get("checks", {}).get("package_verifier") else "PARTIAL", [str(f292_package_lifecycle_path.relative_to(ROOT)), str(f292_packages_path.relative_to(ROOT)), str(f222_packages_path.relative_to(ROOT)), str(f195_path.relative_to(ROOT)), str(f205_path.relative_to(ROOT)), "outputs/packages/lyoko-runtime-signature-v1.1/manifest.json", str(f245_path)], "Repeat the same volatile lifecycle only after the final firmware image changes."),
        requirement("storage", "Persistent package store plus RAM execution", "PARTIAL" if f301_store_preflight.get("local_preflight_pass") is True and f301_store_preflight.get("source_contract", {}).get("pass") is True else "NOT_RUN", [str(f301_store_preflight_path.relative_to(ROOT)), "docs/f301_store_protection_probe.md", str(f295_store_protection_path.relative_to(ROOT))], "After the F301 soak, execute the read-only observer load/unload gate; persistent writes remain disabled until that result passes."),
        requirement("vlan", "VLAN traffic", "NOT_RUN" if f301_vlan_preflight.get("execute_eligible_offline") is True else "BLOCKED", [str(f301_vlan_preflight_path.relative_to(ROOT)), "docs/OPENMITRASTAR_F301_VLAN_GATE.md"], "After the soak, validate live UART and the controller VLAN adapter, then run isolated VLAN 4090 traffic with all watchdogs armed."),
        requirement("igmp", "Multicast and IGMP snooping", "NOT_RUN" if f301_multicast_preflight.get("local_preflight_pass") is True and f301_multicast_preflight.get("candidate_matches") is True else "BLOCKED", [str(f301_multicast_preflight_path.relative_to(ROOT)), str(f297_path), "tools/run_f301_multicast_igmp_physical.py"], "Execute the F301 bidirectional multicast gate after the active soak releases the shared physical lock."),
        requirement("hardware", "Buttons, LEDs, GPIO and thermal/watchdog observability", "PARTIAL", [str(f176_path.relative_to(ROOT)), str(f229_path), str(f243_path), "outputs/frontend/f243-hardware-provenance-browser-20260902/result.json", "docs/OPENMITRASTAR_FRONTPANEL_LED_GATE.md", "tools/run_frontpanel_led_identification_gate.ps1", "F222 live sysfs/input inventory"], "Run the guarded visual LED identification gate with an observer; it restores the exact pre-test state."),
        requirement("soak", "Six-hour and 24-hour dual-radio soak", "PASS" if f301_soak_checkpoint.get("status") == "PASS" and f301_soak_checkpoint.get("duration_reached") is True else "PARTIAL" if f301_soak_checkpoint.get("status") == "IN_PROGRESS" and int(f301_soak_checkpoint.get("cycles_completed") or 0) > 0 else "NOT_RUN", [str(f301_soak_checkpoint_path.relative_to(ROOT)) if f301_soak_checkpoint_path else "missing", str(f301_campaign_path.relative_to(ROOT))], "Let the active six-hour F301 soak complete, then run the final 24-hour and simultaneous two-client gates."),
        requirement("museum", "Development museum and reproducible evidence", "PASS" if museum_pass else "PARTIAL", ["docs/museum/README.md", "docs/museum/manifest.json"], "Keep regenerating the index and add final benchmark deltas and release tags."),
    ]
    summary = summarize(requirements)
    result = {
        "schema": "openmitrastar.lyoko-release-readiness/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "installed_firmware": live.get("FIRMWARE") or current_state.get("physical", {}).get("firmware") or "UNKNOWN",
        "installed_candidate": {"name": "F301", "sha256": f301.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f301_reconciliation.get("status"), "target": "mtd4/linux_live"},
        "next_candidate": {"name": "F306", "sha256": f306.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f306.get("physical_validation", {}).get("status"), "eligible": f306.get("candidate_eligible"), "execute_allowed_now": f306_preflight.get("execute_allowed_now")},
        "offline_network_successor": {"name": "F297", "sha256": f297.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f297.get("physical_validation", {}).get("status"), "eligible": f297.get("candidate_eligible")},
        "latest_integrated_hold": {"name": "F298", "sha256": f298.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f298.get("physical_validation", {}).get("status"), "eligible": f298.get("candidate_eligible")},
        "legacy_multicast_harness": {"name": "F278", "sha256": f278.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f278.get("physical_validation", {}).get("status"), "eligible": f278.get("candidate_eligible")},
        "offline_store_writer_module": {"name": "F279", "sha256": f279_store_module.get("artifact", {}).get("sha256"), "hardware": f279_store_module.get("physical_validation"), "eligible": False},
        "offline_store_driver_image": {"name": "F280", "sha256": f280.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f280.get("physical_validation", {}).get("status"), "eligible": f280.get("candidate_eligible")},
        "latest_recovery_candidate": {"name": "F194", "sha256": f194.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f194.get("physical_validation", {}).get("status")},
        "latest_datapath_candidate": {"name": "F300", "sha256": f300.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f300_reconciliation.get("status"), "eligible": f300.get("candidate_eligible")},
        "latest_soak_plan": {"name": "F306-24h-sequential", "duration_hours": f306_soak_plan.get("duration_hours"), "hardware": "NOT_RUN", "simultaneous": f306_soak_plan.get("simultaneous_dual_radio")},
        "proven_datapath_baseline": {"name": "F300", "sha256": f300.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f300_reconciliation.get("status")},
        "rejected_datapath_candidates": [
            {"name": "F289", "sha256": "3a4596bd93b64eea3f2b91ca7f510908e5383130f5d4d4eb708cc13b8c516a2b", "hardware": f289_rejection.get("status")},
            {"name": "F291", "sha256": "26687f230365c6bc4cd9048104f35990a29d9edcaece2a1492b30d34607abf51", "hardware": f291_rejection.get("status")},
        ],
        "latest_product_candidate": {"name": "F306", "sha256": f306.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f306.get("physical_validation", {}).get("status"), "eligible": f306.get("candidate_eligible")},
        "latest_frontend_source": {"name": "F301", "version": "6.6.1", "sha256": f301.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f301_reconciliation.get("status"), "eligible": f301.get("candidate_eligible"), "offline": "PASS"},
        "previous_frontend_source": {"name": "F294", "version": "6.5.2", "sha256": f294.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f294.get("physical_validation", {}).get("status"), "eligible": f294.get("candidate_eligible"), "offline": f294_frontend.get("status")},
        "latest_store_protection_observer": {"name": "F295", "sha256": f295_store_protection.get("artifact", {}).get("sha256"), "hardware": f295_store_protection.get("physical_validation"), "write_capable": False},
        "offline_store_protection_hold": {"name": "F296", "sha256": f296.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f296.get("physical_validation", {}).get("status"), "eligible": f296.get("candidate_eligible"), "flash_supported": f296.get("flash_supported")},
        "latest_qtn_control_candidate": {"name": "F277", "sha256": f277.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f277.get("physical_validation", {}).get("status"), "eligible": f277.get("candidate_eligible")},
        "superseded_dual_control_candidate": {"name": "F235", "sha256": f235.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f235.get("physical_validation", {}).get("status"), "eligible": False},
        "latest_dual_control_candidate": {"name": "F237", "sha256": f237.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f237.get("physical_validation", {}).get("status"), "eligible": f237.get("candidate_eligible")},
        "latest_dfs_observability_candidate": {"name": "F239", "sha256": f239.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f239.get("physical_validation", {}).get("status"), "eligible": f239.get("candidate_eligible")},
        "latest_dfs_replay": {"name": "F307", "status": f307_radar_replay_manifest.get("status"), "classification": f307_radar_replay_manifest.get("classification"), "physical_rf_detection_proven": f307_radar_replay_manifest.get("physical_rf_detection_proven")},
        "latest_dfs_observer": {"name": "F308", "status": f308_radar_observer_manifest.get("status"), "classification": f308_radar_observer_manifest.get("classification"), "module_loaded": f308_radar_observer_manifest.get("safety", {}).get("module_loaded"), "backend_ready": f308_radar_observer_manifest.get("behavior", {}).get("backend_ready")},
        "latest_network_observability_candidate": {"name": "F241", "sha256": f241.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f241.get("physical_validation", {}).get("status"), "eligible": f241.get("candidate_eligible")},
        "latest_hardware_provenance_candidate": {"name": "F243", "sha256": f243.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f243.get("physical_validation", {}).get("status"), "eligible": f243.get("candidate_eligible")},
        "latest_package_catalog_candidate": {"name": "F245", "sha256": f245.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f245.get("physical_validation", {}).get("status"), "eligible": f245.get("candidate_eligible")},
        "latest_package_runtime_evidence": {"name": "F292", "status": f292_package_lifecycle.get("status"), "api_status": f292_packages.get("status"), "persistent_writes": f292_package_lifecycle.get("persistent_writes")},
        "latest_physical_test_candidate": {"name": "F247", "sha256": f247.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f247.get("physical_validation", {}).get("status"), "eligible": f247.get("candidate_eligible")},
        "latest_opkg_compatibility_candidate": {"name": "F248", "sha256": f248.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f248.get("physical_validation", {}).get("status"), "eligible": f248.get("candidate_eligible")},
        "latest_integrated_opkg_hold": {"name": "F249", "sha256": f249.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f249.get("physical_validation", {}).get("status"), "eligible": f249.get("candidate_eligible")},
        "latest_led_control_candidate": {"name": "F250", "sha256": f250.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f250.get("physical_validation", {}).get("status"), "eligible": f250.get("candidate_eligible")},
        "latest_integrated_led_hold": {"name": "F251", "sha256": f251.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f251.get("physical_validation", {}).get("status"), "eligible": f251.get("candidate_eligible")},
        "latest_config_store_candidate": {"name": "F252", "sha256": f252.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f252.get("physical_validation", {}).get("status"), "eligible": f252.get("candidate_eligible")},
        "latest_integrated_config_store_hold": {"name": "F253", "sha256": f253.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f253.get("physical_validation", {}).get("status"), "eligible": f253.get("candidate_eligible")},
        "latest_config_store_status_candidate": {"name": "F254", "sha256": f254.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f254.get("physical_validation", {}).get("status"), "eligible": f254.get("candidate_eligible")},
        "latest_integrated_config_status_hold": {"name": "F255", "sha256": f255.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f255.get("physical_validation", {}).get("status"), "eligible": f255.get("candidate_eligible")},
        "latest_config_store_api_candidate": {"name": "F256", "sha256": f256.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f256.get("physical_validation", {}).get("status"), "eligible": f256.get("candidate_eligible")},
        "latest_integrated_config_api_hold": {"name": "F257", "sha256": f257.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f257.get("physical_validation", {}).get("status"), "eligible": f257.get("candidate_eligible")},
        "latest_private_candidate": {"name": "F301", "sha256": f301.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f301_reconciliation.get("status"), "visibility": "private-single-device"},
        "legacy_integrated_hold": {"name": "F246", "sha256": f246.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f246.get("physical_validation", {}).get("status"), "eligible": f246.get("candidate_eligible")},
        "latest_storage_candidate": {"name": "F180", "sha256": f180.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f180.get("physical_validation", {}).get("status")},
        "latest_spi_probe": {"name": "F181", "sha256": f181.get("artifact", {}).get("sha256"), "hardware": f181.get("physical_validation")},
        "latest_storage_probe": {"name": "F182", "sha256": f182.get("artifacts", {}).get("webformat", {}).get("sha256"), "hardware": f182.get("physical_validation", {}).get("status")},
        "live": live,
        "requirements": requirements,
        **summary,
    }
    (out / "report.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    lines = ["# Lyoko release readiness", "", f"Release ready: **{result['release_ready']}**", "", "| Requirement | Status | Next action |", "|---|---|---|"]
    lines.extend(f"| {item['title']} | `{item['status']}` | {item['next_action']} |" for item in requirements)
    (out / "REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"release_ready": result["release_ready"], "counts": result["counts"], "report": str(out / "report.json")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
