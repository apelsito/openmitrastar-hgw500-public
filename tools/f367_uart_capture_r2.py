"""Passive UART semantic capture before the unchanged legacy redactor.

Composes the existing single-read serial proxy and R2 ledger/redactor. A bounded
writer queue keeps filesystem flushes out of the serial read path. This module
has no execution CLI and adds no serial reads, writes, radio actions or retries.
"""
from pathlib import Path
import hashlib
import json
import os
import queue
import re
import threading
import time

import f366_evidence_r2 as r2
import f366r3_reset_observation as reset

MAX_LINE = 8192
TOKEN_FIELD = re.compile(rb'(?i)("?(?:token|nonce|secret)"?\s*[:=]\s*)("[^"]*"|[^\s,}]+)')
BARE_TOKEN = re.compile(rb'(?i)(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])')
REASON = re.compile(r'^(OMRADIO5_REFUSED|OMF367_ERROR)\s+reason=([a-z][a-z0-9_-]{0,95})(?:\s|$)')


def redacted_event(raw):
    cleaned = raw.strip(b'\0\r\n \t')
    cleaned = TOKEN_FIELD.sub(rb'\1"[token-redacted]"', cleaned)
    cleaned = BARE_TOKEN.sub(b'[token-redacted]', cleaned)
    event = r2.redacted_event(cleaned)
    reason = REASON.match(cleaned.decode('ascii', 'replace'))
    if reason:
        # A firmware reason code such as calibration-not-ready is metadata.
        # Retain only that code, never other fields or calibration payload.
        event.update(kind='diagnostic', marker=reason[1],
                     text=reason[1]+' reason='+reason[2], reason_only=True)
    event['bytes'] = len(raw)
    event['redacted_sha256'] = hashlib.sha256(event['text'].encode('ascii')).hexdigest()
    return event


class Ledger(r2.Ledger):
    """R2 format/lifecycle with the narrowly scoped reason/token treatment."""
    def record_line(self, raw, observed_ms, offset, oversized=False):
        self.hashes.setdefault('uart', hashlib.sha256()).update(raw)
        self.counts['uart'] = self.counts.get('uart', 0)+len(raw)
        self.lines['uart'] = self.lines.get('uart', 0)+1
        self.sequence += 1
        item = redacted_event(raw) if not oversized else dict(
            bytes=len(raw), kind='oversized', text='[oversized-line-redacted]',
            redacted_sha256=hashlib.sha256(b'[oversized-line-redacted]').hexdigest())
        item.update(sequence=self.sequence, source='uart',
                    host_monotonic_ms=observed_ms, stream_offset=offset,
                    line_terminated=raw.endswith(b'\n'))
        self.stream.write(json.dumps(item)+'\n')
        self.stream.flush()
        os.fsync(self.stream.fileno())


class SemanticCapture:
    def __init__(self, path):
        self.path = Path(path)
        self.frames = queue.Queue(maxsize=128)
        self.thread = None
        self.ledger = None
        self.error = None
        self.raw_bytes = 0
        self.raw_hash = hashlib.sha256()
        self.dropped_bytes = 0
        self.summary = None
    def start(self):
        self.ledger = Ledger(self.path)
        self.thread = threading.Thread(target=self._write, name='F367-UART-ledger', daemon=True)
        self.thread.start()
    def feed(self, data):
        offset = self.raw_bytes
        self.raw_bytes += len(data)
        self.raw_hash.update(data)
        try:
            self.frames.put_nowait((offset, bytes(data), round(time.monotonic()*1000)))
        except queue.Full:
            self.error = self.error or 'semantic_queue_overflow'
            self.dropped_bytes += len(data)
    def _write(self):
        pending = bytearray()
        offset = 0
        observed_ms = 0
        discarding = False
        try:
            while True:
                frame = self.frames.get()
                if frame is None:
                    break
                frame_offset, data, observed_ms = frame
                if frame_offset != offset+len(pending):
                    self.error = self.error or 'semantic_stream_gap'
                    if pending:
                        self.ledger.record_line(bytes(pending), observed_ms, offset, oversized=True)
                    pending.clear();offset=frame_offset;discarding=True
                pending.extend(data)
                while b'\n' in pending:
                    index = pending.index(b'\n')+1
                    raw = bytes(pending[:index])
                    self.ledger.record_line(raw, observed_ms, offset, oversized=discarding or len(raw)>MAX_LINE)
                    del pending[:index];offset+=index;discarding=False
                if len(pending)>MAX_LINE:
                    self.ledger.record_line(bytes(pending), observed_ms, offset, oversized=True)
                    offset+=len(pending);pending.clear();discarding=True
            if pending:
                self.ledger.record_line(bytes(pending), observed_ms, offset, oversized=discarding)
        except Exception as error:
            self.error = self.error or type(error).__name__
        finally:
            try:self.summary = self.ledger.close()
            except Exception as error:self.error = self.error or type(error).__name__
    def close(self):
        if self.thread:
            try:self.frames.put(None, timeout=2)
            except queue.Full:self.error = self.error or 'semantic_writer_not_draining'
            self.thread.join(timeout=5)
            if self.thread.is_alive():self.error = self.error or 'semantic_writer_not_contained'
        return dict(schema='openmitrastar.f367-uart-semantic-capture/v1',
                    complete=self.error is None, error=self.error,
                    started=self.thread is not None, raw_bytes=self.raw_bytes,
                    raw_stream_sha256=self.raw_hash.hexdigest(),
                    dropped_bytes=self.dropped_bytes, ledger=self.summary,
                    raw_saved=False, extra_serial_reads=0, extra_serial_writes=0)


class Uart(reset.Uart):
    def __init__(self, plan, guard, out):
        super().__init__(plan, guard, out)
        factory = self.factory
        self.semantic = SemanticCapture(Path(out)/'uart-semantic-r2.jsonl')
        self.factory = lambda: reset.ObservedSerial(factory(), self.semantic)
    def open(self):
        self.semantic.start()
        return super().open()
    def close(self):
        try:
            result = super().close()
        finally:
            captured = self.semantic.close()
        result['semantic_capture'] = captured
        if not captured['complete']:
            result['reader_error'] = result.get('reader_error') or 'semantic_uart_capture_failed'
        return result
