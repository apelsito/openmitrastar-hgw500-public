"""In-memory evidence from one uninterrupted UART reader; never replay old logs.

Only bounded marker metadata survives ring rotation. Closing the capture, a
reader error or an unparseable oversized frame permanently destroys continuity.
There is deliberately no restore/import/hydrate API.
"""
import re
from f366r3_reset_observation import is_missing_banner, legacy_counts

MAX_LINE = 8192
LINUX = re.compile(rb'^(?:\[\s*[0-9]+\.[0-9]+\]\s*)?Linux version 5\.10\.260-openmitrastar-radiohw(?:\s|$)')
PROMPT = re.compile(rb'^(?:topaz>|ZHAL>)[ \t]*$')


class Epoch:
    def __init__(self):
        self.total = 0
        self.offset = 0
        self.pending = bytearray()
        self.linux_offset = self.reset_offset = self.prompt_offset = -1
        self.previous_linux_offset = -1
        self.linux_count = self.reset_count = self.prompt_count = 0
        self.failure = None
        self.started = False

    def start(self):
        if self.started:
            self.invalidate('capture_reopened')
        self.started = True

    def invalidate(self, reason):
        self.failure = self.failure or reason

    def _markers(self, line, offset, terminated):
        value = line.strip(b'\0\r\n \t')
        if is_missing_banner(value) or legacy_counts(value):
            if self.reset_offset != offset:
                self.reset_offset = offset
                self.reset_count += 1
        elif PROMPT.fullmatch(value):
            if self.prompt_offset != offset:
                self.prompt_offset = offset
                self.prompt_count += 1
        elif terminated and LINUX.match(value):
            self.previous_linux_offset = self.linux_offset
            self.linux_offset = offset
            self.linux_count += 1

    def feed(self, data):
        if not self.started:
            self.invalidate('capture_not_started')
        self.total += len(data)
        # Streaming framing: even a giant supplied chunk cannot grow pending.
        for piece in data.splitlines(keepends=True):
            self.pending.extend(piece[:MAX_LINE + 1 - len(self.pending)])
            if len(self.pending) > MAX_LINE or len(piece) > MAX_LINE:
                self.invalidate('oversized_frame')
            if piece.endswith(b'\n'):
                if not self.failure:
                    self._markers(bytes(self.pending), self.offset, True)
                self.offset += len(self.pending)
                self.pending.clear()
            elif not self.failure:
                self._markers(bytes(self.pending), self.offset, False)

    def proof(self, handoff):
        reasons = []
        if not self.started or self.failure:
            reasons.append(self.failure or 'capture_not_started')
        if type(handoff) is not int or handoff < 0 or handoff > self.total:
            reasons.append('invalid_handoff')
        else:
            if self.linux_offset < handoff:
                reasons.append('linux_not_observed_after_handoff')
            if self.previous_linux_offset >= handoff:
                reasons.append('multiple_linux_epochs_after_handoff')
            # A later banner cannot renew an older, invalidated bootm handoff.
            if max(self.reset_offset, self.prompt_offset) >= handoff:
                reasons.append('reset_or_prompt_after_handoff')
        if self.pending.strip(b'\0\r\n \t'):
            reasons.append('unterminated_frame')
        return dict(schema='openmitrastar.uart-continuous-epoch/v2',
                    eligible=not reasons, reasons=reasons, observed_bytes=self.total,
                    handoff_offset=handoff, linux_offset=self.linux_offset,
                    reset_offset=self.reset_offset, prompt_offset=self.prompt_offset,
                    linux_count=self.linux_count, reset_count=self.reset_count,
                    prompt_count=self.prompt_count, raw_content_saved=False)
