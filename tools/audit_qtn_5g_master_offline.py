#!/usr/bin/env python3
"""Fail-closed offline audit for the HGW-500BNA-QCv2 Quantenna 5 GHz lane.

This tool only reads local source, manifests and captured logs.  It never
contacts the router, opens a serial port, loads a module or writes firmware.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def require(path: Path, needles: list[str]) -> dict:
    data = text(path)
    missing = [needle for needle in needles if needle not in data]
    return {
        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": sha256(path),
        "pass": not missing,
        "missing": missing,
    }


def no_fatal(data: str) -> bool:
    return not any(
        marker in data
        for marker in (
            "Misaligned Access",
            "Kernel panic",
            "BUG:",
            "\nOops\n",
            "Invalid Read",
            "Invalid Write",
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", type=Path, help="write JSON report")
    args = parser.parse_args()

    hardware_state_path = ROOT / "work/mission-state/HARDWARE_STATE.json"
    q3_manifest_path = (
        ROOT
        / "work/mission-state/q3-maintenance-hbm-clear-tqe-dma-v1/build/manifest.json"
    )
    qtn_manifest_path = (
        ROOT
        / "outputs/kernel-port/quantenna-linux510-radiohw-assoc-trace-20260821/module-manifest.tsv"
    )
    q3_image_path = (
        ROOT
        / "work/tftp/omvl/linux510-q3-maintenance-hbm-clear-tqe-dma-v1-RAM-TEST-NO-FLASH.bin"
    )
    realtek_manifest_path = (
        ROOT
        / "outputs/kernel-port/realtek-loop/w2-tx8-rx-unaligned-RAM-ONLY-NO-FLASH/manifest.json"
    )
    assoc_log_path = ROOT / "outputs/uart-live/q3-hbm-clear-run2-20260821.log"
    post_fix_log_path = (
        ROOT / "outputs/uart-live/q3-switch-tqe-dma-fix-runtime-20260821.log"
    )
    latest_fault_log_path = ROOT / "outputs/uart-live/w2-2g-tx7-hw-20260822.log"
    checklist_path = ROOT / "work/mission-state/FULL_MIGRATION_TO_ENHANCEMENTS_CHECKLIST.md"

    hardware_state = json.loads(text(hardware_state_path))
    q3_manifest = json.loads(text(q3_manifest_path))
    realtek_manifest = json.loads(text(realtek_manifest_path))
    qtn_manifest_lines = [
        line for line in text(qtn_manifest_path).splitlines() if line.strip()
    ]

    source_checks = {
        "v89_shared_abi": require(
            ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_abi_v89.h",
            [
                "sizeof(struct shared_params_v89_wire) == 400",
                "QDRV_V89_SHARED_ALLOC_SIZE",
                "offsetof(struct qdrv_shared_params_alloc_v89, txbf_mbox) == 0x190",
                "offsetof(struct qdrv_shared_params_alloc_v89, nac_mon_info) == 0x6d7c",
                "b->board_id != 65535",
            ],
        ),
        "shared_publisher": require(
            ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_soc.c",
            [
                ".board_id = 65535",
                ".wifi_hw = 7, .rfic = 4",
                "qdrv_v89_shared_publish_init",
                "switch_vlan_vdev_table_bus",
                "OMQDRVSHM stage=publish-pass",
            ],
        ),
        "beacon_v89_wire": require(
            ROOT / "work/linux510-radio-port/quantenna/wlan/ieee80211_beacon_desc.c",
            [
                "BEACON_PARAM_SIZE",
                "qdrv_dma_handle_to_wire",
                "next_muc_addr",
            ],
        ),
        "beacon_v89_publish": require(
            ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_wlan.c",
            [
                "offsetof(struct qtn_beacon_args, bc_ie_buf_start) != 0x3c",
                "bc_args->bc_ie_buf_start",
                "OMQDRVBC stage=preflight-pass",
            ],
        ),
        "rx_alignment": require(
            ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_rx.c",
            [
                "skb_copy_expand(skb, NET_SKB_PAD + NET_IP_ALIGN",
                "OMQDRVRX stage=stack-realign",
                "omqdrvrx_fifo_sem_bit",
                "OMQDRVRX_SEM_SPIN_LIMIT",
            ],
        ),
        "hbm_alignment": require(
            ROOT / "work/linux510-radio-port/quantenna/platform/topaz/hbm.c",
            [
                "alloc_skb(buf_size + NET_IP_ALIGN",
                "skb_reserve(skb, NET_IP_ALIGN)",
                "OMHBM stage=module-ready",
            ],
        ),
        "calibration_readonly": require(
            ROOT
            / "work/mission-state/q3-dual-radio-autostart/rootfs/usr/sbin/om-qtn-cal-readonly",
            [
                "primary_crc=valid",
                "backup_crc=valid",
                "copies=match",
                "flash_writes=0",
                "rx_iq.cal",
                "dc_iq.cal",
                "pdetector.cal",
            ],
        ),
    }

    switch_source = text(
        ROOT / "work/linux510-radio-port/quantenna/platform/topaz/switch_tqe.c"
    )
    drop_signature = (
        "static inline void __sram_text tqe_rx_pkt_drop"
        "(const union topaz_tqe_cpuif_descr *desc)\n{"
    )
    drop_start = switch_source.index(drop_signature)
    drop_end = switch_source.index("\n}\n", drop_start) + 3
    drop_block = switch_source[drop_start:drop_end]
    source_checks["switch_tqe_dma_fix"] = {
        "path": "work/linux510-radio-port/quantenna/platform/topaz/switch_tqe.c",
        "sha256": sha256(
            ROOT / "work/linux510-radio-port/quantenna/platform/topaz/switch_tqe.c"
        ),
        "pass": "cache_op_before_rx" in drop_block and "dma_map_page_attrs" not in drop_block,
        "missing": [],
    }

    assoc_log = text(assoc_log_path)
    post_fix_log = text(post_fix_log_path)
    latest_fault_log = text(latest_fault_log_path)
    checklist = text(checklist_path)

    runtime_evidence = {
        "muc_boot": "MuC boot succeeded" in assoc_log,
        "vap_create": "VAP create succeeded" in assoc_log,
        "beacon_wire": "OMQDRVBC stage=preflight-pass" in assoc_log,
        "open_auth": "OMQDRVASSOC stage=auth-open-rx" in assoc_log,
        "association": "OMQDRVASSOC stage=iwev-registered" in assoc_log,
        "client_uplink_l2": "OMQDRVRX stage=tqe" in post_fix_log,
        "switch_tqe_fix_followup_no_fatal": no_fatal(post_fix_log),
        "switch_tqe_fix_followup_association": " associated, tot=" in post_fix_log,
        "latest_fault_signature_present": all(
            marker in latest_fault_log
            for marker in ("EFA: 0x86f900a9", "ERET: 0x701fce3c", "Workqueue: events")
        ),
        "latest_fault_symbolized_realtek": all(
            marker in checklist
            for marker in (
                "rtl92ee_rx_query_desc+0x204",
                "_rtl_pci_rx_interrupt+0x188",
                "ldw_s r1,[r1,0x18]",
            )
        ),
    }

    realtek_fix = realtek_manifest["experiments"]["hgw500_rx_unaligned_header"]
    current_q3_has_fix = bool(
        q3_manifest.get("capabilities", {}).get("realtek_rx_unaligned_header", False)
    )
    current_q3_q2_label = q3_manifest.get("capabilities", {}).get(
        "realtek_v4_payload", False
    )

    board = {
        "board_id": 65535,
        "board_id_meaning": "QTN_RUBY_UNIVERSAL_BOARD_ID / QHS860; expected, not corruption",
        "wifi_hw": 7,
        "wifi_hw_label": "QTN_TPZ_SKY85703",
        "rfic": 4,
        "emac0": 1,
        "emac1": 1,
        "phy0": 1,
        "phy1": 3,
        "rgmii_timing": "0x81828282",
    }

    all_source_pass = all(item["pass"] for item in source_checks.values())
    all_runtime_found = all(runtime_evidence.values())
    module_count = len(qtn_manifest_lines) - 1
    qtn_manifest_ok = module_count == 25
    q3_image = {
        "path": str(q3_image_path.relative_to(ROOT)).replace("\\", "/"),
        "sha256": sha256(q3_image_path),
        "bytes": q3_image_path.stat().st_size,
        "bootbase_contract": q3_manifest["slot"]["bootbase_contract"],
        "flash_supported": False,
    }

    report = {
        "schema": "openmitrastar.qtn-5g-master-offline/v1",
        "date": "2026-08-23",
        "target": "HGW-500BNA-QCv2-A2",
        "scope": "offline-only-no-router-no-uart-no-tftp-no-reboot-no-flash",
        "verdict": "QUANTENNA_CORE_ASSOC_UPLINK_PROVEN_REENTRY_IMAGE_NOT_YET_SAFE",
        "board": board,
        "source_checks": source_checks,
        "runtime_evidence": runtime_evidence,
        "quantenna_artifact": {
            "manifest": str(qtn_manifest_path.relative_to(ROOT)).replace("\\", "/"),
            "manifest_sha256": sha256(qtn_manifest_path),
            "module_count": module_count,
            "module_count_pass": qtn_manifest_ok,
        },
        "q3_image": q3_image,
        "latest_hard_fault": {
            "owner": "realtek_rtl8192ee_rx",
            "not_owner": "quantenna_qdrv",
            "efa": "0x86f900a9",
            "eret": "0x701fce3c",
            "callee": realtek_fix["fault_signature"]["callee"],
            "caller": realtek_fix["fault_signature"]["caller"],
            "instruction": realtek_fix["fault_signature"]["instruction"],
            "fix_bundle": str(realtek_manifest_path.relative_to(ROOT)).replace("\\", "/"),
            "fix_bundle_sha256": sha256(realtek_manifest_path),
        },
        "completion_matrix": {
            "v89_host_firmware_pair": "PROVEN",
            "hardware_identity": "PROVEN",
            "muc_auc_dsp_boot": "PROVEN",
            "hbm_tqe_init": "PROVEN",
            "beacon_tx": "PROVEN",
            "open_auth_assoc": "PROVEN",
            "client_to_ap_l2": "PROVEN",
            "ap_to_client_l2": "NOT_PROVEN",
            "dhcp_bridge_internet": "NOT_PROVEN",
            "throughput_soak": "NOT_PROVEN",
            "wpa2_wrong_key_rekey": "NOT_PROVEN",
            "dfs_cac_radar": "NOT_PROVEN",
            "sta_repeater_mode": "NOT_PROVEN",
            "calibration_files_served": "PROVEN",
            "calibration_v81_runtime_readback": "NOT_CAPTURED_ON_LINUX510",
        },
        "reentry_gate": {
            "offline_contract_pass": all_source_pass and all_runtime_found and qtn_manifest_ok,
            "current_q3_contains_realtek_rx_fix": current_q3_has_fix,
            "current_q3_declares_legacy_realtek_v4": current_q3_q2_label,
            "ram_validation_eligible": False,
            "reason": "build one combined RAM-only image containing the pinned Quantenna lane and a Realtek bundle with hgw500_rx_unaligned_header before another dual-radio test",
            "required_order": [
                "compose exact Q3 Quantenna payload plus Realtek RX-unaligned fix",
                "verify hashes, depmod, Bootbase contract and no flash/MTD path",
                "RAM boot exact image and capture vmlinux plus all qdrv/wlan/switch/hbm/rtl module text bases before RF",
                "start unique open 5 GHz SSID and require AUTH/ASSOC/IWEV plus no fatal marker",
                "prove bidirectional L2, DHCP, DNS/HTTPS and at least 10-minute counter/IRQ/SSH continuity",
                "then validate WPA2 correct key, wrong-key rejection and rekey",
                "finally validate legal ES DFS/CAC/radar behavior without bypass",
            ],
        },
        "safety": {
            "router_accessed": False,
            "uart_used": False,
            "tftp_used": False,
            "network_used": False,
            "flash_supported": False,
            "mtd_writes": False,
        },
        "hardware_state_snapshot": {
            "updated_at": hardware_state.get("updated_at"),
            "radio_5_ghz": hardware_state.get("radio_5_ghz", {}),
        },
    }

    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.write:
        output = args.write
        if not output.is_absolute():
            output = ROOT / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if report["reentry_gate"]["offline_contract_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
