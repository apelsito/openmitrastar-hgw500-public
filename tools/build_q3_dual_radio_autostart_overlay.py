#!/usr/bin/env python3
"""Build the deterministic Q3 secure dual-radio rootfs overlay.

This is an offline composer only.  It reads pinned local artifacts, writes a
rootfs overlay and deterministic tar archive, and never opens COM, SSH or MTD.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import tarfile
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/mission-state/q3-dual-radio-autostart/rootfs"
ARTIFACT = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-direct-symbols-20260820"
RELEASE = "5.10.260-openmitrastar-radiohw"
MODULE_SOURCE = ARTIFACT / f"rootfs/lib/modules/{RELEASE}/extra/quantenna"
HISTORICAL_QDRV = (
    ROOT
    / "outputs/kernel-port/quantenna-linux510-radiohw-rxalign-20260820"
    / f"rootfs/lib/modules/{RELEASE}/extra/quantenna/qdrv/qdrv.ko"
)
BEACON_PREFLIGHT = ROOT / "outputs/kernel-port/q3-beacon-wire-preflight-v1-20260821-0d9bf9e9"
BEACON_QDRV = BEACON_PREFLIGHT / "qdrv.ko"
BEACON_WLAN = BEACON_PREFLIGHT / "wlan.ko"
BEACON_MANIFEST = BEACON_PREFLIGHT / "manifest.json"
BEACON_FULL_MANIFEST = (
    ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-beacon-preflight-20260821/module-manifest.tsv"
)
BEACON_LIFETIME = Path(os.environ.get(
    "OM_Q3_BEACON_LIFETIME_ARTIFACT",
    ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-powerselect-seq-f46-20260825",
))
BEACON_LIFETIME_QDRV = Path(os.environ.get(
    "OM_Q3_BEACON_LIFETIME_QDRV_PATH",
    BEACON_LIFETIME
    / f"rootfs/lib/modules/{RELEASE}/extra/quantenna/qdrv/qdrv.ko",
))
BEACON_LIFETIME_WLAN = BEACON_LIFETIME / f"rootfs/lib/modules/{RELEASE}/extra/quantenna/wlan/wlan.ko"
BEACON_LIFETIME_SWITCH_VLAN = BEACON_LIFETIME / f"rootfs/lib/modules/{RELEASE}/extra/quantenna/platform/topaz/switch_vlan.ko"
BEACON_LIFETIME_MANIFEST = BEACON_LIFETIME / "BEACON_LIFETIME_MANIFEST.json"
BEACON_LIFETIME_FULL_MANIFEST = BEACON_LIFETIME / "module-manifest.tsv"
HOSTAPD = ROOT / "outputs/kernel-port/qtn-hostapd-madwifi-v5-open-authorize-20260821"
WIRELESS = ROOT / "outputs/kernel-port/qtn-wireless-tools-v4-noatomic-20260820"
POWER = ROOT / "outputs/radio-driver-kit-0.7/payload/etc/power_tables"
RAM_INSMOD = ROOT / "outputs/kernel-port/ram-insmod-nolibc/ram_insmod_nolibc"
COMPACT_SWITCH_TQE = (
    ROOT
    / "outputs/kernel-port/q3-switch-tqe-compact256-RAM-ONLY-NO-FLASH/switch_tqe.ko"
)
SRAMGATE_ARTIFACT = (
    ROOT
    / "outputs/kernel-port/quantenna-linux510-radiohw-direct-compact-tqe256-sramgate-20260820"
)
SRAMGATE_BOARD = (
    ROOT
    / "outputs/kernel-port/q3-board-compat-sramgate-RAM-ONLY-NO-FLASH/board_compat.ko"
)
BOOTENV_PRODUCER = (
    ROOT
    / "outputs/kernel-port/q3-bootenv-wifiaddr-readonly-v3-20260821-7ae702da/om-bootenv-readonly"
)
BOOTENV_PRODUCER_MANIFEST = (
    ROOT
    / "outputs/kernel-port/q3-bootenv-wifiaddr-readonly-v3-20260821-7ae702da/manifest.json"
)
EPOCH = 1787184000

PINNED = {
    ARTIFACT / "module-manifest.tsv": "f2b2c2369d22a38aa7868ab22838a707c2121cb1528a32f84759672f4ab96eee",
    MODULE_SOURCE / "platform/ruby/board_compat.ko": "827899bd46eb37e444c1351592fe725870f4e4da70605e3d641bdbca477bdd9a",
    SRAMGATE_ARTIFACT / "module-manifest.tsv": "7246a6cbac0b8a77ec17bfa9a52d2492e775a1a4feaf7047e57bd25737920ba1",
    SRAMGATE_BOARD: "0969752af8257a03a6951b82c5e1a269f4aeb99036e38cf6a781cf1a58cef97d",
    BOOTENV_PRODUCER: "7ae702dafca99b95fa95a0098a2662622278e10788869d70e00f61b5738fdb96",
    BOOTENV_PRODUCER_MANIFEST: "6d25f8c72cc083fa5a8b0a862d9b32dd0d81ff2c7dc69e2f3819602f80fe55ea",
    MODULE_SOURCE / "qdrv/qdrv.ko": "b406f17333fe41114a2d8f307d9d6e71fad3b96be210cf55e8110b4afc141ca2",
    HISTORICAL_QDRV: "9ba6cd3ff63e23fb03fc8e8d5cd6e93f9d710e0d56a0693852f4227cf9dabb20",
    BEACON_QDRV: "0d9bf9e92231e0db77b8c3320e09f7af40de691086618ab1d83464234f01f982",
    BEACON_WLAN: "f8449c18a08e46dfe9b9d581bb7eed060d3d260d5e9d36a5364913e3c5b561c8",
    BEACON_MANIFEST: "ac2c9690052e523002868b70d463b574e40eb603b1cb6390a5b0988a9d72650f",
    BEACON_FULL_MANIFEST: "47b0e2cb0b411266ce3fd90628f1a8004692222c4f125e708cc9142ea316291f",
    BEACON_LIFETIME_QDRV: os.environ.get(
        "OM_Q3_EXPECTED_BEACON_LIFETIME_QDRV_SHA256",
        "37527d16fa93325b676fde7247314fa0a9179095f3e6a7eb8dc19c63962b6f5f",
    ),
    BEACON_LIFETIME_WLAN: os.environ.get(
        "OM_Q3_EXPECTED_BEACON_LIFETIME_WLAN_SHA256",
        "09c5e347f6c0fa9acad4a7e0e3571d5d976a2cf4a5f0e304730eb825badbc872",
    ),
    BEACON_LIFETIME_SWITCH_VLAN: os.environ.get(
        "OM_Q3_EXPECTED_BEACON_LIFETIME_SWITCH_VLAN_SHA256",
        "595149bd0f87f69e1ec3aa9b42a29a8b8010302e8e2ae2dea58a4ae569649abc",
    ),
    BEACON_LIFETIME_MANIFEST: os.environ.get(
        "OM_Q3_EXPECTED_BEACON_LIFETIME_MANIFEST_SHA256",
        "76594d65396f4ddfbb2f890d91fe82cb798076ec8531adc48a41a1f85eb1b0a3",
    ),
    BEACON_LIFETIME_FULL_MANIFEST: os.environ.get(
        "OM_Q3_EXPECTED_BEACON_LIFETIME_FULL_MANIFEST_SHA256",
        "3f94ebe7f2fa924798992628af5db7ada10079b95ce340f6860cb29ca6aa3523",
    ),
    MODULE_SOURCE / "platform/topaz/switch_emac.ko": "9c45dcf6300b1ac668b73c3fce92d8e6f25599604850a293bbac0f0e58992c87",
    MODULE_SOURCE / "platform/topaz/hbm.ko": "c5084d18167b20f250718c2e97ad94bf36f059543eb37d7372513352b3aa357b",
    HOSTAPD / "hostapd": "3d9e89809bef74711f7e77addbbfdc6892245020accd7ab11605a7420ffd3f7e",
    HOSTAPD / "hostapd_cli": "67df5a9d7e6484101ac29f25c8f178cdea2bef51d4ea3f6fcdeeebb9eb033504",
    WIRELESS / "iwconfig": "5ebc31cb2ca69a1fbe1e0882f4aadba248e131a3b153c1d86d210ba53890c18b",
    WIRELESS / "iwpriv": "94c0d675a2d18fd0c259eb713e6a69d99fe6b2f73f2f838dc2fca2c2bf5f4edd",
    RAM_INSMOD: "8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6",
    COMPACT_SWITCH_TQE: "d41e530d65dae9ddbc5ff5893b9c44e07a829fba52759e466f71e26ba5d1047b",
}

MODULES = (
    "platform/ruby/qtn_pm_qos_compat.ko",
    "platform/ruby/qtn_platform_support.ko",
    "platform/ruby/board_compat.ko",
    "platform/ruby/runtime_compat.ko",
    "platform/ruby/iputil.ko",
    "platform/ruby/dmautil.ko",
    "platform/topaz/switch_vlan.ko",
    "platform/topaz/fwt_if.ko",
    "platform/topaz/hbm.ko",
    "platform/topaz/topaz_congest_queue.ko",
    "platform/ruby/emac_lib.ko",
    "platform/topaz/dpi.ko",
    "platform/topaz/switch_tqe.ko",
    "platform/topaz/switch_emac.ko",
    "platform/ruby/gpio.ko",
    "platform/qtsens/temp_sensor.ko",
    "platform/topaz/temp_sens.ko",
    "wlan/wlan.ko",
    "qdrv/qdrv.ko",
    "wlan/wlan_scan_ap.ko",
    "wlan/wlan_ccmp.ko",
    "wlan/wlan_xauth.ko",
)

PAYLOAD = (
    (ARTIFACT / "rootfs/lib/firmware/qtn_driver.qtn_ruby.0.bin", "lib/firmware/qtn_driver.qtn_ruby.0.bin", 0o600),
    (ARTIFACT / "rootfs/lib/firmware/auc_driver.nomu.0.bin", "lib/firmware/auc_driver.nomu.0.bin", 0o600),
    (ARTIFACT / "rootfs/lib/firmware/rdsp_driver.0.bin", "lib/firmware/rdsp_driver.0.bin", 0o600),
    (ARTIFACT / "rootfs/etc/qtn_regulatory_db.bin", "etc/qtn_regulatory_db.bin", 0o600),
    (POWER / "power_table.conf", "etc/power_tables/power_table.conf", 0o600),
    (POWER / "tx_power_QSR1000_es.txt", "etc/power_tables/tx_power_QSR1000_es.txt", 0o600),
    (HOSTAPD / "hostapd", "usr/sbin/hostapd-qtn", 0o755),
    (HOSTAPD / "hostapd_cli", "usr/sbin/hostapd-cli-qtn", 0o755),
    (WIRELESS / "iwconfig", "usr/sbin/iwconfig-qtn", 0o755),
    (WIRELESS / "iwpriv", "usr/sbin/iwpriv-qtn", 0o755),
    (RAM_INSMOD, "usr/sbin/ram-insmod-qtn", 0o755),
)

SOURCE_MODES = {
    "etc/init.d/S53-qtn-calibration": 0o755,
    "etc/init.d/S54-qtn-mac": 0o755,
    "etc/init.d/S55-radio5-ap": 0o755,
    "usr/share/openmitrastar/qtn/txpower.cal": 0o600,
    "usr/sbin/om-qtn-cal-readonly": 0o755,
    "usr/sbin/om-qtn-mac-prepare": 0o755,
    "usr/sbin/om-radio5-start": 0o755,
    "usr/sbin/om-radio5-stop": 0o755,
}
TARGET_MODES = SOURCE_MODES | {relative: mode for _, relative, mode in PAYLOAD}
TARGET_MODES["usr/sbin/om-bootenv-readonly"] = 0o755


def module_source(relative: str, profile: str = "secure") -> Path:
    # The compact ring is a Q3-only artifact.  The normal radiohw tree and its
    # default 512-entry switch_tqe remain untouched outside this overlay.
    if relative == "platform/topaz/switch_tqe.ko":
        return COMPACT_SWITCH_TQE
    if relative == "platform/ruby/board_compat.ko":
        return SRAMGATE_BOARD
    if relative == "qdrv/qdrv.ko" and profile == "open-lab-qdrv9ba6":
        return HISTORICAL_QDRV
    if profile == "open-lab-beacon-preflight":
        if relative == "qdrv/qdrv.ko":
            return BEACON_QDRV
        if relative == "wlan/wlan.ko":
            return BEACON_WLAN
    if profile == "open-lab-beacon-lifetime":
        if relative == "qdrv/qdrv.ko":
            return BEACON_LIFETIME_QDRV
        if relative == "wlan/wlan.ko":
            return BEACON_LIFETIME_WLAN
        if relative == "platform/topaz/switch_vlan.ko":
            return BEACON_LIFETIME_SWITCH_VLAN
    return MODULE_SOURCE / relative


def sha(path: Path, algorithm: str = "sha256") -> str:
    digest = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_inputs(profile: str) -> None:
    for path, expected in PINNED.items():
        if not path.is_file():
            raise SystemExit(f"missing pinned Q3 input: {path}")
        actual = sha(path)
        if actual != expected:
            raise SystemExit(f"pinned Q3 input drift: {path} expected={expected} actual={actual}")
    for relative in MODULES:
        path = module_source(relative)
        if not path.is_file():
            raise SystemExit(f"missing Q3 module: {relative}")
    for source, _, _ in PAYLOAD:
        if not source.is_file():
            raise SystemExit(f"missing Q3 payload: {source}")
    if any("fwt_ctrl" in item or "ioss" in item.lower() for item in MODULES):
        raise SystemExit("forbidden fwt_ctrl/IOSS module in Q3 order")
    if profile == "open-lab-beacon-lifetime" and \
            b"openmitrastar_beacon_v89_wire_enable" not in BEACON_LIFETIME_QDRV.read_bytes():
        raise SystemExit(
            "beacon lifetime qdrv is stale: build and pin the v89 wire-gated module first"
        )


def copy_file(source: Path, destination: Path, mode: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    os.chmod(destination, mode)
    os.utime(destination, (EPOCH, EPOCH))


def write_text_lf(path: Path, text: str, encoding: str = "ascii") -> None:
    path.write_text(text, encoding=encoding, newline="\n")


def profile_slug(profile: str) -> str:
    return {
        "secure": "dual-radio-autostart",
        "open-lab": "dual-radio-open-lab",
        "open-lab-tqe512": "dual-radio-open-lab-tqe512",
        "open-lab-qdrv9ba6": "dual-radio-open-lab-qdrv9ba6",
        "open-lab-beacon-preflight": "dual-radio-open-lab-beacon-preflight",
        "open-lab-beacon-lifetime": "dual-radio-open-lab-beacon-lifetime",
    }[profile]


def stage_rootfs(stage: Path, profile: str = "secure") -> dict[str, object]:
    open_lab = profile in {
        "open-lab", "open-lab-tqe512", "open-lab-qdrv9ba6",
        "open-lab-beacon-preflight",
        "open-lab-beacon-lifetime",
    }
    tqe512 = profile == "open-lab-tqe512"
    qdrv9 = profile == "open-lab-qdrv9ba6"
    beacon_preflight = profile == "open-lab-beacon-preflight"
    beacon_lifetime = profile == "open-lab-beacon-lifetime"
    shutil.copytree(SOURCE, stage)
    for path in stage.rglob("*"):
        if path.is_file():
            relative = path.relative_to(stage).as_posix()
            os.chmod(path, SOURCE_MODES.get(relative, 0o644))

    target_module_dir = stage / f"lib/modules/{RELEASE}/openmitrastar/radio5g"
    target_module_dir.mkdir(parents=True, exist_ok=True)
    artifact_rows: list[tuple[str, str]] = []
    module_rows: list[str] = []
    for relative in MODULES:
        source = module_source(relative, profile)
        name = source.name
        target = target_module_dir / name
        copy_file(source, target, 0o644)
        absolute = f"/{target.relative_to(stage).as_posix()}"
        artifact_rows.append((sha(target), absolute))
        module_rows.append(name)

    for source, relative, mode in PAYLOAD:
        target = stage / relative
        copy_file(source, target, mode)
        artifact_rows.append((sha(target), f"/{relative}"))
    txpower_cal = stage / "usr/share/openmitrastar/qtn/txpower.cal"
    if not txpower_cal.is_file():
        raise SystemExit("missing static qtn txpower.cal payload")
    if txpower_cal.stat().st_size != 220:
        raise SystemExit("unexpected static qtn txpower.cal size")
    artifact_rows.append((sha(txpower_cal), "/usr/share/openmitrastar/qtn/txpower.cal"))

    share = stage / "usr/share/openmitrastar/radio5g"
    share.mkdir(parents=True, exist_ok=True)
    write_text_lf(share / "modules.order", "\n".join(module_rows) + "\n")
    write_text_lf(
        share / "artifacts.sha256",
        "".join(f"{digest} {path}\n" for digest, path in artifact_rows),
    )
    power_md5 = sha(POWER / "tx_power_QSR1000_es.txt", "md5")
    write_text_lf(
        share / "runtime.env",
        "Q3_QDRV_SHA256=" + (
            PINNED[HISTORICAL_QDRV] if qdrv9 else
            PINNED[BEACON_LIFETIME_QDRV] if beacon_lifetime else
            PINNED[BEACON_QDRV] if beacon_preflight else
            PINNED[MODULE_SOURCE / "qdrv/qdrv.ko"]
        ) + "\n"
        "Q3_WLAN_SHA256=" + (
            PINNED[BEACON_LIFETIME_WLAN] if beacon_lifetime else
            PINNED[BEACON_WLAN] if beacon_preflight else
            sha(MODULE_SOURCE / "wlan/wlan.ko")
        ) + "\n"
        "Q3_BOARD_COMPAT_SHA256=" + PINNED[SRAMGATE_BOARD] + "\n"
        "Q3_SWITCH_EMAC_SHA256=" + PINNED[MODULE_SOURCE / "platform/topaz/switch_emac.ko"] + "\n"
        "Q3_HBM_SHA256=" + PINNED[MODULE_SOURCE / "platform/topaz/hbm.ko"] + "\n"
        "Q3_SWITCH_TQE_SHA256=" + PINNED[COMPACT_SWITCH_TQE] + "\n"
        "Q3_RAM_INSMOD_SHA256=" + PINNED[RAM_INSMOD] + "\n"
        "Q3_POWER_TABLE_MD5=" + power_md5 + "\n",
    )
    write_text_lf(share / "q3-radio5-autostart.feature", "Q3_RADIO5_AUTOSTART=1\n")
    producer = stage / "usr/sbin/om-qtn-mac-prepare"
    producer_init = stage / "etc/init.d/S54-qtn-mac"
    calibration_producer = stage / "usr/sbin/om-qtn-cal-readonly"
    calibration_init = stage / "etc/init.d/S53-qtn-calibration"
    bootenv_producer_ready = BOOTENV_PRODUCER.is_file() and BOOTENV_PRODUCER_MANIFEST.is_file()
    if bootenv_producer_ready:
        producer_manifest = json.loads(BOOTENV_PRODUCER_MANIFEST.read_text(encoding="utf-8"))
        expected = producer_manifest.get("binary_sha256")
        required_producer_contract = {
            "schema": "openmitrastar.bootenv-wifiaddr-producer/v1",
            "source": "mtd1+mtd2-redundant-readonly",
            "primary_label": "uboot_env",
            "backup_label": "uboot_env_bak",
            "partition_size": 0x10000,
            "logical_env_size": 0x6000,
            "crc32": "stored-little-endian-over-bytes-4-through-0x5fff",
            "key": "wifiaddr",
            "copies_must_match": True,
            "compatible": "mitrastar,hgw-500bna-qcv2",
            "mtd_type": "rom",
            "output": "/run/openmitrastar/bootenv/wifiaddr",
            "output_mode": "0600",
            "read_only": True,
            "writes_flash": False,
            "dtb_sha256": "50f854bfbc2cfa07d63f7ebe57bc4e452059f9cef2a0c59de4c48179cc0c93ed",
            "runtime": "arc700-syscall-only-no-libc-no-tls-no-atomics",
        }
        for key, wanted in required_producer_contract.items():
            if producer_manifest.get(key) != wanted:
                raise SystemExit(f"invalid Bootbase wifiaddr producer contract: {key}")
        if not isinstance(expected, str) or sha(BOOTENV_PRODUCER) != expected:
            raise SystemExit("Bootbase wifiaddr producer hash mismatch")
        copy_file(BOOTENV_PRODUCER, stage / "usr/sbin/om-bootenv-readonly", 0o755)
    feature_active = (
        producer.is_file() and producer_init.is_file() and
        calibration_producer.is_file() and calibration_init.is_file() and
        bootenv_producer_ready
    )
    if feature_active:
        active_feature = stage / "etc/openmitrastar/features/q3-radio5-autostart"
        copy_file(share / "q3-radio5-autostart.feature", active_feature, 0o644)
    if open_lab:
        if not feature_active:
            raise SystemExit("OPEN-LAB requires the validated automatic MAC producer")
        open_feature = stage / "etc/openmitrastar/features/q3-radio5-open-lab"
        open_feature.parent.mkdir(parents=True, exist_ok=True)
        write_text_lf(open_feature, "Q3_RADIO5_OPEN_LAB=1\n")
        os.chmod(open_feature, 0o644)
        os.utime(open_feature, (EPOCH, EPOCH))
    if tqe512:
        tqe_feature = stage / "etc/openmitrastar/features/q3-radio5-tqe512-discriminator"
        tqe_feature.parent.mkdir(parents=True, exist_ok=True)
        write_text_lf(tqe_feature, "Q3_RADIO5_TQE_RING_ENTRIES=512\n")
        os.chmod(tqe_feature, 0o644)
        os.utime(tqe_feature, (EPOCH, EPOCH))
    if qdrv9:
        qdrv_feature = stage / "etc/openmitrastar/features/q3-radio5-qdrv9ba6-discriminator"
        qdrv_feature.parent.mkdir(parents=True, exist_ok=True)
        write_text_lf(
            qdrv_feature,
            "Q3_RADIO5_QDRV_SHA256=9ba6cd3ff63e23fb03fc8e8d5cd6e93f9d710e0d56a0693852f4227cf9dabb20\n"
            "Q3_QDRV9BA6_ASSOCIATION_POLICY=visibility-first-short-window\n"
            "Q3_QDRV9BA6_ASSOCIATION_WINDOW_SECONDS=30\n",
        )
        os.chmod(qdrv_feature, 0o644)
        os.utime(qdrv_feature, (EPOCH, EPOCH))
    if beacon_preflight:
        beacon_feature = stage / "etc/openmitrastar/features/q3-radio5-beacon-preflight"
        beacon_feature.parent.mkdir(parents=True, exist_ok=True)
        write_text_lf(beacon_feature, "Q3_RADIO5_BEACON_PREFLIGHT=1\n")
        os.chmod(beacon_feature, 0o644)
        os.utime(beacon_feature, (EPOCH, EPOCH))
    if beacon_lifetime:
        lifetime_feature = stage / "etc/openmitrastar/features/q3-radio5-beacon-lifetime"
        lifetime_feature.parent.mkdir(parents=True, exist_ok=True)
        write_text_lf(lifetime_feature, "Q3_RADIO5_BEACON_LIFETIME=1\n")
        os.chmod(lifetime_feature, 0o644)
        os.utime(lifetime_feature, (EPOCH, EPOCH))
    contract = {
        "schema": "openmitrastar.q3-dual-radio-autostart/v1",
        "classification": (
            "OPEN-LAB-BEACON-LIFETIME-RAM-ONLY-NO-FLASH" if beacon_lifetime
            else "OPEN-LAB-BEACON-PREFLIGHT-RAM-ONLY-NO-FLASH" if beacon_preflight
            else "OPEN-LAB-QDRV9BA6-DISCRIMINATOR-RAM-ONLY-NO-FLASH" if qdrv9
            else "OPEN-LAB-TQE512-DISCRIMINATOR-RAM-ONLY-NO-FLASH" if tqe512
            else "OPEN-LAB-RAM-ONLY-NO-FLASH" if open_lab
            else "OFFLINE-PROVEN-HARDWARE-PENDING-NO-FLASH"
        ),
        "profile": profile,
        "target": "HGW-500BNA-QCv2-A2",
        "kernel_release": RELEASE,
        "management": {"path": "direct-eth0-preserved", "bridge": "br0"},
        "radio2g": {"interface": "wlan0", "preserved": True},
        "calibration": {
            "producer": "/usr/sbin/om-qtn-cal-readonly",
            "producer_sha256": sha(calibration_producer),
            "init": "/etc/init.d/S53-qtn-calibration",
            "init_sha256": sha(calibration_init),
            "source": "mtd1+mtd2-redundant-readonly",
            "runtime": "/run/openmitrastar/calibration",
            "files": ["rx_iq.cal", "dc_iq.cal", "pdetector.cal", "txpower.cal", "env"],
            "txpower_cal_source": "/usr/share/openmitrastar/qtn/txpower.cal",
            "bootcfg_env": "/run/openmitrastar/calibration/env",
            "crc_required": ["primary", "backup"],
            "copies_must_match": True,
            "output_mode": "0600",
            "flash_writes": False,
            "qdrv_target_gate": "OPENMITRASTAR_QDRV_V89_PAIR",
        },
        "radio5g": {
            "interface": "wifi0",
            "topology": "isolated-l3",
            "address": "192.168.77.1/24",
            "bridge_member": False,
            "vap_count": 1,
            "region_source": "/run/openmitrastar/origin-mtd5/wireless_conf.txt",
            "ssid_source": "/run/openmitrastar/origin-mtd5/runtime.conf",
            "psk_source": None if open_lab else "/run/openmitrastar/secrets/wpa2.psk",
            "psk_required": not open_lab,
            "private_mac_source": "/run/openmitrastar/secrets/qtn-mac0addr",
            "private_mac_producer": "/usr/sbin/om-qtn-mac-prepare",
            "private_mac_producer_init": "/etc/init.d/S54-qtn-mac",
            "private_mac_source_contract": "Bootbase mtd1+mtd2 wifiaddr, CRC-valid and equal",
            "bootenv_producer": "/usr/sbin/om-bootenv-readonly",
            "bootenv_producer_required_manifest": "openmitrastar.bootenv-wifiaddr-producer/v1",
            "bootenv_producer_validation": "hardware-pass-v3",
            "region": "ES",
            "channel": 36,
            "bandwidth_mhz": 80,
            "security": "OPEN" if open_lab else "WPA2-PSK-CCMP",
            "open_lab_feature": (
                "/etc/openmitrastar/features/q3-radio5-open-lab" if open_lab else None
            ),
            "qdrv_sha256": (
                PINNED[HISTORICAL_QDRV] if qdrv9 else
                PINNED[BEACON_LIFETIME_QDRV] if beacon_lifetime else
                PINNED[BEACON_QDRV] if beacon_preflight else
                PINNED[MODULE_SOURCE / "qdrv/qdrv.ko"]
            ),
            "wlan_sha256": (
                PINNED[BEACON_LIFETIME_WLAN] if beacon_lifetime else
                PINNED[BEACON_WLAN] if beacon_preflight else
                sha(MODULE_SOURCE / "wlan/wlan.ko")
            ),
            "qdrv_carrier_led_observer_gate": (
                "disabled-observer-only" if qdrv9 else "required"
            ),
            "qdrv9ba6_discriminator_feature": (
                "/etc/openmitrastar/features/q3-radio5-qdrv9ba6-discriminator"
                if qdrv9 else None
            ),
            "beacon_preflight_feature": (
                "/etc/openmitrastar/features/q3-radio5-beacon-preflight"
                if beacon_preflight else None
            ),
            "beacon_preflight_manifest_sha256": PINNED[BEACON_MANIFEST] if beacon_preflight else None,
            "beacon_preflight_full_manifest_sha256": PINNED[BEACON_FULL_MANIFEST] if beacon_preflight else None,
            "beacon_lifetime_feature": (
                "/etc/openmitrastar/features/q3-radio5-beacon-lifetime"
                if beacon_lifetime else None
            ),
            "beacon_lifetime_manifest_sha256": PINNED[BEACON_LIFETIME_MANIFEST] if beacon_lifetime else None,
            "beacon_lifetime_full_manifest_sha256": PINNED[BEACON_LIFETIME_FULL_MANIFEST] if beacon_lifetime else None,
            "board_compat_sha256": PINNED[SRAMGATE_BOARD],
            "board_compat_profile_manifest_sha256": PINNED[SRAMGATE_ARTIFACT / "module-manifest.tsv"],
            "board_compat_internal_target_gate": "mitrastar,hgw-500bna-qcv2",
            "dram_sram_fallback_q3": True,
            "dram_sram_fallback_default_outside_q3": False,
            "switch_emac_sha256": PINNED[MODULE_SOURCE / "platform/topaz/switch_emac.ko"],
            "switch_emac_mode": "symbols-only",
            "switch_tqe_sha256": PINNED[COMPACT_SWITCH_TQE],
            "switch_vlan_sha256": (
                PINNED[BEACON_LIFETIME_SWITCH_VLAN] if beacon_lifetime else
                sha(MODULE_SOURCE / "platform/topaz/switch_vlan.ko")
            ),
            "switch_tqe_rx_ring_entries": 512 if tqe512 else 256,
            "switch_tqe_default_outside_q3": 512,
            "tqe512_discriminator_feature": (
                "/etc/openmitrastar/features/q3-radio5-tqe512-discriminator"
                if tqe512 else None
            ),
            "module_loader": "/usr/sbin/ram-insmod-qtn",
            "module_loader_sha256": PINNED[RAM_INSMOD],
            "led": "GPIO1 carrier policy",
        },
        "forbidden": (
            ["fwt_ctrl", "IOSS reset pulse", "PSK use", "COM3", "flash"]
            if open_lab else
            ["fwt_ctrl", "IOSS reset pulse", "open AP", "bundled PSK", "COM3", "flash"]
        ),
        "rollback": "wifi0/RF/5G-hostapd only; eth0+wlan0+br0 preserved",
        "discriminator": (
            {
                "changed_dimension": "qdrv_beacon_lifetime_and_hostlink_serialization",
                "qdrv_sha256": PINNED[BEACON_LIFETIME_QDRV],
                "wlan_sha256": PINNED[BEACON_LIFETIME_WLAN],
                "callback_context": "workqueue",
                "terminal_ack": "DONE|ERR",
                "published_timeout": "quarantine",
                "mailbox_publish_doorbell": "serialized",
                "preflight_preserved": True,
                "module_parameters": [
                    "openmitrastar_beacon_preflight_enable=1",
                    "openmitrastar_beacon_v89_wire_enable=1",
                ],
                "marker_wait_seconds": 15,
                "marker_poll_seconds": 1,
                "required_markers": [
                    "OMQDRVBC stage=preflight-pass",
                    "OMQDRVBC stage=ioctl-send",
                ],
                "wait_health_gates": [
                    "hostapd-process-alive",
                    "hostapd-PONG",
                    "RF=1",
                    "no-fatal-or-quarantine",
                ],
                "wait_timeout_reason": "beacon-lifetime-markers-timeout",
            }
            if beacon_lifetime else
            {
                "changed_dimension": "qdrv_wlan_beacon_wire_preflight",
                "qdrv_sha256": PINNED[BEACON_QDRV],
                "wlan_sha256": PINNED[BEACON_WLAN],
                "module_parameter": "openmitrastar_beacon_preflight_enable=1",
                "default": 0,
                "diagnostic_value": 1,
                "fail_closed": True,
                "before_ioctl": "IOCTL_DEV_BEACON_START",
                "pass_marker": "OMQDRVBC stage=preflight-pass",
                "fail_marker": "OMQDRVBC stage=preflight-fail",
                "marker_fields": ["reason", "index", "count", "total", "used", "beacon_len", "head_dma", "args_dma"],
            }
            if beacon_preflight else
            {
                "changed_dimension": "qdrv_target_carrier_led_blocks",
                "a_value": "b406f17333fe41114a2d8f307d9d6e71fad3b96be210cf55e8110b4afc141ca2",
                "c_value": "9ba6cd3ff63e23fb03fc8e8d5cd6e93f9d710e0d56a0693852f4227cf9dabb20",
                "all_non_qdrv_binary_hashes_equal": True,
                "observer_only_gate_delta": "carrier/LED requirements disabled",
                "recommended_client_window_seconds": 30,
                "association_policy": "external harness must prove visibility before requesting association",
                "visibility_pass_sentinel": "/run/openmitrastar/radio5g/qdrv9ba6-visibility-pass",
                "association_open_sentinel": "/run/openmitrastar/radio5g/qdrv9ba6-association-window",
                "local_watchdog_seconds": 120,
                "persistent_or_flash": False,
            }
            if qdrv9 else
            {
                "changed_dimension": "switch_tqe_rx_ring_entries",
                "a_value": 256,
                "b_value": 512,
                "all_binary_hashes_equal": True,
                "reference_analysis": "work/mission-state/q3-open-lab-discriminator/w3-analysis.json",
            }
            if tqe512 else None
        ),
        "autostart_feature_gate": {
            "installed": feature_active,
            "candidate": "/usr/share/openmitrastar/radio5g/q3-radio5-autostart.feature",
            "activation": "/etc/openmitrastar/features/q3-radio5-autostart",
            "condition": "validated read-only Bootbase calibration and MAC producers plus S53/S54 gates",
            "reason": "bootenv-producer-present" if feature_active else "bootenv-producer-missing",
        },
    }
    write_text_lf(
        share / "runtime-contract.json",
        json.dumps(contract, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    for path in stage.rglob("*"):
        if path.is_file():
            os.utime(path, (EPOCH, EPOCH))
        elif path.is_dir():
            os.utime(path, (EPOCH, EPOCH))
    return contract


def deterministic_tar(stage: Path, output: Path) -> None:
    with output.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=EPOCH) as zipped:
            with tarfile.open(fileobj=zipped, mode="w", format=tarfile.GNU_FORMAT) as archive:
                for path in sorted(stage.rglob("*"), key=lambda item: item.relative_to(stage).as_posix()):
                    relative = path.relative_to(stage).as_posix()
                    info = archive.gettarinfo(str(path), arcname=relative)
                    info.uid = info.gid = 0
                    info.uname = info.gname = "root"
                    info.mtime = EPOCH
                    info.mode = 0o755 if path.is_dir() else TARGET_MODES.get(relative, 0o644)
                    if path.is_file():
                        with path.open("rb") as handle:
                            archive.addfile(info, handle)
                    else:
                        archive.addfile(info)


def compose_archive(output_dir: Path, suffix: str, profile: str) -> tuple[Path, dict[str, object]]:
    with tempfile.TemporaryDirectory(prefix=f"q3-dual-radio-{suffix}-") as directory:
        stage = Path(directory) / "rootfs"
        contract = stage_rootfs(stage, profile)
        slug = profile_slug(profile)
        archive = output_dir / f"openmitrastar-q3-{slug}-overlay-{suffix}.tar.gz"
        deterministic_tar(stage, archive)
    return archive, contract


def build(output_dir: Path, profile: str = "secure") -> Path:
    verify_inputs(profile)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_a, contract_a = compose_archive(output_dir, "a", profile)
    archive_b, contract_b = compose_archive(output_dir, "b", profile)
    hash_a = sha(archive_a)
    hash_b = sha(archive_b)
    if hash_a != hash_b or contract_a != contract_b:
        raise SystemExit(f"Q3 A/B reproducibility failure: a={hash_a} b={hash_b}")
    slug = profile_slug(profile)
    archive = output_dir / f"openmitrastar-q3-{slug}-overlay.tar.gz"
    shutil.copyfile(archive_a, archive)
    os.utime(archive, (EPOCH, EPOCH))
    manifest = {
        "schema": "openmitrastar.q3-dual-radio-overlay-build/v1",
        "profile": profile,
        "classification": contract_a["classification"],
        "source_date_epoch": EPOCH,
        "archive": {"file": archive.name, "size": archive.stat().st_size, "sha256": sha(archive)},
        "reproducibility": {
            "builds": 2,
            "identical": True,
            "a": {"file": archive_a.name, "sha256": hash_a},
            "b": {"file": archive_b.name, "sha256": hash_b},
        },
        "module_count": len(MODULES),
        "fwt_ctrl_included": False,
        "ioss_operation_included": False,
        "psk_bundled": False,
        "psk_required": contract_a["radio5g"]["psk_required"],
        "private_mac_bundled": False,
        "device_calibration_bundled": False,
        "device_calibration_runtime_import": True,
        "hardware_actions": False,
        "network_actions": False,
        "flash_actions": False,
        "autostart_enabled_by_default": bool(
            contract_a["autostart_feature_gate"]["installed"]
        ),
        "contract": contract_a,
    }
    write_text_lf(
        output_dir / "manifest.json",
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return archive


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "work/mission-state/q3-dual-radio-autostart/build",
    )
    parser.add_argument(
        "--profile", choices=(
            "secure", "open-lab", "open-lab-tqe512", "open-lab-qdrv9ba6",
            "open-lab-beacon-preflight", "open-lab-beacon-lifetime",
        ),
        default="secure",
    )
    args = parser.parse_args()
    archive = build(args.output_dir.resolve(), args.profile)
    manifest = json.loads((args.output_dir.resolve() / "manifest.json").read_text(encoding="utf-8"))
    autostart_gate = "active" if manifest["autostart_enabled_by_default"] else "closed"
    print(
        "OMQ3_DUAL_RADIO_BUILD_PASS "
        f"sha256={sha(archive)} reproducible=2/2 modules={len(MODULES)} fwt_ctrl=0 ioss=0 "
        f"open_ap={1 if args.profile != 'secure' else 0} "
        f"profile={args.profile} secrets=external autostart_gate={autostart_gate} hardware=0 flash=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
