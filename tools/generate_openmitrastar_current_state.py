#!/usr/bin/env python3
"""Generate the authoritative OpenMitraStar current-state files from evidence."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JSON_OUT = ROOT / "work/mission-state/CURRENT_STATE.json"
MD_OUT = ROOT / "docs/OPENMITRASTAR_CURRENT_STATE.md"
F194 = ROOT / "work/mission-state/q3-recovery-f194-linux510-safety-slot/build/manifest.json"
F213 = ROOT / "work/mission-state/q3-persistent-composite-f213-movistar-f1-ui-from-f209/build/manifest.json"
PRIVATE_F222 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f222-device-bound/manifest.json"
PRIVATE_F223 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f223-device-bound/manifest.json"
PRIVATE_F224 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f224-device-bound/manifest.json"
PRIVATE_F225 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f225-device-bound/manifest.json"
PRIVATE_F226 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f226-device-bound/manifest.json"
PRIVATE_F227 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f227-device-bound/manifest.json"
PRIVATE_F228 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f228-device-bound/manifest.json"
PRIVATE_F229 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f229-device-bound/manifest.json"
PRIVATE_F230 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f230-device-bound/manifest.json"
PRIVATE_F231 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f231-device-bound/manifest.json"
PRIVATE_F232 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f232-device-bound/manifest.json"
PRIVATE_F233 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f233-device-bound/manifest.json"
PRIVATE_F234 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f234-device-bound/manifest.json"
PRIVATE_F235 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f235-device-bound/manifest.json"
PRIVATE_F236 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f236-device-bound/manifest.json"
PRIVATE_F237 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f237-device-bound/manifest.json"
PRIVATE_F238 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f238-device-bound/manifest.json"
PRIVATE_F239 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f239-device-bound/manifest.json"
PRIVATE_F240 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f240-device-bound/manifest.json"
PRIVATE_F241 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f241-device-bound/manifest.json"
PRIVATE_F242 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f242-device-bound/manifest.json"
PRIVATE_F243 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f243-device-bound/manifest.json"
PRIVATE_F244 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f244-device-bound/manifest.json"
PRIVATE_F245 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f245-device-bound/manifest.json"
PRIVATE_F246 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f246-device-bound/manifest.json"
PRIVATE_F247 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f247-device-bound/manifest.json"
PRIVATE_F248 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f248-device-bound/manifest.json"
PRIVATE_F249 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f249-device-bound/manifest.json"
PRIVATE_F250 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f250-device-bound/manifest.json"
PRIVATE_F251 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f251-device-bound/manifest.json"
PRIVATE_F252 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f252-device-bound/manifest.json"
PRIVATE_F253 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f253-device-bound/manifest.json"
PRIVATE_F254 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f254-device-bound/manifest.json"
PRIVATE_F255 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f255-device-bound/manifest.json"
PRIVATE_F256 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f256-device-bound/manifest.json"
PRIVATE_F257 = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f257-device-bound/manifest.json"
F222_FLASH = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f222-device-bound/flash-one-shot-20260902T080852Z/result.json"
F222_GATE = ROOT / "outputs/postflash/f222-device-20260902T080842Z/status.json"
F222_PACKAGES = ROOT / "outputs/postflash/f222-packages-20260902T080842Z/status.json"
F219_RADIO2_EVALUATION = ROOT / "outputs/f3-certification/f219-realtek-2g-napi128-evaluation.json"
F219_RADIO5 = ROOT / "outputs/f3-certification/qtn-5g-f219-32m-buffered-20260901T230840Z/evaluation-20260902-010841.json"
RECOVERY = ROOT / "outputs/recovery/mtd3-current-evidence-20260901/result.json"
RECOVERY_PROVISIONING = ROOT / "outputs/recovery/f194-provisioning-contract-20260901/contract.json"
STORE_FORMAT = ROOT / "outputs/storage/f211-lyoko-store-v1-20260901/manifest.json"
STORE_UPDATE = ROOT / "outputs/storage/f212-store-preserving-update-20260901/result.json"


def latest_live() -> tuple[Path, dict]:
    paths = sorted((ROOT / "outputs/current-state").glob("hgw500-*/status.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not paths:
        raise SystemExit("no current-state capture found")
    return paths[0], json.loads(paths[0].read_text(encoding="ascii"))


def artifact(manifest: dict, version: str, visibility: str) -> dict:
    return {
        "version": version,
        "classification": manifest["classification"],
        "visibility": visibility,
        "bytes": manifest["artifacts"]["webformat"]["bytes"],
        "sha256": manifest["artifacts"]["webformat"]["sha256"],
        "kernel_sha256": manifest["artifacts"]["kernel_lzma"]["sha256"],
        "hardware_validation": manifest["physical_validation"]["status"],
        "release_eligible": manifest.get("release_eligible", False),
    }


def main() -> int:
    live_path, live = latest_live()
    recovery = json.loads(RECOVERY.read_text(encoding="ascii"))
    recovery_provisioning = json.loads(RECOVERY_PROVISIONING.read_text(encoding="ascii"))
    store_format = json.loads(STORE_FORMAT.read_text(encoding="ascii"))
    store_update = json.loads(STORE_UPDATE.read_text(encoding="ascii"))
    f194 = json.loads(F194.read_text(encoding="ascii"))
    f213 = json.loads(F213.read_text(encoding="ascii"))
    f222 = json.loads(PRIVATE_F222.read_text(encoding="ascii"))
    f223 = json.loads(PRIVATE_F223.read_text(encoding="ascii"))
    f224 = json.loads(PRIVATE_F224.read_text(encoding="ascii"))
    f225 = json.loads(PRIVATE_F225.read_text(encoding="ascii"))
    f226 = json.loads(PRIVATE_F226.read_text(encoding="ascii"))
    f227 = json.loads(PRIVATE_F227.read_text(encoding="ascii"))
    f228 = json.loads(PRIVATE_F228.read_text(encoding="ascii"))
    f229 = json.loads(PRIVATE_F229.read_text(encoding="ascii"))
    f230 = json.loads(PRIVATE_F230.read_text(encoding="ascii"))
    f231 = json.loads(PRIVATE_F231.read_text(encoding="ascii"))
    f232 = json.loads(PRIVATE_F232.read_text(encoding="ascii"))
    f233 = json.loads(PRIVATE_F233.read_text(encoding="ascii"))
    f234 = json.loads(PRIVATE_F234.read_text(encoding="ascii"))
    f235 = json.loads(PRIVATE_F235.read_text(encoding="ascii"))
    f236 = json.loads(PRIVATE_F236.read_text(encoding="ascii"))
    f237 = json.loads(PRIVATE_F237.read_text(encoding="ascii"))
    f238 = json.loads(PRIVATE_F238.read_text(encoding="ascii"))
    f239 = json.loads(PRIVATE_F239.read_text(encoding="ascii"))
    f240 = json.loads(PRIVATE_F240.read_text(encoding="ascii"))
    f241 = json.loads(PRIVATE_F241.read_text(encoding="ascii"))
    f242 = json.loads(PRIVATE_F242.read_text(encoding="ascii"))
    f243 = json.loads(PRIVATE_F243.read_text(encoding="ascii"))
    f244 = json.loads(PRIVATE_F244.read_text(encoding="ascii"))
    f245 = json.loads(PRIVATE_F245.read_text(encoding="ascii"))
    f246 = json.loads(PRIVATE_F246.read_text(encoding="ascii"))
    f247 = json.loads(PRIVATE_F247.read_text(encoding="ascii"))
    f248 = json.loads(PRIVATE_F248.read_text(encoding="ascii"))
    f249 = json.loads(PRIVATE_F249.read_text(encoding="ascii"))
    f250 = json.loads(PRIVATE_F250.read_text(encoding="ascii"))
    f251 = json.loads(PRIVATE_F251.read_text(encoding="ascii"))
    f252 = json.loads(PRIVATE_F252.read_text(encoding="ascii"))
    f253 = json.loads(PRIVATE_F253.read_text(encoding="ascii"))
    f254 = json.loads(PRIVATE_F254.read_text(encoding="ascii"))
    f255 = json.loads(PRIVATE_F255.read_text(encoding="ascii"))
    f256 = json.loads(PRIVATE_F256.read_text(encoding="ascii"))
    f257 = json.loads(PRIVATE_F257.read_text(encoding="ascii"))
    f222_flash = json.loads(F222_FLASH.read_text(encoding="utf-8"))
    f222_gate = json.loads(F222_GATE.read_text(encoding="utf-8"))
    f222_packages = json.loads(F222_PACKAGES.read_text(encoding="utf-8"))
    f219_radio2 = json.loads(F219_RADIO2_EVALUATION.read_text(encoding="utf-8"))
    f219_radio5 = json.loads(F219_RADIO5.read_text(encoding="utf-8"))
    state = {
        "schema": "openmitrastar.authoritative-current-state/v1",
        "generated_at": live["captured_at"],
        "physical": {
            "evidence": str(live_path.relative_to(ROOT)),
            "firmware": live["firmware"],
            "kernel": live["kernel"],
            "boot_state": live["boot_state"],
            "degraded_services": live["degraded_services"],
            "radio2": live["radio2"],
            "radio5_state": live["radio5_state"],
            "fatal_count": live["fatal_count"],
            "normal_write_target": "mtd4/linux_live",
        },
        "recovery": {
            "current_mtd3": recovery["status"],
            "current_mtd3_sha256": recovery["mtd3"]["sha256"],
            "candidate": artifact(f194, "F194", "offline-recovery-only"),
            "provisioning_contract": {
                "status": recovery_provisioning["status"],
                "authorization_granted": recovery_provisioning["authorization"]["granted"],
                "target": recovery_provisioning["target"]["partition"],
                "candidate_sha256": recovery_provisioning["target"]["candidate_sha256"],
                "full_slot_sha256": recovery_provisioning["target"]["full_slot_sha256"],
            },
        },
        "candidates": {
            "generic": artifact(f213, "F213", "shareable-no-private-key"),
            "device_bound": {
                **artifact(f222, "F222", "private-single-device"),
                "hardware_validation": f222_gate.get("status", "NOT_RUN"),
            },
            "datapath": artifact(f223, "F223", "private-single-device-offline"),
            "foundation": artifact(f231, "F231", "private-single-device-offline"),
            "qtn_control_experiment": artifact(f233, "F233", "private-single-device-offline-hold"),
            "dual_control_superseded": artifact(f235, "F235", "private-single-device-superseded"),
            "hardened_control": artifact(f237, "F237", "private-single-device-hardware-test"),
            "dfs_observability": artifact(f239, "F239", "private-single-device-offline-hold"),
            "network_observability": artifact(f241, "F241", "private-single-device-offline-hold"),
            "hardware_provenance": artifact(f243, "F243", "private-single-device-offline-hold"),
            "package_catalog": artifact(f245, "F245", "private-single-device-offline-hold"),
            "integrated_hold": artifact(f246, "F246", "private-single-device-offline-hold"),
            "physical_test_candidate": artifact(f247, "F247", "private-single-device-hardware-test"),
            "opkg_compatibility": artifact(f248, "F248", "private-single-device-offline-hold"),
            "integrated_opkg_hold": artifact(f249, "F249", "private-single-device-offline-hold"),
            "led_control": artifact(f250, "F250", "private-single-device-offline-hold"),
            "integrated_led_hold": artifact(f251, "F251", "private-single-device-offline-hold"),
            "config_store": artifact(f252, "F252", "private-single-device-offline-hold"),
            "integrated_config_store_hold": artifact(f253, "F253", "private-single-device-offline-hold"),
            "config_store_status": artifact(f254, "F254", "private-single-device-offline-hold"),
            "integrated_config_status_hold": artifact(f255, "F255", "private-single-device-offline-hold"),
            "config_store_api": artifact(f256, "F256", "private-single-device-offline-hold"),
            "integrated_config_api_hold": artifact(f257, "F257", "private-single-device-offline-hold"),
        },
        "physical_validation": {
            "flash": f222_flash.get("status"),
            "postflash": f222_gate.get("status"),
            "packages": f222_packages.get("status"),
            "radio2_transport": "PASS" if f219_radio2.get("checks", {}).get("three_runs_passed_transport") else "FAIL",
            "radio2_optimization": f219_radio2.get("status"),
            "radio5": f219_radio5.get("status"),
        },
        "storage": {
            "format": "F211",
            "status": store_format["status"],
            "bytes": store_format["store"]["bytes"],
            "sha256": store_format["store"]["sha256"],
            "runtime_writes": store_format["policy"]["runtime_writes"],
            "update_simulation": "F212",
            "update_status": store_update["status"],
            "store_preserved": store_update["checks"]["store_preserved"],
            "full_mtd4_erase_allowed": store_update["write_contract"]["full_mtd4_erase_allowed"],
        },
        "release_blockers": [
            "validate the device-label credential through a real browser session",
            "restore AELITA SSH, then run the guarded F247 full physical campaign",
            "validate F233 native Quantenna SSID/channel/bandwidth apply and rollback on hardware",
            "validate F237 hardened Realtek and Quantenna transactions with real client reconnects and watchdog rollback",
            "restore AELITA SSH and certify multicast/IGMP with bidirectional real traffic",
            "provide an independent management path before attempting tagged VLAN traffic",
            "certify DFS/CAC/radar behavior",
            "validate F239 DFS readbacks against physical driver state before any regulated-channel test",
            "validate F241 multicast/VLAN readbacks before isolated tagged and multicast traffic tests",
            "run the guarded front-panel LED identification gate with an observer and record the physical colour/window mapping",
            "validate F245 signed package queries and volatile package lifecycle on the physical unit",
            "complete dual-radio 8-hour and 24-hour soaks",
        ],
    }
    JSON_OUT.write_text(json.dumps(state, indent=2) + "\n", encoding="ascii")
    generic = state["candidates"]["generic"]
    private = state["candidates"]["device_bound"]
    datapath = state["candidates"]["datapath"]
    foundation = state["candidates"]["foundation"]
    qtn_control = state["candidates"]["qtn_control_experiment"]
    dual_control = state["candidates"]["dual_control_superseded"]
    hardened_control = state["candidates"]["hardened_control"]
    dfs_observability = state["candidates"]["dfs_observability"]
    network_observability = state["candidates"]["network_observability"]
    hardware_provenance = state["candidates"]["hardware_provenance"]
    package_catalog = state["candidates"]["package_catalog"]
    integrated = state["candidates"]["integrated_hold"]
    physical_test = state["candidates"]["physical_test_candidate"]
    opkg_compatibility = state["candidates"]["opkg_compatibility"]
    integrated_opkg = state["candidates"]["integrated_opkg_hold"]
    led_control = state["candidates"]["led_control"]
    integrated_led = state["candidates"]["integrated_led_hold"]
    config_store = state["candidates"]["config_store"]
    integrated_config_store = state["candidates"]["integrated_config_store_hold"]
    config_store_status = state["candidates"]["config_store_status"]
    integrated_config_status = state["candidates"]["integrated_config_status_hold"]
    config_store_api = state["candidates"]["config_store_api"]
    integrated_config_api = state["candidates"]["integrated_config_api_hold"]
    MD_OUT.write_text(
        f"""# OpenMitraStar Current State

