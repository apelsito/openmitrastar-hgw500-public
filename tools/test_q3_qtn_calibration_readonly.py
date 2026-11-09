#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path
import re
import struct
import unittest
import zlib


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "work/mission-state/q3-dual-radio-autostart/rootfs/usr/sbin/om-qtn-cal-readonly"
INIT = ROOT / "work/mission-state/q3-dual-radio-autostart/rootfs/etc/init.d/S53-qtn-calibration"
S55 = ROOT / "work/mission-state/q3-dual-radio-autostart/rootfs/etc/init.d/S55-radio5-ap"
START = ROOT / "work/mission-state/q3-dual-radio-autostart/rootfs/usr/sbin/om-radio5-start"
STATIC_TXPOWER = ROOT / "work/mission-state/q3-dual-radio-autostart/rootfs/usr/share/openmitrastar/qtn/txpower.cal"
BUILDER = ROOT / "tools/build_q3_dual_radio_autostart_overlay.py"
QDRV_COMM = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_comm.c"
QDRV_WLAN = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_wlan.c"
PRIMARY = ROOT / "outputs/flash-backups/hgw500-physical-ssh-20260820/current-unit/hgw500_mtdblock1.bin"
BACKUP = ROOT / "outputs/flash-backups/hgw500-physical-ssh-20260820/current-unit/hgw500_mtdblock2.bin"

EXPECTED = {
    "rx_iq.cal": (0x3420, 0x0308, 0x0032, "8.1", "ffd81386fb53e33d1fffafd63f47de80e4cbdff5bab05483e3456218e89c21d8"),
    "dc_iq.cal": (0x3728, 0x1A30, 0x0022, "8.1", "a0fc9669b325ea1768bbc645f3b0de04033eadbf0d7db46853c0da804a0b98a9"),
    "pdetector.cal": (0x5158, 0x0332, 0x0032, "8.1", "3154db2f885b0103564d0dd965ad230fbde874a6eb8b2b8ad40cb056f9d63cf1"),
}


def parse_cfg(raw: bytes, name: str) -> tuple[int, int]:
    match = re.findall(
        rb"(?:^|\x00)" + re.escape(name.encode()) + rb"=cfg 0x([0-9a-fA-F]{8}) 0x([0-9a-fA-F]{8})(?:\x00|$)",
        raw[:0x6000],
    )
    if len(match) != 1:
        raise AssertionError(f"{name}: expected one cfg record, got {len(match)}")
    return int(match[0][0], 16), int(match[0][1], 16)


def validate_header(blob: bytes, magic: int) -> str:
    actual_magic, version, _part, data_size, data_offset, elements, _checksum = struct.unpack_from("<HHIIHHI", blob)
    assert actual_magic == magic
    assert data_offset <= len(blob)
    assert 20 + elements * 8 + data_size == len(blob)
    return f"{version >> 8}.{version & 0xff}"


