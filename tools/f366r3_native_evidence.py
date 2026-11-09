"""R3 additionally proves the OEM radar filter setter and RAM-only guard."""
import re
import f366r2_native_evidence as previous

FILTER = 'OMF366_NATIVE_FILTER_CONFIG radar_bw=80 setter=ieee80211-param-235 authority=0'
GUARD_KEYS = {'revision', 'reason', 'core_started', 'vap_created', 'attempt_used', 'args_eu', 'mac_present', 'wlan_present', 'opmode', 'channel_valid', 'channel', 'radar_bw', 'phymode', 'reads'}
EXPECTED = dict(revision='3', reason='allow', core_started='1', vap_created='1', attempt_used='0', args_eu='1', mac_present='1', wlan_present='1', opmode='6', channel_valid='1', channel='36', radar_bw='80', reads='ram-only')


def guard_fields(line):
    if not line.startswith('OMF366_NATIVE_GUARD '):
        raise ValueError('guard_marker')
    result = {}
    for item in line.split()[1:]:
        key, separator, value = item.partition('=')
        if not separator or key in result:
            raise ValueError('guard_duplicate_or_malformed_field')
        result[key] = value
    if set(result) != GUARD_KEYS or not re.fullmatch(r'-?[0-9]+', result['phymode']):
        raise ValueError('guard_fields')
    return result


def review_transcript(text, events):
    result = previous.review_transcript(text)
    lines = text.splitlines()
    filters = [(index, line) for index, line in enumerate(lines) if line.startswith('OMF366_NATIVE_FILTER_CONFIG')]
    attempts = [index for index, line in enumerate(lines) if line == previous.ATTEMPT]
    if len(filters) != 1 or filters[0][1] != FILTER:
        result['failures'].append('radar_filter_235_80_not_exactly_once')
    if len(filters) == len(attempts) == 1 and filters[0][0] >= attempts[0]:
        result['failures'].append('radar_filter_not_before_enable')
    guards = [row for row in events if row.get('source') == 'uart' and row.get('text', '').startswith('OMF366_NATIVE_GUARD')]
    snapshot = None
    if len(guards) != 1:
        result['failures'].append('native_guard_uart_snapshot_not_exactly_once')
    else:
        try:
            snapshot = guard_fields(guards[0]['text'])
            if any(snapshot[key] != value for key, value in EXPECTED.items()):
                result['failures'].append('native_guard_not_allowed_exact_context')
        except ValueError:
            result['failures'].append('native_guard_uart_snapshot_invalid')
    result['failures'] = sorted(set(result['failures']))
    result['status'] = 'PASS_CAPTURED_DIAGNOSTIC_TELEMETRY' if not result['failures'] else 'FAIL_CAPTURED_DIAGNOSTIC_TELEMETRY'
    result.update(candidate_revision='f366r3', radar_filter_config_count=len(filters), native_guard_count=len(guards), native_guard_snapshot=snapshot,
                  guard_cross_stream_order_claimed=False, reset_cause_attested=False)
    return result