Generated from live and artifact evidence: `{state['generated_at']}`.

## Physical Unit

- Firmware: `{live['firmware']}`.
- Kernel: `{live['kernel']}`.
- Boot state: `{live['boot_state']}`.
- Degraded services: `{', '.join(live['degraded_services']) or 'none'}`.
- 2.4 GHz control plane: `{live['radio2']['state']}`.
- 5 GHz control plane: `{live['radio5_state']}`.
- Fatal markers: `{live['fatal_count']}`.

The physical unit runs F222 from `mtd4/linux_live`. Its persistent flash,
readback, SquashFS boot, SSH identity, web/API protection and dual-radio
control-plane gates are hardware-proven.

## Recovery

- Current mtd3: `{recovery['status']}`.
- Cause: valid kernel payload reaches Linux but cannot mount its rootfs.
- F194: offline Linux 5.10 safety-slot candidate, SHA-256 `{f194['artifacts']['webformat']['sha256']}`.
- F194 provisioning contract: `{recovery_provisioning['status']}`.
- F194 write authorization: `{recovery_provisioning['authorization']['granted']}`.

## Current Candidates

| Role | Version | Bytes | SHA-256 | Hardware |
|---|---|---:|---|---|
| Generic | {generic['version']} | {generic['bytes']} | `{generic['sha256']}` | {generic['hardware_validation']} |
| Device-bound | {private['version']} | {private['bytes']} | `{private['sha256']}` | {private['hardware_validation']} |
| Datapath experiment | {datapath['version']} | {datapath['bytes']} | `{datapath['sha256']}` | {datapath['hardware_validation']} |
| Foundation experiment | {foundation['version']} | {foundation['bytes']} | `{foundation['sha256']}` | {foundation['hardware_validation']} |
| Quantenna control experiment | {qtn_control['version']} | {qtn_control['bytes']} | `{qtn_control['sha256']}` | {qtn_control['hardware_validation']} |
| Superseded dual-radio experiment | {dual_control['version']} | {dual_control['bytes']} | `{dual_control['sha256']}` | {dual_control['hardware_validation']} |
| Hardened control candidate | {hardened_control['version']} | {hardened_control['bytes']} | `{hardened_control['sha256']}` | {hardened_control['hardware_validation']} |
| DFS observability experiment | {dfs_observability['version']} | {dfs_observability['bytes']} | `{dfs_observability['sha256']}` | {dfs_observability['hardware_validation']} |
| Network observability experiment | {network_observability['version']} | {network_observability['bytes']} | `{network_observability['sha256']}` | {network_observability['hardware_validation']} |
| Hardware provenance experiment | {hardware_provenance['version']} | {hardware_provenance['bytes']} | `{hardware_provenance['sha256']}` | {hardware_provenance['hardware_validation']} |
| Package catalog experiment | {package_catalog['version']} | {package_catalog['bytes']} | `{package_catalog['sha256']}` | {package_catalog['hardware_validation']} |
| Integrated hold | {integrated['version']} | {integrated['bytes']} | `{integrated['sha256']}` | {integrated['hardware_validation']} |
| Physical test candidate | {physical_test['version']} | {physical_test['bytes']} | `{physical_test['sha256']}` | {physical_test['hardware_validation']} |
| OpenWrt package CLI experiment | {opkg_compatibility['version']} | {opkg_compatibility['bytes']} | `{opkg_compatibility['sha256']}` | {opkg_compatibility['hardware_validation']} |
| Integrated OpenWrt package hold | {integrated_opkg['version']} | {integrated_opkg['bytes']} | `{integrated_opkg['sha256']}` | {integrated_opkg['hardware_validation']} |
| LED control experiment | {led_control['version']} | {led_control['bytes']} | `{led_control['sha256']}` | {led_control['hardware_validation']} |
| Integrated LED hold | {integrated_led['version']} | {integrated_led['bytes']} | `{integrated_led['sha256']}` | {integrated_led['hardware_validation']} |
| Configuration-store experiment | {config_store['version']} | {config_store['bytes']} | `{config_store['sha256']}` | {config_store['hardware_validation']} |
| Integrated configuration-store hold | {integrated_config_store['version']} | {integrated_config_store['bytes']} | `{integrated_config_store['sha256']}` | {integrated_config_store['hardware_validation']} |
| Configuration-store status | {config_store_status['version']} | {config_store_status['bytes']} | `{config_store_status['sha256']}` | {config_store_status['hardware_validation']} |
| Integrated configuration status hold | {integrated_config_status['version']} | {integrated_config_status['bytes']} | `{integrated_config_status['sha256']}` | {integrated_config_status['hardware_validation']} |
| Configuration-store API experiment | {config_store_api['version']} | {config_store_api['bytes']} | `{config_store_api['sha256']}` | {config_store_api['hardware_validation']} |
| Integrated configuration API hold | {integrated_config_api['version']} | {integrated_config_api['bytes']} | `{integrated_config_api['sha256']}` | {integrated_config_api['hardware_validation']} |

