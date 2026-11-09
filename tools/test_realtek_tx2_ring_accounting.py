#!/usr/bin/env python3
from __future__ import annotations

import unittest


RING = 512


def rtl92ee_closed(index: int, rp: int, wp: int) -> bool:
    if wp > rp:
        return not (index < wp and index >= rp)
    if wp < rp:
        return index > wp and index < rp
    return index != rp


def oem_reclaim(sw_tail: int, hw_rp: int, size: int = RING) -> list[int]:
    reclaimed: list[int] = []
    while sw_tail != hw_rp:
        reclaimed.append(sw_tail)
        sw_tail = (sw_tail + 1) % size
    return reclaimed


class Tx2RingAccountingTests(unittest.TestCase):
    def test_observed_full_minus_one_head_is_not_reclaimable(self) -> None:
        self.assertFalse(rtl92ee_closed(index=204, rp=204, wp=203))
        self.assertEqual(oem_reclaim(sw_tail=204, hw_rp=204), [])

    def test_one_hardware_rp_advance_reclaims_exactly_once(self) -> None:
        self.assertTrue(rtl92ee_closed(index=204, rp=205, wp=203))
        self.assertEqual(oem_reclaim(sw_tail=204, hw_rp=205), [204])
        self.assertFalse(rtl92ee_closed(index=205, rp=205, wp=203))
        self.assertEqual(oem_reclaim(sw_tail=205, hw_rp=205), [])

    def test_wrap_reclaim_matches_oem_tail_to_rp_semantics(self) -> None:
        self.assertEqual(oem_reclaim(510, 2), [510, 511, 0, 1])
        for index in (510, 511, 0, 1):
            self.assertTrue(rtl92ee_closed(index=index, rp=2, wp=100))
        self.assertFalse(rtl92ee_closed(index=2, rp=2, wp=100))

    def test_compact_txbd_addresses_match_oem_stride(self) -> None:
        base = 0x04D40000
        compact = [base + i * 0x20 for i in range(RING)]
        self.assertEqual(compact[0], 0x04D40000)
        self.assertEqual(compact[1], 0x04D40020)
        self.assertEqual(compact[2], 0x04D40040)
        self.assertEqual(compact[-1] + 0x20, base + RING * 0x20)
        self.assertEqual(len(set(compact)), RING)

    def test_legacy_64_byte_stride_does_not_match_oem(self) -> None:
        base = 0x04D40000
        self.assertNotEqual(base + 1 * 0x40, base + 1 * 0x20)
        self.assertEqual(base + 256 * 0x40, base + RING * 0x20)


if __name__ == "__main__":
    unittest.main()
