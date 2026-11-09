"""F366r2 delta checks: synthetic telemetry/local pipes and prior return files."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import f366_acquisition_executor_r2 as capture
import f366r2_acquisition_worker as worker
import f366r2_native_evidence as native
import prepare_f366r2_acquisition as prepare
from test_f366_dfs_campaign import fixture as telemetry_fixture


def fixture():
    lines = []
    for phase in native.PHASES[:4]:
        lines += [f'OMF366_WDT_PHASE command=begin phase={phase} acknowledgement=verified',
                  'OMF366_WDT_PHASE command=complete phase=between-phases acknowledgement=verified']
    lines += ['OMF366_WDT_PHASE command=begin phase=native-radar acknowledgement=verified',
              'OMF366_WDT_PHASE command=verify phase=native-radar acknowledgement=verified',
              native.ATTEMPT, native.STARTED,
              'OMF366_WDT_PHASE command=complete phase=between-phases acknowledgement=verified',
              'OMF366_WDT_PHASE command=begin phase=pipeline-observe acknowledgement=verified']
    lines += telemetry_fixture().splitlines()
    lines += ['OMF366_WDT_PHASE command=complete phase=between-phases acknowledgement=verified',
              'OMF366_WDT_PHASE command=cease phase=cease-reboot-required acknowledgement=verified']
    return 'OMF366_WATCHDOG_ARM_ACK hardware=1 first_pet=1\n'+'\n'.join(lines)+'\n'


class DeltaTests(unittest.TestCase):
    def test_exact_once_and_six_phases(self):
        result = native.review_transcript(fixture())
        self.assertEqual(result['failures'], [])
        self.assertTrue(result['native_start_order_verified'])
        self.assertEqual(result['native_start_attempts'], 1)
        self.assertEqual(result['native_started_readbacks'], 1)

    def test_missing_duplicate_or_reordered_start_is_rejected(self):
        text = fixture()
        variants = [text.replace(native.ATTEMPT+'\n', ''), text.replace(native.STARTED+'\n', ''),
                    text+native.ATTEMPT+'\n', text.replace(native.ATTEMPT+'\n'+native.STARTED, native.STARTED+'\n'+native.ATTEMPT)]
        for invalid in variants:
            self.assertEqual(native.review_transcript(invalid)['status'], 'FAIL_CAPTURED_DIAGNOSTIC_TELEMETRY')

    def test_altered_region_or_authority_is_rejected(self):
        for invalid in (fixture().replace('radar-enable-eu', 'radar-enable-us'), fixture().replace('authority=0', 'authority=1', 1)):
            self.assertIn('native_start_attempt_not_exactly_once', native.review_transcript(invalid)['failures'])

    def test_current_return_evidence_must_be_closed_and_exact(self):
        root = Path(__file__).resolve().parents[1]
        prior = json.loads((root/'outputs/preflight/f365-install-20260922T092141Z/plan.json').read_text())
        result = json.loads(Path('/workspace/OpenMitraStar/f366-acquisition/f366-acquisition-20260922T095127Z-2149c8c9/result.json').read_text())
        self.assertTrue(prepare.validate_previous_return(result, prior)['exact_f365_return'])
        for key, value in [('retain_lease_required', True), ('baseline_returned', False), ('flash_command_in_flight', True)]:
            broken = copy.deepcopy(result)
            broken[key] = value
            with self.assertRaises(Exception):
                prepare.validate_previous_return(broken, prior)

    def test_real_local_pipe_capture_records_stdout_stderr_uart(self):
        text = fixture()+'unclassified synthetic text\n'
        class Host(worker.Host):
            def network_guard(self): return True
            def ssh_argv(self, command):
                if command != '/usr/sbin/om-f366-diagnostic activate '+'a'*32:
                    raise AssertionError('unexpected command')
                script = 'import sys;sys.stdout.buffer.write('+repr(text.encode())+');sys.stderr.buffer.write('+repr(b'synthetic error for capture test\n')+')'
                return [sys.executable, '-c', script]
        class Uart:
            failed = False
            data = b'RADAR: synthetic capture message\n'
            def invalidate_prompt(self): pass
            def stop_autoboot(self, seconds): pass
            def checkpoint(self): return 0
            def since(self, cursor): return self.data[cursor:]
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder)
            modules = (capture, capture.evidence)
            plan = dict(capture_revision=2, sources={str(Path(m.__file__).resolve()): worker.core.baseline.sha(m.__file__) for m in modules})
            host = Host(plan, out)
            result = host.diagnostic('a'*32, Uart(), out/'transcript.log')
            self.assertTrue(host.contain())
            self.assertEqual(result['status'], 'PASS_CAPTURED_DIAGNOSTIC_TELEMETRY')
            self.assertEqual(result['unrecorded_consumed_stdout_bytes'], 0)
            self.assertEqual(result['capture']['sources']['stdout']['bytes'], len(text.encode()))
            self.assertEqual(set(result['capture']['sources']), {'stdout', 'stderr', 'uart'})
            rows = [json.loads(line) for line in (out/'diagnostic-events-r2.jsonl').read_text().splitlines()]
            self.assertTrue(any(row['kind'] == 'unclassified' for row in rows))
            self.assertEqual(result['native_start_attempts'], 1)

    def test_worker_rejects_old_plan_without_capture_revision(self):
        with patch.object(worker.core, 'load_plan', return_value={}):
            with self.assertRaises(worker.core.Failure):
                worker.load_plan('not-used', 'not-used')


if __name__ == '__main__':
    unittest.main()