F213 remains the latest shareable generic image. F222 is the installed private
device-bound image with stable SSH identity and the complete dashboard behind
the session gate. Its signed volatile package lifecycle is hardware-proven. It
is not yet a final release.

F223 is the next private datapath candidate. Its rootfs, kernel configuration
and DTB are byte-identical to F222; the only datapath change is the EMAC RX
ring from 128 to 256 descriptors. It is built and offline-verified but has not
been flashed or performance-tested.

F231 is the next private product candidate. It keeps the F222 kernel and the
F229 hardware/package surface, then makes the 5 GHz control contract match the
real Linux 5.10 image: status remains readable, while SSID/channel/bandwidth
stay fail-closed until a qcsapi-compatible control backend is present.

F233 adds an experimental native Quantenna control backend using the already
working WEXT and hostapd-qtn binaries. It supports only SSID, non-DFS channels
36/40/44/48 and 20/40/80 MHz through the existing transactional rollback path.
It is offline-only until a physical change/reconnect/rollback campaign passes.

F235/F236 are superseded by the adversarial review. They lacked a real
unconfirmed-change watchdog and had insufficient Quantenna process recovery.

F237 adds verified automatic rollback, explicit commit, PID ownership checks,
`PONG` plus `state=ENABLED`, fail-closed DFS staging and UI reset on contract
failure. F239 adds read-only DFS/CAC/regulatory observability. F241 adds
read-only multicast, IGMP and VLAN state. F243 adds exact input GPIO and LED
provider provenance while explicitly reporting absent thermal/watchdog/gpiochip
interfaces. F244 combines the exact F223 kernel with the exact F243 rootfs.
F245 adds authenticated signed-catalog queries, searchable package metadata and
the exact dependency plan before any volatile install. F246 combines the exact
F223 RX-ring-256 kernel with the exact F245 rootfs; it remains an offline hold.
F247 promotes those exact F246 bytes into a guarded hardware-test envelope and
adds an F222-to-mtd4 rollback tool. Its preflight currently blocks before flash
only because AELITA SSH is unavailable; router SSH, COM3 and the traffic server
are ready.
F248 continues on a separate offline branch with a fail-closed `opkg` subset
over `lyoko-pkg`; it does not supersede the frozen F247 physical candidate.
F249 combines that exact F248 rootfs with the exact F223 RX-ring-256 kernel and
remains an offline integration hold.
F250 adds a feature-gated, time-bounded LED identification operation with exact
snapshot restoration. It remains offline until a person observes the panel.
F251 combines the exact F250 rootfs with the exact F223 kernel and remains an
offline integration hold.
F252 adds a disabled JFFS2 A/B configuration journal validated entirely in a
file-backed simulation. F253 combines it with the exact F223 kernel.
F254 exposes only the journal status through authenticated API/UI; persistence
writes remain disabled and the store remains unmounted.
F255 combines the exact F254 rootfs with the exact F223 kernel.
F256 adds confirmed, feature-gated journal commit/rollback controls while the
physical writable store remains disabled.
F257 combines the exact F256 rootfs with the exact F223 kernel.

