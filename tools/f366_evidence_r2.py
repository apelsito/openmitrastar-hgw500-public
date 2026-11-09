"""F366 evidence correction: reason-specific failures and redacted event ledger.

File-only utilities. No hardware or original F366 source mutation occurs here.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import time

import f366_dfs_campaign as original

SENSITIVE = re.compile(r'password|passwd|passphrase|\bpsk\b|credential|ap_pin|wps[._ ]pin|private[._ ]key|runtime[.]conf|settings[.]conf|\bkey=|calibration|raw[_ -]?(?:pulse|zc)|pulse[_ -]?(?:data|array|buffer)|\bzc[_ -]?(?:data|array|matrix|buffer)', re.I)
MAC = re.compile(r'(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}', re.I)
AUTH_TOKEN = re.compile(r'\b(token|nonce|secret)=([^\s,}]+)', re.I)
MARKER = re.compile(r'^(OM[A-Z0-9_]{2,80})(?:\s|$)')
ERROR = re.compile(r'^OMF366_ERROR reason=([a-z0-9-]{1,80}) hardware_quiesced=0 reboot_required=1$')
PHASE = re.compile(r'^OMF(?:338|341|366)_WDT_PHASE command=(begin|verify|complete|cease) phase=([a-z0-9-]{1,40}) acknowledgement=verified$')


def review_transcript(text):
    result = original.review_transcript(text)
    native_lines = [line for line in text.splitlines() if line.startswith('OMF366_NATIVE_FAILED')]
    reasons = []
    for line in text.splitlines():
        if not line.startswith('OMF366_ERROR '):
            continue
        match = ERROR.fullmatch(line)
        reasons.append(match[1] if match else 'malformed-error-marker')
    if not native_lines:
        result['failures'] = [item for item in result['failures'] if item != 'native_start_failed']
    result['failures'] += ['diagnostic_error:'+reason for reason in reasons]
    result['failures'] = sorted(set(result['failures']))
    result['status'] = 'PASS_CAPTURED_DIAGNOSTIC_TELEMETRY' if not result['failures'] else 'FAIL_CAPTURED_DIAGNOSTIC_TELEMETRY'
    result['schema'] = 'openmitrastar.f366-diagnostic-transcript-review/v2'
    result['native_failure_marker_observed'] = bool(native_lines)
    result['diagnostic_error_reasons'] = reasons
    result['phase_events'] = [dict(command=match[1], phase=match[2]) for line in text.splitlines() if (match := PHASE.fullmatch(line))]
    result['correction'] = 'OMF366_ERROR is not a native-start failure unless its actual reason or separate marker says so; acceptance gates are unchanged.'
    return result


def redacted_event(raw):
    text = raw.decode('ascii', 'replace').rstrip('\r\n')
    event = {'bytes': len(raw), 'kind': 'unclassified', 'text': '[unclassified-line-redacted]'}
    marker = MARKER.match(text)
    if marker:
        event['marker'] = marker[1]
    if SENSITIVE.search(text):
        event.update(kind='sensitive', text='[sensitive-line-redacted]')
    else:
        visible = MAC.sub('[mac-redacted]', text)
        visible = AUTH_TOKEN.sub(lambda match: match[1]+'=[token-redacted]', visible)
        # Preserve diagnostics, not uninterpreted pulse/calibration matrices.
        dense = re.search(r'(?:\b(?:0x)?[0-9a-f]{4,16}\b[ ,:;]+){3}', visible, re.I)
        scalar_dump = re.fullmatch(r'[\s0-9a-fx,;:\[\]{}.+-]+', visible, re.I)
        diagnostic = marker or re.search(r'\bRADAR\b|\bradar_(?:start|enable|disable|stop|ready)\b|\bqtn_radar_f(?:338|341|366)\b|\b(?:error|failed|failure|cannot|unable|timeout|refused|not found)\b', visible, re.I)
        if dense or scalar_dump:
            event.update(kind='unstructured-data', text='[unstructured-data-redacted]')
        elif diagnostic:
            event.update(kind='diagnostic', text=''.join(ch if 32 <= ord(ch) < 127 else '?' for ch in visible)[:4096])
    # Per-line digest is of REDACTED text. Do not make PSKs guessable by
    # publishing the digest of an individual discarded sensitive line.
    event['redacted_sha256'] = hashlib.sha256(event['text'].encode('ascii')).hexdigest()
    return event


class Ledger:
    """One record for every consumed line; raw content is never written."""
    def __init__(self, path):
        self.path = Path(path)
        self.stream = self.path.open('x', encoding='ascii', newline='\n')
        self.hashes = {}
        self.counts = {}
        self.lines = {}
        self.sequence = 0
    def record(self, source, raw):
        if source not in ('stdout', 'stderr', 'uart'):
            raise ValueError('unexpected_capture_source')
        self.hashes.setdefault(source, hashlib.sha256()).update(raw)
        self.counts[source] = self.counts.get(source, 0)+len(raw)
        self.lines[source] = self.lines.get(source, 0)+1
        self.sequence += 1
        item = dict(sequence=self.sequence, host_monotonic_ms=round(time.monotonic()*1000), source=source, **redacted_event(raw))
        self.stream.write(json.dumps(item)+'\n')
        self.stream.flush()
        os.fsync(self.stream.fileno())
        return item
    def close(self):
        self.stream.flush()
        self.stream.close()
        return dict(path=str(self.path), sha256=original.sha(self.path), raw_content_saved=False,
                    sources={key: dict(bytes=self.counts[key], lines=self.lines[key], stream_sha256=value.hexdigest()) for key, value in self.hashes.items()})
