"""Four checks for cache format/partial evidence and immediate no-retry reads."""
from pathlib import Path
import argparse,json,unittest
import f365_sensor_commands as c
import f365_thermal_status as t
from f336_wdt_ram_executor import Failure
def diag(source='hwmon',operation='temp1_input',sequence=1):
 return dict(schema=t.SCHEMA,source=source,operation=operation,sequence=sequence,complete=1,errno=-110,read_count=42,first_word='0x00000021',last_word='0x00000022',elapsed_us=150000,elapsed_valid=1)
def output(legacy=None):
 fields=dict(temp_rc='1',temp_mc='',temp_stderr='cat: read error: Connection timed out',temp_diag_hwmon_rc='0',temp_diag_hwmon=json.dumps(diag()),temp_diag_legacy_rc='0',temp_diag_legacy=json.dumps(legacy or diag('legacy','legacy',9)))
 return ('\n'.join(k+'='+v for k,v in fields.items())+'\n').encode()
class Cache(unittest.TestCase):
 def test_failed_read_preserves_exact_errno_words_count_and_elapsed(self):
  r=c.diagnostic(output());d=r['access_diagnostics']['temp']['hwmon'];self.assertEqual((d['errno'],d['read_count'],d['first_word'],d['last_word'],d['elapsed_us']),(-110,42,'0x00000021','0x00000022',150000))
  with self.assertRaises(Failure):c.sampled(output())
 def test_malformed_legacy_does_not_discard_valid_hwmon_data(self):
  r=c.diagnostic(output({'schema':'invalid'}));self.assertEqual(r['access_diagnostics']['temp']['hwmon']['read_count'],42);self.assertTrue(r['access_diagnostics']['temp']['legacy']['unavailable'])
  raw=output().replace(b'temp_diag_legacy_rc=0',b'temp_diag_legacy_rc=1')+b'temp_diag_legacy_stderr=cat: read error: Input/output error\n'
  r=c.diagnostic(raw);legacy=r['access_diagnostics']['temp']['legacy'];self.assertEqual(legacy['read_exit_code'],1);self.assertEqual(legacy['read_stderr']['exact_stderr'],'cat: read error: Input/output error');self.assertEqual(r['access_diagnostics']['temp']['hwmon']['errno'],-110)
 def test_zero_reads_null_words_and_large_elapsed_are_not_fabricated(self):
  r=diag('legacy','legacy');r.update(errno=-19,read_count=0,first_word=None,last_word=None);self.assertIsNone(t.cached(json.dumps(r),'legacy')['first_word'])
  for key,value in [('first_word','0x00000000'),('read_count',True),('elapsed_us',-1)]:
   bad={**r,key:value}
   with self.assertRaises(Failure):t.cached(json.dumps(bad),'legacy')
 def test_cache_capture_precedes_error_exit_and_interval_read(self):
  text=c.sample('hwmon0','/run/openmitrastar/f365-sensor/'+'a'*32)
  self.assertEqual(text.count('cat /sys/class/hwmon/hwmon0/temp1_input'),1);self.assertEqual(text.count('cat /sys/class/hwmon/hwmon0/interval '),1)
  early=text.index('[ "$rc" = 0 ] || exit 0');self.assertLess(text.index('temp_diag_hwmon_rc='),early);self.assertLess(text.index('temp_diag_legacy_rc='),early);self.assertGreater(text.index('cat /sys/class/hwmon/hwmon0/interval '),early)
  for prefix in ('temp','interval'):
   for source in ('hwmon','legacy'):
    key=prefix+'_diag_'+source;self.assertIn('/'+key+'.stderr',text);self.assertIn(key+'_stderr=%s',text)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);a=ap.parse_args();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Cache));a.result.write_text(json.dumps(dict(passed=r.wasSuccessful(),tests=r.testsRun,hardware_actions=False),indent=2)+'\n',encoding='ascii');raise SystemExit(0 if r.wasSuccessful() else 1)
