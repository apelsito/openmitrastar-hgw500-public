"""New r2 capture adapter; original frozen F366 runner remains untouched.

CLI reviews existing local evidence only. Hardware use requires a separately
bound future plan/launcher that supplies this Host to the existing run core.
"""
from pathlib import Path
import argparse
import json
import os
import queue
import re
import subprocess
import threading
import time

import f366_acquisition_executor as original
import f366_evidence_r2 as evidence


class Host(original.Host):
    def diagnostic(self, token, uart, output):
        original.require(re.fullmatch('[0-9a-f]{32}', token), 'diagnostic_token')
        # A caller cannot silently use this changed capture with the old plan.
        original.require(self.plan.get('capture_revision') == 2 and
                         self.plan['sources'].get(str(Path(__file__).resolve())) == original.baseline.sha(__file__) and
                         self.plan['sources'].get(str(Path(evidence.__file__).resolve())) == original.baseline.sha(evidence.__file__), 'r2_capture_not_bound')
        original.require(self.network_guard(), 'network_guard_before_activation')
        uart.invalidate_prompt()
        uart.stop_autoboot(120)
        uart_cursor = uart.checkpoint()
        self.diagnostic_started = time.monotonic()
        process = subprocess.Popen(self.ssh_argv('/usr/sbin/om-f366-diagnostic activate '+token), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.children.append(process)
        messages = queue.Queue(maxsize=256)
        errors = []
        def reader(stream, source):
            total = 0
            try:
                while True:
                    raw = stream.readline(16385)
                    if not raw:
                        break
                    total += len(raw)
                    if total > 262144 or len(raw) > 16384:
                        errors.append('diagnostic_output_limit')
                        break
                    try:
                        messages.put((source, raw), timeout=1)
                    except queue.Full:
                        errors.append('diagnostic_output_queue_full')
                        break
            finally:
                try:
                    messages.put((source, None), timeout=1)
                except queue.Full:
                    errors.append('diagnostic_close_queue_full')
        for stream, source in ((process.stdout, 'stdout'), (process.stderr, 'stderr')):
            thread = threading.Thread(target=reader, args=(stream, source), daemon=True)
            self.threads.append(thread)
            thread.start()
        done = set()
        transcript = []
        uart_pending = bytearray()
        capture_refresh = time.monotonic()
        ledger = evidence.Ledger(output.with_name('diagnostic-events-r2.jsonl'))
        summary = None
        def capture_uart():
            nonlocal uart_cursor
            raw = uart.since(uart_cursor)
            uart_cursor += len(raw)
            uart_pending.extend(raw)
            while b'\n' in uart_pending:
                line, _, remainder = uart_pending.partition(b'\n')
                uart_pending[:] = remainder
                ledger.record('uart', bytes(line)+b'\n')
            if len(uart_pending) > 16384:
                ledger.record('uart', bytes(uart_pending))
                uart_pending.clear()
        with output.open('x', encoding='ascii', newline='\n') as target:
            try:
                while len(done) < 2:
                    original.require(time.monotonic()-self.diagnostic_started < 215, 'diagnostic_transport_deadline')
                    original.require(not uart.failed, 'uart_capture_failed')
                    original.require(not errors, errors[0] if errors else 'diagnostic_reader')
                    capture_uart()
                    if time.monotonic()-capture_refresh >= 45:
                        uart.stop_autoboot(120)
                        capture_refresh = time.monotonic()
                    try:
                        source, raw = messages.get(timeout=.2)
                    except queue.Empty:
                        continue
                    if raw is None:
                        done.add(source)
                        continue
                    item = ledger.record(source, raw)
                    # Every line is in the ledger; only redacted diagnostic
                    # lines enter the plain transcript consumed by the parser.
                    if source == 'stdout' and item['kind'] == 'diagnostic':
                        target.write(item['text']+'\n')
                        target.flush()
                        os.fsync(target.fileno())
                        transcript.append(item['text'])
                process.wait(timeout=3)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=3)
                try:
                    capture_uart()
                    if uart_pending:
                        ledger.record('uart', bytes(uart_pending))
                finally:
                    summary = ledger.close()
                    output.with_name('diagnostic-capture-r2.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='ascii')
        report = evidence.review_transcript('\n'.join(transcript))
        report.update(transport_exit_code=process.returncode, stderr_bytes=summary['sources'].get('stderr', {}).get('bytes', 0),
                      unrecorded_consumed_stdout_bytes=0, capture=summary,
                      watchdog_arm_marker=sum(line == 'OMF366_WATCHDOG_ARM_ACK hardware=1 first_pet=1' for line in transcript),
                      transcript_path=str(output), transcript_sha256=original.baseline.sha(output))
        return report


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--review-transcript', type=Path, required=True)
    parser.add_argument('--capture-summary', type=Path)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        parser.error('new immutable output directory required')
    transcript = args.review_transcript.resolve(strict=True)
    result = evidence.review_transcript(transcript.read_text(encoding='utf-8'))
    result['transcript'] = dict(path=str(transcript), sha256=original.baseline.sha(transcript))
    if args.capture_summary:
        old = json.loads(args.capture_summary.read_text())
        result['old_capture_limit'] = dict(discarded_stdout_bytes=old.get('nonallowlisted_stdout_bytes'),
                                           content_recoverable_from_this_file=False, original_result_unchanged=True)
    result['source_bindings'] = {str(Path(module.__file__).resolve()): original.baseline.sha(module.__file__) for module in (original, evidence)}
    args.output_dir.mkdir(parents=True, exist_ok=False)
    output = args.output_dir/'result.json'
    output.write_text(json.dumps(result, indent=2)+'\n', encoding='ascii')
    print(json.dumps(dict(result=str(output.resolve()), status=result['status'], native_failure_marker_observed=result['native_failure_marker_observed'], diagnostic_error_reasons=result['diagnostic_error_reasons'], hardware_actions=False)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
