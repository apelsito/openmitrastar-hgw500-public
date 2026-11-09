#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402
import build_f143_5g_deferred_dma_free_from_f142 as engine  # noqa: E402
import build_f146_5g_auc_submit_trace_from_f145 as f146  # noqa: E402
import build_f147_5g_readonly_get_from_f146 as f147  # noqa: E402


class F147ReadonlyGetBuilderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = (f146.OUT / f"{f146.BASE_OUT}.decompressed.bin").read_bytes()
        cls.patched, cls.report = f147.patch_cpio(cls.source)
        _, cls.old_entries, cls.old_remainder = f71.parse_first_cpio(cls.source)
        _, cls.new_entries, cls.new_remainder = f71.parse_first_cpio(cls.patched)
        cls.old_map = {entry.name: entry.data for entry in cls.old_entries}
        cls.new_map = {entry.name: entry.data for entry in cls.new_entries}

    def test_qdrv_replacement_is_exact_expected_build(self) -> None:
        old = self.old_map[engine.QDRV_ENTRY]
        new = self.new_map[engine.QDRV_ENTRY]
        self.assertEqual(f147.OLD_QDRV_SHA, hashlib.sha256(old).hexdigest())
        self.assertEqual(f147.NEW_QDRV_SHA, hashlib.sha256(new).hexdigest())
        self.assertIn(b"OMQDRVTXPATH stage=auc-submit", new)

    def test_payload_scope_is_fixed_and_wlan_is_unchanged(self) -> None:
        allowed = {
            engine.QDRV_ENTRY, engine.START_ENTRY, engine.DRIVER_CONTRACT_ENTRY,
            engine.HASHES_ENTRY, engine.PAD_ENTRY,
        }
        changed = {name for name in self.old_map if self.old_map[name] != self.new_map[name]}
        self.assertTrue(changed.issubset(allowed))
        self.assertEqual(self.old_map[engine.WLAN_ENTRY], self.new_map[engine.WLAN_ENTRY])
        self.assertEqual(len(self.source), len(self.patched))
        self.assertEqual(self.old_remainder, self.new_remainder)


if __name__ == "__main__":
    unittest.main(verbosity=2)
