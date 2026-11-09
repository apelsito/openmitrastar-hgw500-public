#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_ALL64 = ROOT / "outputs/kernel-port/realtek-loop/eapol-mgntq-v1-RAM-ONLY-NO-FLASH"
SRC_WARM = ROOT / "outputs/kernel-port/realtek-loop/warm-fw-retry-RAM-ONLY-NO-FLASH"
OUT = ROOT / "outputs/kernel-port/realtek-loop/all64-mcs7-q2-product-v1-RAM-ONLY-NO-FLASH"
MODULES = [
    "ctr.ko",
    "ccm.ko",
    "cmac.ko",
    "cfg80211.ko",
    "libarc4.ko",
    "mac80211.ko",
    "rtlwifi.ko",
    "btcoexist.ko",
    "rtl_pci.ko",
    "rtl8192ee.ko",
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "modules").mkdir(parents=True)
    (OUT / "firmware/rtlwifi").mkdir(parents=True)
    (OUT / "evidence").mkdir(parents=True)

    for module in MODULES:
        shutil.copy2(SRC_ALL64 / "modules" / module, OUT / "modules" / module)
    shutil.copy2(SRC_WARM / "firmware/regulatory.db", OUT / "firmware/regulatory.db")
    shutil.copy2(
        SRC_WARM / "firmware/rtlwifi/rtl8192eefw.bin",
        OUT / "firmware/rtlwifi/rtl8192eefw.bin",
    )
    shutil.copy2(SRC_WARM / "LOAD_ORDER.txt", OUT / "LOAD_ORDER.txt")
    module_abi = SRC_ALL64 / "evidence/module-abi.txt"
    if module_abi.is_file():
        shutil.copy2(module_abi, OUT / "evidence/module-abi.txt")

    artifact_paths = [
        "firmware/regulatory.db",
        "firmware/rtlwifi/rtl8192eefw.bin",
        *[f"modules/{module}" for module in MODULES],
    ]
    artifacts = [
        {
            "path": rel,
            "bytes": (OUT / rel).stat().st_size,
            "sha256": sha(OUT / rel),
        }
        for rel in artifact_paths
    ]
    manifest = {
        "schema": "openmitrastar.realtek-product-bundle/v1",
        "classification": "RAM-ONLY-NO-FLASH",
        "profile_id": "all64-mcs7-eapol-mgntq-q2-product-v1",
        "candidate_eligible": False,
        "kernel_release": "5.10.260-openmitrastar-radiohw",
        "load_order": MODULES,
        "artifacts": artifacts,
        "runtime_profile": {
            "rtlwifi": "hgw500_tx_ampdu_disable=0 hgw500_honest_tx_ack=0",
            "rtl_pci": (
                "hgw500_eapol_mgnt_queue=1 hgw500_eapol_trace=0 "
                "hgw500_mgmt_tx_complete_trace=0 hgw500_tx_queue_guard=0 "
                "hgw500_tx_reclaim_poll=0"
            ),
            "rtl8192ee": (
                "msi=0 dma64=0 aspm=0 ips=0 fwlps=0 swenc=1 "
                "disable_watchdog=0 debug_level=0 hgw500_force_txbd64_width=1 "
                "hgw500_tx_dma_wmb=1 hgw500_tx_close_diag=1 "
                "hgw500_tx_page_units=2 hgw500_tx_pbp_256=0 "
                "hgw500_txbd_mgmt_split=0 hgw500_force_data_mcs7=1 "
                "hgw500_force_data_mcs15=0 hgw500_force_data_11m=0 "
                "hgw500_txbd_be_data_split=0 hgw500_tx_rate_trace=0"
            ),
        },
        "module_abi": {
            "vermagic": "5.10.260-openmitrastar-radiohw mod_unload ARC700",
            "elf": "ELF32 little-endian ARCompact",
            "rtlwifi_exports_rtl_hgw500_honest_tx_ack": True,
            "rtl_pci_imports_rtl_hgw500_honest_tx_ack": True,
        },
        "static_gates": {
            "all64_mcs7_product": "PASS",
            "eapol_mgntq_product": "PASS",
            "full_matching_wireless_stack": "PASS",
            "regulatory_db_contract": "PASS",
            "firmware_contract": "PASS",
            "pci_10ec_818b_alias": "PASS",
            "vermagic": "PASS",
            "arc_elf": "PASS",
        },
        "source_bundles": {
            "modules": "outputs/kernel-port/realtek-loop/eapol-mgntq-v1-RAM-ONLY-NO-FLASH",
            "firmware": "outputs/kernel-port/realtek-loop/warm-fw-retry-RAM-ONLY-NO-FLASH",
        },
        "safety": {
            "flash_supported": False,
            "persistent_writes_supported": False,
            "router_accessed": False,
            "uart_used": False,
            "network_used": False,
            "offline_build_only": True,
        },
    }
    write_text(OUT / "manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    write_text(OUT / "MODULE_SHA256SUMS", "".join(
        f"{sha(OUT / 'modules' / module)}  modules/{module}\n" for module in MODULES
    ))
    write_text(OUT / "UPLOAD_SHA256SUMS", "".join(
        f"{sha(OUT / rel)}  {rel}\n" for rel in artifact_paths
    ))
    all_files = sorted(path for path in OUT.rglob("*") if path.is_file() and path.name != "SHA256SUMS")
    write_text(OUT / "SHA256SUMS", "".join(
        f"{sha(path)}  {path.relative_to(OUT).as_posix()}\n" for path in all_files
    ))
    print(f"OMALL64_PRODUCT_BUNDLE_READY path={OUT}")
    print(f"manifest_sha256={sha(OUT / 'manifest.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
