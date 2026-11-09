"""F366r2-specific native-start evidence, in addition to r2 capture checks."""
import f366_evidence_r2 as capture

ATTEMPT = 'OMF366_NATIVE_START_ATTEMPT command=radar-enable-eu authority=0'
STARTED = 'OMF366_NATIVE_STARTED started=1 hardware_dirty=1 hardware_ready=1 authority=0'
PHASES = ['module-load', 'core-start', 'vap-create', 'radio-nondfs', 'native-radar', 'pipeline-observe']


def review_transcript(text):
    result = capture.review_transcript(text)
    lines = text.splitlines()
    attempts = [(index, line) for index, line in enumerate(lines) if line.startswith('OMF366_NATIVE_START_ATTEMPT')]
    started = [(index, line) for index, line in enumerate(lines) if line.startswith('OMF366_NATIVE_STARTED')]
    samples = [index for index, line in enumerate(lines) if line.startswith('OMF366_STATUS index=')]
    if len(attempts) != 1 or attempts[0][1] != ATTEMPT:
        result['failures'].append('native_start_attempt_not_exactly_once')
    if len(started) != 1 or started[0][1] != STARTED:
        result['failures'].append('native_started_readback_not_exactly_once')
    if len(attempts) == len(started) == 1 and (not samples or not attempts[0][0] < started[0][0] < samples[0]):
        result['failures'].append('native_start_order_not_proven')
    phases = [item['phase'] for item in result['phase_events'] if item['command'] == 'begin']
    if phases != PHASES:
        result['failures'].append('six_watchdog_phases_not_observed_in_order')
    native_health = 'OMF366_WDT_PHASE command=verify phase=native-radar acknowledgement=verified'
    health_positions = [index for index, line in enumerate(lines) if line == native_health]
    if not health_positions or not attempts or health_positions[0] >= attempts[0][0]:
        result['failures'].append('native_phase_health_before_attempt_unproven')
    result['failures'] = sorted(set(result['failures']))
    result['status'] = 'PASS_CAPTURED_DIAGNOSTIC_TELEMETRY' if not result['failures'] else 'FAIL_CAPTURED_DIAGNOSTIC_TELEMETRY'
    result['native_start_attempts'] = len(attempts)
    result['native_started_readbacks'] = len(started)
    result['native_start_order_verified'] = not any(item.startswith(('native_start_', 'native_started_', 'native_phase_', 'six_watchdog_')) for item in result['failures'])
    result['candidate_revision'] = 'f366r2'
    return result
