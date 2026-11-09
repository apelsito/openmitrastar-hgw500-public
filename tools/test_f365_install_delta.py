"""Only F365 identity and cached-state acceptance; inherited writers unchanged."""
from pathlib import Path
import argparse,ast,json,unittest,tempfile
from unittest.mock import patch
from f365_failure_snapshot import save_failure_snapshot
import f365_install_contract as c
import f365_thermal_status as thermal
from f336_wdt_ram_executor import Failure
def diag(source,complete=0):
 return dict(schema=thermal.SCHEMA,source=source,operation='legacy' if complete else 'none',sequence=5 if complete else 0,complete=complete,errno=-19 if complete else 0,read_count=0,first_word=None,last_word=None,elapsed_us=7 if complete else 0,elapsed_valid=complete)
class Delta(unittest.TestCase):
 def test_failure_snapshot_is_local_and_never_blocks_recovery(self):
  result=dict(error='ethernet_dt_probe_mapping',platform=dict(status='PASS',checks=27),watchdog=dict(control='00000000'))
  with tempfile.TemporaryDirectory(prefix='f365-snapshot-') as directory:
   out=Path(directory);self.assertTrue(save_failure_snapshot(out,result));saved=json.loads((out/'failure-before-recovery.json').read_text(encoding='ascii'));self.assertEqual(saved['error'],result['error']);self.assertEqual(saved['platform']['checks'],27)
   with patch('f365_failure_snapshot.os.replace',side_effect=OSError('fixture')):self.assertFalse(save_failure_snapshot(out,result))
   self.assertEqual(result['failure_snapshot_error'],'OSError')
  source=(c.ROOT/'tools/f365_install_executor.py').read_text(encoding='utf-8');self.assertLess(source.index("result['failure_snapshot_written']=save_failure_snapshot"),source.index('can_recover=reboot_started'))
 def test_real_candidate_and_physical_F364_fallback(self):
  images=c.images();c.validate_proofs();self.assertEqual(images['f364']['full_slot_crc32'],'d7a19077');self.assertEqual(c.store_binding()['crc32'],'5d2ee646');self.assertEqual(images['f365']['kernel_build'],'#358')
 def test_transport_write_functions_unchanged(self):
  def functions(name):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse((c.ROOT/'tools'/name).read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef)}
  old=functions('f364_install_executor.py');new=functions('f365_install_executor.py')
  for name in ['crc_command','read_command','write_command','ram_crc','flash_read','flash_crc','selector','protected','domain','transfer','write_image','boot_written']:self.assertEqual(old[name],new[name],name)
 def test_cached_revision_accepts_legacy_ENODEV_without_reading_sensor(self):
  header='temp_module=1\nhwmon_module=1\nmodule_version=363\nenabled=0\nactivation_attempted=0\nactivation_error=-19\nsensor_count=1\n'
  data=(header+'diag_hwmon='+json.dumps(diag('hwmon'))+'\ndiag_legacy='+json.dumps(diag('legacy',1))+'\n').encode();r=thermal.validate(data);self.assertEqual(r['diagnostic_revision'],365);self.assertEqual(r['diag_legacy']['read_count'],0)
  invalid=diag('legacy',1);invalid.update(read_count=1,first_word='0x00000000',last_word='0x00000000')
  with self.assertRaises(Failure):thermal.validate((header+'diag_hwmon='+json.dumps(diag('hwmon'))+'\ndiag_legacy='+json.dumps(invalid)+'\n').encode())
  for attr in ['temp1_input','interval','experimental_enable']:self.assertNotIn('/'+attr,thermal.command())
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);a=ap.parse_args();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Delta));a.result.write_text(json.dumps(dict(passed=r.wasSuccessful(),tests=r.testsRun,hardware_actions=False),indent=2)+'\n',encoding='ascii');raise SystemExit(0 if r.wasSuccessful() else 1)