class QtnCalibrationReadonlyTests(unittest.TestCase):
    def test_current_unit_redundant_crc_and_records(self) -> None:
        primary = PRIMARY.read_bytes()
        backup = BACKUP.read_bytes()
        self.assertEqual(len(primary), 0x10000)
        self.assertEqual(len(backup), 0x10000)
        for raw in (primary, backup):
            stored = struct.unpack_from("<I", raw)[0]
            self.assertEqual(stored, zlib.crc32(raw[4:0x6000]) & 0xFFFFFFFF)
        for name, (offset, length, magic, version, digest) in EXPECTED.items():
            self.assertEqual(parse_cfg(primary, name), (offset, length))
            self.assertEqual(parse_cfg(backup, name), (offset, length))
            first = primary[offset : offset + length]
            second = backup[offset : offset + length]
            self.assertEqual(first, second)
            self.assertEqual(validate_header(first, magic), version)
            self.assertEqual(hashlib.sha256(first).hexdigest(), digest)

    def test_importer_is_target_gated_read_only_and_fail_closed(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        for marker in (
            "mitrastar,hgw-500bna-qcv2",
            "/usr/share/openmitrastar/qtn/txpower.cal",
            "copy_static_txpower",
            'cp "$static_txpower" "$stage/publish/txpower.cal"',
            "txpower_cal_sha256=$txpower_sha",
            "uboot_env",
            "uboot_env_bak",
            "append_matching_env",
            "append_optional_matching_env tx_power_QSR1000_es",
            "set +e",
            "set -e",
            "awk 'NF && !seen[$0]++ { print }'",
            "bootcfg_env=present",
            "bootcfg_env_sha256=$env_sha",
            "primary_crc=valid",
            "backup_crc=valid",
            "copies=match",
            "flash_writes=0",
            "type\")\" = rom",
            'chmod 0600 "$stage/publish/$name"',
            'mv "$stage/publish" "$runtime"',
            "OMQTNCAL_READY",
        ):
            self.assertIn(marker, text)
        for forbidden in ("flash_erase", "MEMERASE", "saveenv", "mtd_debug", "nandwrite", "dd of=\"$dev_root"):
            self.assertNotIn(forbidden, text)

    def test_init_order_and_runtime_gate(self) -> None:
        self.assertLess(INIT.name, "S54-qtn-mac")
        init = INIT.read_text(encoding="utf-8")
        s55 = S55.read_text(encoding="utf-8")
        start = START.read_text(encoding="utf-8")
        self.assertIn("exec /usr/sbin/om-qtn-cal-readonly", init)
        for marker in (
            "schema=openmitrastar.qtn-calibration/v1",
            "calibration-not-ready",
            "primary_crc=valid",
            "backup_crc=valid",
            "copies=match",
            "bootcfg_env=present",
            "flash_writes=0",
            "env",
            "txpower.cal",
        ):
            self.assertIn(marker, s55 + start)
        self.assertLess(start.index("calibration_gate"), start.index("load_module qtn_pm_qos_compat.ko"))

    def test_static_txpower_payload_is_the_oem_220_byte_blob(self) -> None:
        blob = STATIC_TXPOWER.read_bytes()
        self.assertEqual(len(blob), 220)
        self.assertEqual(
            hashlib.sha256(blob).hexdigest(),
            "3157e8a6c6aa10d758024219712ec9db5434064ee8bd5bde6f475ffdc488659f",
        )

    def test_qdrv_paths_change_only_under_v89_pair(self) -> None:
        comm = QDRV_COMM.read_text(encoding="utf-8")
        wlan = QDRV_WLAN.read_text(encoding="utf-8")
        self.assertRegex(
            comm,
            r"(?s)#ifdef OPENMITRASTAR_QDRV_V89_PAIR.*?/run/openmitrastar/calibration/dc_iq[.]cal.*?"
            r"/run/openmitrastar/calibration/pdetector[.]cal.*?/run/openmitrastar/calibration/env.*?"
            r"/run/openmitrastar/calibration/rx_iq[.]cal.*?"
            r"#else\s+static const char \* const cal_filenames\[\] = LHOST_CAL_FILES;\s+#endif",
        )
        self.assertIn("OMQTNCALFOPS stage=open-fail", comm)
        self.assertRegex(
            wlan,
            r"#ifdef OPENMITRASTAR_QDRV_V89_PAIR\s+#define PDETECTOR_IN_PROC "
            r"\"/run/openmitrastar/calibration/pdetector[.]cal\"\s+#else\s+"
            r"#define PDETECTOR_IN_PROC \"/proc/bootcfg/pdetector[.]cal\"\s+#endif",
        )

    def test_overlay_contract_includes_runtime_calibration_not_blobs(self) -> None:
        builder = BUILDER.read_text(encoding="utf-8")
        for marker in (
            '"device_calibration_bundled": False',
            '"device_calibration_runtime_import": True',
            '"source": "mtd1+mtd2-redundant-readonly"',
            '"txpower_cal_source": "/usr/share/openmitrastar/qtn/txpower.cal"',
            '"/usr/share/openmitrastar/qtn/txpower.cal"',
            '"bootcfg_env":',
            '"env"',
            '"txpower.cal"',
            '"qdrv_target_gate": "OPENMITRASTAR_QDRV_V89_PAIR"',
            'calibration_producer.is_file() and calibration_init.is_file()',
        ):
            self.assertIn(marker, builder)


if __name__ == "__main__":
    unittest.main(verbosity=2)