## Physical Radio Validation

- 2.4 GHz: three 32 MiB bidirectional runs passed transport; median
  `{f219_radio2['candidate']['median_download_mbps']}` Mbps down and
  `{f219_radio2['candidate']['median_upload_mbps']}` Mbps up.
- NAPI-128 optimization decision: `{f219_radio2['decision']}`. The next driver
  change must target RX descriptor starvation rather than increasing NAPI
  weight again.
- 5 GHz: `{f219_radio5['status']}`, 32 MiB bidirectional plus 120-second
  continuity; `{f219_radio5['observed']['download_mbps']}` Mbps down and
  `{f219_radio5['observed']['upload_mbps']}` Mbps up with
  `{f219_radio5['observed']['router_samples']}` router samples.

## Storage

- F211 store format: `{store_format['status']}`, `{store_format['store']['bytes']}` bytes, SHA-256 `{store_format['store']['sha256']}`.
- F212 prefix-preserving update simulation: `{store_update['status']}`.
- Full `mtd4` erase after store initialization: `{store_update['write_contract']['full_mtd4_erase_allowed']}`.
- Runtime store writes remain disabled.
- Normal firmware updates erase only the `0x5e0000` firmware prefix of `mtd4`
  and preserve the `0x1c0000` `lyoko_store` tail.

## Release Blockers

""" + "".join(f"- {item}.\n" for item in state["release_blockers"]),
        encoding="utf-8",
    )
    print(json.dumps({"status": "PASS", "json": str(JSON_OUT), "markdown": str(MD_OUT), "physical": live["firmware"], "generic": generic["version"], "device_bound": private["version"], "datapath": datapath["version"], "foundation": foundation["version"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
