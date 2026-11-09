"""Offline reason and redaction regressions; no RF or hardware actions."""
import json
from pathlib import Path
import tempfile
import unittest

import f366_evidence_r2 as evidence


class EvidenceTests(unittest.TestCase):
    def test_observation_failure_is_not_native_marker(self):
        result = evidence.review_transcript('OMF366_ERROR reason=observation-failed hardware_quiesced=0 reboot_required=1\n')
        self.assertNotIn('native_start_failed', result['failures'])
        self.assertIn('diagnostic_error:observation-failed', result['failures'])
        self.assertIs(result['native_failure_marker_observed'], False)
        self.assertEqual(result['status'], 'FAIL_CAPTURED_DIAGNOSTIC_TELEMETRY')

    def test_real_native_marker_still_fails(self):
        result = evidence.review_transcript('OMF366_NATIVE_FAILED watchdog_cease_requested=1 hardware_quiesced=0\n')
        self.assertIn('native_start_failed', result['failures'])
        self.assertIs(result['native_failure_marker_observed'], True)

    def test_phase_and_older_provider_markers_are_visible(self):
        rows = [b'OMF366_WDT_PHASE command=begin phase=core-start acknowledgement=verified\n', b'OMF338_STATUS service=ready\n', b'F341 radar_start failed errno=-5\n', b'RADAR: CAC started for channel 52\n']
        for raw in rows:
            self.assertEqual(evidence.redacted_event(raw)['kind'], 'diagnostic')
        result = evidence.review_transcript(rows[0].decode())
        self.assertEqual(result['phase_events'], [dict(command='begin', phase='core-start')])

    def test_sensitive_mac_token_and_arrays_redacted(self):
        for raw in (b'password=hunter2\n', b'calibration payload=1234\n', b'1000 2000 3000 4000\n'):
            self.assertNotIn(raw.decode().strip(), evidence.redacted_event(raw)['text'])
        text = evidence.redacted_event(b'OMF341_OWNER token=abcd mac=01:23:45:67:89:ab\n')['text']
        self.assertNotIn('abcd', text)
        self.assertNotIn('01:23:45:67:89:ab', text)

    def test_every_consumed_line_has_a_ledger_record(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'ledger.jsonl'
            ledger = evidence.Ledger(path)
            ledger.record('stdout', b'unknown text\n')
            ledger.record('stderr', b'cannot find module\n')
            ledger.record('uart', b'RADAR: disabled\n')
            summary = ledger.close()
            self.assertEqual(len(path.read_text().splitlines()), 3)
            self.assertEqual(summary['sources']['stdout']['bytes'], 13)
            rows = [json.loads(line) for line in path.read_text().splitlines()]
            self.assertEqual(rows[0]['kind'], 'unclassified')
            self.assertEqual(rows[1]['kind'], 'diagnostic')
            self.assertEqual(rows[2]['kind'], 'diagnostic')


if __name__ == '__main__':
    unittest.main()
