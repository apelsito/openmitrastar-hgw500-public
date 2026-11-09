"""R3-only synthetic evidence gates and existing local F365 return binding."""
import copy
import json
from pathlib import Path
import unittest

import f366_dfs_campaign as fields
import f366_evidence_r2 as capture
import f366r3_native_evidence as native
import prepare_f366r3_acquisition as prepare

GUARD = 'OMF366_NATIVE_GUARD revision=3 reason=allow core_started=1 vap_created=1 attempt_used=0 args_eu=1 mac_present=1 wlan_present=1 opmode=6 channel_valid=1 channel=36 radar_bw=80 phymode=7 reads=ram-only'


def fixture():
    lines = ['OMF366_WATCHDOG_ARM_ACK hardware=1 first_pet=1']
    for phase in native.previous.PHASES[:5]:
        lines.append(f'OMF366_WDT_PHASE command=begin phase={phase} acknowledgement=verified')
        if phase == 'native-radar':
            lines += ['OMF366_WDT_PHASE command=verify phase=native-radar acknowledgement=verified', native.FILTER, native.previous.ATTEMPT, native.previous.STARTED]
        lines.append('OMF366_WDT_PHASE command=complete phase=between-phases acknowledgement=verified')
    lines.append('OMF366_WDT_PHASE command=begin phase=pipeline-observe acknowledgement=verified')
    for index in range(20):
        row = {key: 0 for key in fields.NUMERIC_FIELDS}
        row.update(schema='openmitrastar.f366-status/v1', provider_present=True, hardware_enabled=1, hardware_ready=1, hardware_dirty=1,
                   started=1, postfilter_applied=1, channel=36, jobs_completed=index+1, polls=index+1, ipc_sequence=index+1, ipc_session=1, ipc_generation=1)
        lines.append('OMF366_STATUS index='+str(index)+' json='+json.dumps(row))
    lines.append('OMF366_DIAGNOSTIC_COMPLETE observations=20 jobs_delta=20 authority=0 hardware_quiesced=0 reboot_required=1')
    return '\n'.join(lines), [dict(source='uart', text=GUARD)]


class R3DeltaTests(unittest.TestCase):
    def test_filter_and_ram_guard_pass_without_phymode_assumption(self):
        text, events = fixture()
        events[0]['text'] = GUARD.replace('phymode=7', 'phymode=61')
        result = native.review_transcript(text, events)
        self.assertEqual(result['failures'], [])
        self.assertEqual(result['native_guard_snapshot']['phymode'], '61')
        self.assertFalse(result['guard_cross_stream_order_claimed'])
        self.assertFalse(result['reset_cause_attested'])

    def test_filter_must_be_exact_once_before_enable(self):
        text, events = fixture()
        variants = [text.replace(native.FILTER, native.FILTER.replace('235', '234')), text.replace(native.FILTER+'\n', ''),
                    text+'\n'+native.FILTER, text.replace(native.FILTER+'\n', '')+'\n'+native.FILTER]
        for invalid in variants:
            self.assertEqual(native.review_transcript(invalid, events)['status'], 'FAIL_CAPTURED_DIAGNOSTIC_TELEMETRY')

    def test_denied_guard_is_preserved_and_cannot_pass(self):
        text, events = fixture()
        events[0]['text'] = GUARD.replace('reason=allow', 'reason=bandwidth').replace('radar_bw=80', 'radar_bw=0')
        result = native.review_transcript(text, events)
        self.assertIn('native_guard_not_allowed_exact_context', result['failures'])
        self.assertEqual(result['native_guard_snapshot']['reason'], 'bandwidth')
        self.assertEqual(result['native_guard_snapshot']['radar_bw'], '0')

    def test_capture_keeps_markers_and_requires_uart_guard(self):
        text, events = fixture()
        for line in (GUARD, GUARD.replace('reason=allow', 'reason=denied'), native.FILTER):
            item = capture.redacted_event((line+'\n').encode())
            self.assertEqual(item['kind'], 'diagnostic')
            self.assertEqual(item['text'], line)
        self.assertIn('native_guard_uart_snapshot_not_exactly_once', native.review_transcript(text+'\n'+GUARD, [])['failures'])
        duplicated = events+copy.deepcopy(events)
        self.assertIn('native_guard_uart_snapshot_not_exactly_once', native.review_transcript(text, duplicated)['failures'])

    def test_new_baseline_is_the_closed_r2_return_not_r2_success(self):
        root = Path(__file__).resolve().parents[1]
        prior = json.loads((root/'outputs/preflight/f365-install-20260922T092141Z/plan.json').read_text())
        result = json.loads(Path('/workspace/OpenMitraStar/f366-acquisition/f366r2-acquisition-20260922T103601Z-339fcd03/result.json').read_text())
        verified = prepare.validate_previous_return(result, prior)
        self.assertTrue(verified['failed_acquisition_preserved'])
        self.assertTrue(verified['exact_f365_return'])
        result['retain_lease_required'] = True
        with self.assertRaises(Exception):
            prepare.validate_previous_return(result, prior)


if __name__ == '__main__':
    unittest.main()
