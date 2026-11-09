#!/usr/bin/env python3

import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "kernel-port" / "f303-oem-radar-re-20260904"
RADAR_KO = (
    ROOT
    / "work"
    / "hgw500-rootfs-live"
    / "squashfs-root"
    / "lib"
    / "modules"
    / "2.6.35.12"
    / "extra"
    / "radar"
    / "radar.ko"
)


class F303OemRadarEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.symbols = (OUT / "elf-symbols.txt").read_text(encoding="utf-8")
        cls.relocations = (OUT / "elf-relocations.txt").read_text(encoding="utf-8")
        cls.disassembly = (OUT / "objdump-dr.txt").read_text(encoding="utf-8")
        cls.rodata = (OUT / "rodata.txt").read_text(encoding="utf-8")
        cls.strings = (OUT / "strings-offsets.txt").read_text(encoding="utf-8")
        cls.radar_h = (ROOT / "work/sources/Quantenna-GPL/drivers/radar/radar.h").read_text()
        cls.detect_h = (ROOT / "work/sources/Quantenna-GPL/drivers/radar/detect.h").read_text()
        cls.qdrv = (
            ROOT / "work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv/qdrv_radar.c"
        ).read_text()

    def test_oem_module_hash(self):
        digest = hashlib.sha256(RADAR_KO.read_bytes()).hexdigest()
        self.assertEqual(
            digest,
            "3550945b4affe54ddc5dcc6a3d13bb4caed6f38e1a6d0fb7b295028381e58332",
        )

    def test_classifier_entry_symbols_and_sizes(self):
        for evidence in (
            "00009038   106 FUNC    GLOBAL DEFAULT    1 detect_radar_poll",
            "000090a4  1318 FUNC    GLOBAL DEFAULT    1 isit_itlv",
            "000095cc  3580 FUNC    GLOBAL DEFAULT    1 detect_radar",
            "0000a964   570 FUNC    GLOBAL DEFAULT    1 lsr_detect_poll",
            "0000c160  3216 FUNC    GLOBAL DEFAULT    1 lsr_detect",
        ):
            self.assertIn(evidence, self.symbols)

    def test_poll_worker_binding(self):
        self.assertIn(".text + 3af8", self.relocations)
        self.assertIn("radar_poll_work", self.rodata)
        self.assertIn("R_ARC_32_ME\tschedule_delayed_work", self.disassembly)

    def test_preprocess_binding(self):
        self.assertGreaterEqual(self.relocations.count(".text + 26e8"), 2)
        self.assertIn("radar_preprocess", self.strings)

    def test_pulse_fifo_mmio_is_present(self):
        for address in (
            "e609 1518",
            "e609 1530",
            "e609 156c",
            "e609 1570",
            "e640 1000",
            "e640 1400",
        ):
            self.assertIn(address, self.disassembly)

    def test_zero_crossing_layout_matches_header(self):
        for token in (
            "#define ZC_TO_READ_PER_POLLING",
            "#define WIN_PER_PULSE",
            "#define ZC_PER_PULSE",
            "#define QT4_RADAR_ZC_ADR",
        ):
            self.assertIn(token, self.radar_h)
        self.assertIn("e640 0dff", self.disassembly)
        self.assertIn("e640 0fff", self.disassembly)

    def test_classifier_prototypes_match_headers(self):
        for prototype in (
            "bool detect_radar(raw_pulse_t *s, int count, int count_last_window, zc_cb_t *zc_cb);",
            "bool detect_radar_poll(void);",
            "bool isit_itlv(unsigned *pri_vec);",
        ):
            self.assertIn(prototype, self.detect_h)

    def test_classifier_dispatch_calls_are_present(self):
        self.assertIn("R_ARC_32_ME\tisit_itlv", self.disassembly)
        self.assertIn("R_ARC_32_ME\tlsr_detect", self.disassembly)
        self.assertIn("R_ARC_32_ME\tlsr_detect_poll", self.disassembly)

    def test_internal_classifier_names_survive_in_rodata(self):
        for name in (
            "make_pulse_town",
            "find_center_pulse",
            "is_it_fh_radar",
            "check_for_fh_radar",
            "check_eu_weather_ocac",
            "verify_burst",
            "verify_chirp",
            "are_zcs_linear",
            "is_it_tone",
        ):
            self.assertIn(name, self.strings)

    def test_callback_store_and_indirect_call(self):
        self.assertIn("000000c4 <radar_register>", self.disassembly)
        self.assertIn("R_ARC_32_ME\t.bss+0x1070", self.disassembly)
        self.assertIn("4bbe:\t2022 0080", self.disassembly)

    def test_qdrv_callback_target(self):
        self.assertIn("static void mark_radar(void)", self.qdrv)
        self.assertIn("qdrv_radar_detected(qdrv_radar_cb.ic, 0);", self.qdrv)


if __name__ == "__main__":
    unittest.main()
