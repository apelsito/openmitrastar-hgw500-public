#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "outputs/kernel-port/realtek-loop/all64-autorate-q2-hotload-RAM-ONLY-NO-FLASH"
APPLY = BUNDLE / "scripts/apply-all64-autorate.sh"
ROLLBACK = BUNDLE / "scripts/rollback-all64-autorate.sh"
WRAPPER = ROOT / "tools/run_w2_all64_autorate_after_q2.ps1"


def test_bundle_contains_matching_realtek_module_set() -> None:
    for relative in (
        "modules/ctr.ko",
        "modules/ccm.ko",
        "modules/cmac.ko",
        "modules/cfg80211.ko",
        "modules/libarc4.ko",
        "modules/mac80211.ko",
        "modules/rtlwifi.ko",
        "modules/btcoexist.ko",
        "modules/rtl_pci.ko",
        "modules/rtl8192ee.ko",
        "ram_insmod",
        "MODULE_SHA256SUMS",
    ):
        assert (BUNDLE / relative).is_file()


def test_apply_locks_exact_clean_all64_autorate_profile() -> None:
    text = APPLY.read_text(encoding="utf-8", errors="replace")
    for module in ("ctr", "ccm", "cmac", "cfg80211", "libarc4", "mac80211"):
        assert f'"$loader" "$bundle/modules/{module}.ko"' in text
    assert '"$loader" "$bundle/modules/rtl_pci.ko" || fail load-rtl-pci' in text
    for needle in (
        "hgw500_txbd_compact32 N",
        "hgw500_txbd_tx5_layout N",
        "hgw500_txbd_be_legacy64 N",
        "hgw500_tx_queue_guard N",
        "hgw500_txbd_final_readback N",
        "hgw500_tx_reclaim_poll N",
        "hgw500_force_txbd64_width=1",
        "hgw500_tx_dma_wmb=1",
        "hgw500_tx_close_diag=1",
        "hgw500_tx_page_units=2",
        "hgw500_tx_pbp_256=0",
        "disable_watchdog=0",
        "hgw500_force_data_mcs7=0",
        "hgw500_force_data_mcs15=0",
        "hgw500_force_data_11m=0",
        "hgw500_txbd_be_data_split=0",
        "hgw500_tx_rate_trace=0",
        "global_compact32=0",
        "compact32=0 force64=1 bit15=1",
    ):
        assert needle in text


def test_apply_has_automatic_rollback_and_no_persistent_write() -> None:
    apply = APPLY.read_text(encoding="utf-8", errors="replace")
    rollback = ROLLBACK.read_text(encoding="utf-8", errors="replace")
    assert "rollback-all64-autorate.sh" in apply
    assert "OMALL64_ROLLBACK_PASS" in rollback
    combined = (apply + rollback).lower()
    for forbidden in ("/dev/mtd", "flash_erase", "nandwrite", "mtd write", "fw_setenv", "reboot", "com3"):
        assert forbidden not in combined


def test_wrapper_is_plan_only_by_default_and_ack_gated() -> None:
    text = WRAPPER.read_text(encoding="utf-8", errors="replace")
    assert "OMALL64_PLAN_ONLY_PASS=1" in text
    assert "OPENMITRASTAR_ALL64_AUTORATE_RAM_ONLY" in text
    assert "OPENMITRASTAR_ALL64_AUTORATE_ROLLBACK_RAM_ONLY" in text
    assert "if (-not $ExecuteHotload -and -not $ExecuteRollback)" in text
    assert "ramssh_upload.py" in text
    assert "ramssh_exec.py" in text
