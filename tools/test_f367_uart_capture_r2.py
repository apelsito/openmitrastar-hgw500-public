"""Only passive capture deltas; synthetic bytes and fake serial I/O."""
from pathlib import Path
import json,tempfile,unittest
import f367_uart_capture_r2 as capture


class CaptureTests(unittest.TestCase):
 def test_refusal_code_survives_sensitive_word_without_payload(self):
  row=capture.redacted_event(b'OMRADIO5_REFUSED reason=calibration-not-ready psk=example-secret mac=01:23:45:67:89:ab\n')
  self.assertEqual(row['text'],'OMRADIO5_REFUSED reason=calibration-not-ready')
  self.assertNotIn('example-secret',json.dumps(row));self.assertNotIn('01:23:45:67:89:ab',json.dumps(row))
 def test_guard_and_error_tokens_are_preserved_and_redacted(self):
  token=b'a'*32
  samples=[b'OMF367_NATIVE_GUARD reason=deny core_started=0 token='+token+b' mac=01:23:45:67:89:ab\n',
           b'OMF367_STATE {"nonce":"'+token+b'","ready":0}\n']
  for raw in samples:
   row=capture.redacted_event(raw);self.assertEqual(row['kind'],'diagnostic')
   self.assertNotIn(token.decode(),json.dumps(row));self.assertNotIn('01:23:45:67:89:ab',json.dumps(row))
 def test_split_lines_and_oversize_suffix_do_not_invent_markers(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'ledger.jsonl';observer=capture.SemanticCapture(path);observer.start()
   payload=b'OMRADIO5_REFUSED reason=watchdog-not-protecting\nOMF367_ERROR reason=native-bootstrap\n'
   for index in range(0,len(payload),7):observer.feed(payload[index:index+7])
   observer.feed(b'x'*(capture.MAX_LINE+1));observer.feed(b'OMF367_FAKE guard=1\n')
   observer.feed(b'OMF367_REAL guard=1\n');summary=observer.close()
   rows=[json.loads(line) for line in path.read_text().splitlines()]
   self.assertTrue(summary['complete']);self.assertEqual(summary['dropped_bytes'],0)
   self.assertEqual(rows[0]['text'],'OMRADIO5_REFUSED reason=watchdog-not-protecting')
   self.assertTrue(any(row['text']=='OMF367_REAL guard=1' for row in rows))
   self.assertFalse(any('OMF367_FAKE' in row['text'] for row in rows))
 def test_serial_proxy_forwards_identical_io_and_keeps_reset_observer(self):
  class Serial:
   is_open=False
   def __init__(self):self.reads=[];self.writes=[]
   def read(self,size):self.reads.append(size);return capture.reset.QUANTENNA_BANNER+b'\nOMF367_ERROR reason=test\n'
   def write(self,data):self.writes.append(data);return len(data)
  with tempfile.TemporaryDirectory() as folder:
   semantic=capture.SemanticCapture(Path(folder)/'ledger.jsonl');semantic.start()
   resets=[];raw=Serial();banner=capture.reset.BannerObserver(lambda now,event:resets.append(event))
   inner=capture.reset.ObservedSerial(raw,banner);outer=capture.reset.ObservedSerial(inner,semantic)
   data=outer.read(4096);self.assertIn(b'OMF367_ERROR',data)
   self.assertEqual(outer.write(b'existing-command'),16);summary=semantic.close()
   self.assertEqual(raw.reads,[4096]);self.assertEqual(raw.writes,[b'existing-command'])
   self.assertEqual(len(resets),1);self.assertTrue(summary['complete'])


if __name__=='__main__':unittest.main()
