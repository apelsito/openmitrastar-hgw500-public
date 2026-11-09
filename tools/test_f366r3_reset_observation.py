"""Only parser/proxy tests and review of existing local UART evidence."""
from pathlib import Path
import unittest

import f366r3_reset_observation as observe


class ResetObservationTests(unittest.TestCase):
    def test_actual_banner_is_new_and_not_legacy(self):
        raw = b'\0\r'+observe.QUANTENNA_BANNER+b'\r'
        self.assertTrue(observe.is_missing_banner(raw))
        self.assertFalse(observe.legacy_counts(raw))
        self.assertFalse(observe.is_missing_banner(b'echo '+observe.QUANTENNA_BANNER))
        self.assertFalse(observe.is_missing_banner(b'log: '+observe.QUANTENNA_BANNER))
        self.assertFalse(observe.is_missing_banner(observe.QUANTENNA_BANNER+b' quoted'))

    def test_split_serial_chunks_are_observed_exactly_once(self):
        counted = []
        observer = observe.BannerObserver(lambda now, event: counted.append((now, event)), clock=lambda: 42.5)
        payload = b'other line\n\r'+observe.QUANTENNA_BANNER+b'\r\nnext\n'
        for byte in payload:
            observer.feed(bytes([byte]))
        self.assertEqual(len(counted), 1)
        self.assertEqual(counted[0][0], 42.5)
        self.assertEqual(observer.bytes_seen, len(payload))
        observer.feed(b'U-Boot legacy\nBoot reached stage 13\n')
        self.assertEqual(len(counted), 1)
        observer.feed(b'x'*5000)
        observer.feed(observe.QUANTENNA_BANNER+b'\n')
        self.assertEqual(len(counted), 1)
        observer.feed(observe.QUANTENNA_BANNER+b'\n')
        self.assertEqual(len(counted), 2)

    def test_proxy_preserves_calls_and_bytes_without_extra_io(self):
        class Serial:
            is_open = False
            def __init__(self): self.reads=[]; self.writes=[]
            def read(self, count): self.reads.append(count); return observe.QUANTENNA_BANNER+b'\n'
            def write(self, data): self.writes.append(data); return len(data)
            def open(self): self.is_open=True
            def close(self): self.is_open=False
        raw = Serial()
        events = []
        wrapped = observe.ObservedSerial(raw, observe.BannerObserver(lambda now, event: events.append(event)))
        wrapped.port='FAKE'
        wrapped.open()
        self.assertEqual(wrapped.read(100), observe.QUANTENNA_BANNER+b'\n')
        self.assertEqual(wrapped.write(b'fixture'), 7)
        wrapped.close()
        self.assertEqual(raw.port, 'FAKE')
        self.assertEqual(raw.reads, [100])
        self.assertEqual(raw.writes, [b'fixture'])
        self.assertEqual(len(events), 1)
        self.assertFalse(raw.is_open)

    def test_existing_r2_capture_proves_false_negative_without_rf_pass(self):
        run = Path('/workspace/OpenMitraStar/f366-acquisition/f366r2-acquisition-20260922T103601Z-339fcd03')
        result = observe.audit(run)
        self.assertEqual(result['status'], 'COUNTER_FALSE_NEGATIVE_CONFIRMED')
        self.assertEqual(result['elapsed_cease_to_boot_banner_ms'], 7922)
        self.assertTrue(result['autonomous_reset_following_cease_observed'])
        self.assertFalse(result['watchdog_hardware_qualification'])
        self.assertFalse(result['native_acquisition_pass'])


if __name__ == '__main__':
    unittest.main()
