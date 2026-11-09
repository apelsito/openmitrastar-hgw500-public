"""New clock evidence serialization only; no radio/timer behavior simulation."""
import unittest
import f367r7_clock_capture as capture

class ClockCapture(unittest.TestCase):
    def test_exact_numeric_snapshot_and_redaction(self):
        row={key:0 for key in capture.FIELDS};row.update(tick_hz=100,jiffies_u32=4294955000,boot_until_ticks=120000,quarantine_tick_remaining_ms=1229000,quarantine_ns_remaining_ms=0,quarantine_remaining_ms=1229000,quarantine_deadline_ms=1945983,transition_prepared=0,switch_inflight=0,secret='must-not-copy')
        before=dict(row);result=capture.clock_observation(row)
        self.assertFalse(result['missing_or_invalid_fields'])
        self.assertEqual(result['snapshot'],{key:row[key] for key in capture.FIELDS})
        self.assertEqual(row,before)
        self.assertFalse(result['physical_clock_drift_measured']);self.assertFalse(result['deadlines_modified'])
        trace=b'OMF367_POLICY_CLOCK_REJECT reason=boot-ticks policy_initialized=1 tick_hz=100 jiffies_u32=4294955000 boot_until_ticks=120000 nop_until_ticks=0 nop_policy=0 transition_prepared=0 monotonic_ns=1953860000000 quarantine_deadline_ns=1945983000000 nop_deadline_ns=0 quarantine_ns_remaining_ms=0 quarantine_tick_remaining_ms=1229000'
        self.assertEqual(capture.previous.capture.redacted_event(trace)['text'],trace.decode())
    def test_missing_invalid_are_explicit_not_synthesized(self):
        row={key:0 for key in capture.FIELDS};row.pop('jiffies_u32');row['tick_hz']='100';row['nop_policy']=True;row['boot_until_ticks']=-1
        result=capture.clock_observation(row)
        self.assertEqual(set(result['missing_or_invalid_fields']),{'jiffies_u32','tick_hz','nop_policy','boot_until_ticks'})
        self.assertNotIn('tick_hz',result['snapshot'])

if __name__=='__main__':unittest.main()
