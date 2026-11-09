"""Bounded boot-epoch metadata only. No I/O, recovery action or guard bypass."""
import re
from f366r3_reset_observation import is_missing_banner,legacy_counts

LINUX=re.compile(rb'^(?:\[\s*[0-9]+\.[0-9]+\]\s*)?Linux version 5\.10\.260-openmitrastar-radiohw(?:\s|$)')
PROMPT=re.compile(rb'^(?:topaz>|ZHAL>)[ \t]*$')

class EpochMetadata:
    def __init__(self):
        self.total=0;self.offset=0;self.pending=bytearray();self.discarding=False
        self.linux_offset=-1;self.reset_offset=-1;self.prompt_offset=-1;self.unknown_offset=-1
        self.reset_count=0;self.oversized_lines=0
    def observe_line(self,line,offset):
        value=line.strip(b'\0\r\n \t')
        if is_missing_banner(value) or legacy_counts(value):
            self.reset_offset=offset;self.reset_count+=1
        elif LINUX.match(value):self.linux_offset=offset
        elif PROMPT.fullmatch(value):self.prompt_offset=offset
    def feed(self,data):
        self.total+=len(data);self.pending.extend(data)
        while b'\n' in self.pending:
            end=self.pending.index(b'\n')+1;line=bytes(self.pending[:end]);del self.pending[:end]
            if not self.discarding:self.observe_line(line,self.offset)
            self.offset+=end;self.discarding=False
        if len(self.pending)>8192:
            self.unknown_offset=self.offset;self.oversized_lines+=1
            self.offset+=len(self.pending);self.pending.clear();self.discarding=True
        if not self.discarding and PROMPT.fullmatch(bytes(self.pending).strip(b'\0\r\t ')):
            self.prompt_offset=self.offset
    def proof(self,handoff,*,reader_failed=False,has_prompt=False,autoboot=False):
        reasons=[]
        if type(handoff) is not int or handoff<0 or handoff>self.total:reasons.append('invalid_handoff')
        elif self.linux_offset<handoff:reasons.append('linux_not_observed_after_handoff')
        if self.linux_offset<=max(self.reset_offset,self.prompt_offset,self.unknown_offset):reasons.append('newer_reset_prompt_or_unknown_frame')
        if reader_failed:reasons.append('reader_failed')
        if has_prompt:reasons.append('prompt_present')
        if autoboot:reasons.append('autoboot_not_quiesced')
        return dict(schema='openmitrastar.uart-linux-epoch-metadata/v1',eligible=not reasons,reasons=reasons,
                    handoff_offset=handoff,observed_bytes=self.total,linux_offset=self.linux_offset,
                    reset_offset=self.reset_offset,prompt_offset=self.prompt_offset,unknown_offset=self.unknown_offset,
                    reset_count=self.reset_count,raw_content_saved=False,serial_actions=False)
