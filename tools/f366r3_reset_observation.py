"""R3 observes the actual Quantenna banner omitted by the legacy reset counter.

The serial adapter inspects bytes already returned by the one existing reader.
It adds no reads/writes, commands, reset requests or hardware-cause inference.
CLI is a local-file audit and never creates a serial connection.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import time

import f366_acquisition_executor as original

QUANTENNA_BANNER = b'Info: Quantenna U-Boot version:v36.7.0.30'
CEASE = 'OMF366_WDT_PHASE command=cease phase=cease-reboot-required acknowledgement=verified'


def is_missing_banner(line):
    # Exact protected Bootbase version observed on this unit. Do not match
    # quoted messages, command echoes, a substring, or another device banner.
    return line.strip(b'\0\r\n \t') == QUANTENNA_BANNER


def legacy_counts(line):
    return line.strip(b'\0\r \t') == b'Boot reached stage 13' or bool(re.match(rb'(?:U-Boot |Bootbase Version)', line.strip()))


class BannerObserver:
    def __init__(self, callback, clock=time.monotonic):
        self.callback = callback
        self.clock = clock
        self.pending = bytearray()
        self.pending_offset = 0
        self.bytes_seen = 0
        self.events = []
        self.oversized_lines = 0
        self.discarding_line = False
    def feed(self, data):
        self.bytes_seen += len(data)
        self.pending.extend(data)
        while b'\n' in self.pending:
            line, _, remainder = self.pending.partition(b'\n')
            size = len(line)+1
            if not self.discarding_line and is_missing_banner(bytes(line)):
                now = self.clock()
                event = dict(kind='quantenna_boot_banner', host_monotonic_ms=round(now*1000), stream_offset=self.pending_offset,
                             signature=QUANTENNA_BANNER.decode(), reset_cause='NOT_ATTESTED')
                self.events.append(event)
                self.callback(now, event)
            self.discarding_line = False
            self.pending[:] = remainder
            self.pending_offset += size
        if len(self.pending) > 4096:
            # Never retain an unbounded or sensitive unterminated payload.
            self.pending_offset += len(self.pending)
            self.pending.clear()
            self.oversized_lines += 1
            self.discarding_line = True


class ObservedSerial:
    """Transparent proxy: the old reader still makes every native I/O call."""
    __slots__ = ('_inner', '_observer')
    def __init__(self, inner, observer):
        object.__setattr__(self, '_inner', inner)
        object.__setattr__(self, '_observer', observer)
    def __getattr__(self, name):
        return getattr(self._inner, name)
    def __setattr__(self, name, value):
        if name in self.__slots__:
            object.__setattr__(self, name, value)
        else:
            setattr(self._inner, name, value)
    def read(self, size):
        data = self._inner.read(size)
        self._observer.feed(data)
        return data


class Uart(original.Uart):
    def __init__(self, plan, guard, out):
        super().__init__(plan, guard, out)
        factory = self.factory
        self.r3_observer = BannerObserver(self._r3_banner)
        self.factory = lambda: ObservedSerial(factory(), self.r3_observer)
    def _r3_banner(self, now, event):
        # This signature is deliberately disjoint from the old matcher, so
        # the unchanged legacy reader cannot double-count this same line.
        self.reset_times.append(now)
    def close(self):
        result = super().close()
        result['reset_observation_revision'] = 3
        result['quantenna_boot_banner_events'] = self.r3_observer.events
        result['reset_cause_attested'] = False
        return result


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(run_dir):
    run_dir = Path(run_dir)
    paths = {name: run_dir/name for name in ('result.json', 'uart-redacted.jsonl', 'diagnostic-events-r2.jsonl')}
    result = json.loads(paths['result.json'].read_text())
    uart = [json.loads(line) for line in paths['uart-redacted.jsonl'].read_text().splitlines()]
    events = [json.loads(line) for line in paths['diagnostic-events-r2.jsonl'].read_text().splitlines()]
    ceases = [row for row in events if row.get('source') == 'stdout' and row.get('text') == CEASE]
    cease = ceases[0] if len(ceases) == 1 else None
    banners = [row for row in uart if is_missing_banner(row.get('text', '').encode('ascii'))]
    after = [row for row in banners if cease and row['host_ms'] > cease['host_monotonic_ms']]
    banner = after[0] if len(after) == 1 else None
    prompts = [row for row in uart if banner and row['host_ms'] > banner['host_ms'] and re.fullmatch(r'topaz>\s*', row.get('text', ''))]
    prompt = prompts[0] if prompts else None
    controls = [row for row in uart if prompt and row['host_ms'] > prompt['host_ms'] and re.match(r'^f4000000:\s+00000000\b', row.get('text', ''))]
    hardware = result.get('post_reset_watchdog', {})
    no_host_recovery_recorded = not result.get('software_recovery', False) and not result.get('serial_recovery')
    within_return_wait = bool(cease and banner and 0 < banner['host_ms']-cease['host_monotonic_ms'] <= 95000)
    fresh = bool(within_return_wait and prompt and len(controls) >= 2 and hardware.get('fresh') is True and hardware.get('controls') == [0, 0] and no_host_recovery_recorded)
    mismatch = bool(fresh and result.get('diagnostic_reset_signatures') == 0 and not legacy_counts(banner['text'].encode('ascii')))
    return dict(schema='openmitrastar.f366r3-reset-observation-audit/v1',
                status='COUNTER_FALSE_NEGATIVE_CONFIRMED' if mismatch else 'RESET_SEQUENCE_NOT_ESTABLISHED',
                source_result_status=result.get('status'), source_reset_counter=result.get('diagnostic_reset_signatures'),
                cease_ack=cease, post_cease_boot_banner=banner, fresh_prompt=prompt, first_control_zero_reads=controls[:2],
                elapsed_cease_to_boot_banner_ms=banner['host_ms']-cease['host_monotonic_ms'] if banner and cease else None,
                elapsed_cease_to_prompt_ms=prompt['host_ms']-cease['host_monotonic_ms'] if prompt and cease else None,
                autonomous_reset_following_cease_observed=fresh, host_software_recovery_recorded=not no_host_recovery_recorded,
                legacy_banner_match=False if banner else None, reset_cause_register_captured=False,
                watchdog_hardware_qualification=False, native_acquisition_pass=False,
                interpretation='The actual new Bootbase banner follows acknowledged CEASE and was missed by the old anchored matcher. This does not attest the hardware reset cause or change native acquisition failure.',
                hardware_actions=False, source_files_unchanged=True,
                source_bindings={str(path.resolve()): sha(path) for path in paths.values()},
                observer_source=dict(path=str(Path(__file__).resolve()), sha256=sha(__file__)))


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error('new immutable output directory required')
    result = audit(args.run_dir)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    path = args.output_dir/'result.json'
    path.write_text(json.dumps(result, indent=2)+'\n', encoding='ascii')
    print(json.dumps(dict(result=str(path.resolve()), status=result['status'], elapsed_cease_to_boot_banner_ms=result['elapsed_cease_to_boot_banner_ms'], hardware_actions=False)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
