#!/usr/bin/env python3
from __future__ import annotations

import re
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TREE = ROOT / "work/linux510-radio-port/quantenna"


class V89SharedPublisherTests(unittest.TestCase):
    def test_single_global_compile_knob(self) -> None:
        text = (TREE / "Makefile").read_text(encoding="utf-8")
        self.assertIn("subdir-ccflags-y += -DOPENMITRASTAR_QDRV_V89_PAIR=1", text)

    def test_soc_routes_once_through_gated_publisher(self) -> None:
        text = (TREE / "qdrv/qdrv_soc.c").read_text(encoding="utf-8")
        self.assertEqual(text.count("qdrv_v89_shared_publish_init("), 1)
        self.assertIn("sizeof(struct _shared_params_alloc) == QDRV_V89_SHARED_ALLOC_SIZE", text)
        self.assertIn("offsetof(struct _shared_params_alloc, nac_mon_info) == 0x6d7c", text)

    def test_default_and_gated_versions_are_separate(self) -> None:
        text = (TREE / "qdrv/qdrv_bld.h").read_text(encoding="utf-8")
        self.assertRegex(text, r"#ifndef OPENMITRASTAR_QDRV_V89_PAIR")
        self.assertIn("0x2504003e", text)
        self.assertIn("0x25040059", text)

    def test_every_gated_compile_command_has_macro(self) -> None:
        if os.environ.get("QTN_EXPECT_V89_CMD") != "1":
            self.skipTest("run immediately after the gated build with QTN_EXPECT_V89_CMD=1")
        commands = []
        for path in TREE.rglob("*.cmd"):
            if path.name.endswith(".mod.o.cmd"):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if " -c " in text and ".c" in text:
                commands.append(text)
        self.assertGreaterEqual(len(commands), 20)
        missing = [text[:120] for text in commands if "OPENMITRASTAR_QDRV_V89_PAIR=1" not in text]
        self.assertEqual(missing, [])

    def test_runtime_gate_remains_closed(self) -> None:
        gate = (ROOT / "work/mission-state/w3-offline/W3_RUNTIME_GATE.env").read_text(encoding="utf-8")
        self.assertIn("W3_PAIR_APPROVED=1", gate)
        self.assertIn("W3_HARDWARE_ACTIVE_APPROVED=0", gate)


if __name__ == "__main__":
    unittest.main(verbosity=2)
