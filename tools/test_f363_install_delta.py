"""Three targeted checks; inherited F362 writer/recovery suite is not repeated."""
from pathlib import Path
import argparse,ast,json,unittest
import f363_install_contract as c
import f363_thermal_status as thermal
from f336_wdt_ram_executor import Failure
class Delta(unittest.TestCase):
 def test_real_target_and_physical_fallback_preserve_sequence2(self):
  images=c.images();proofs=c.validate_proofs();self.assertGreater(len(proofs),2)
  self.assertEqual(images['f362']['full_slot_crc32'],'1a6e28c0');self.assertEqual(c.store_binding()['crc32'],'5d2ee646')
  self.assertIn(images['f363']['version'],('lyoko-foundation-6.9.11-f363-temperature-diagnostic-device','lyoko-foundation-6.9.11-f363r2-temperature-owner-device'));self.assertEqual(images['f363']['kernel_build'],'#358');self.assertEqual(images['f363']['marker'],images['f362']['marker'])
 def test_default_cached_thermal_contract_and_no_sampling(self):
  data=b'temp_module=1\nhwmon_module=1\nmodule_version=363\nenabled=0\nactivation_attempted=0\nactivation_error=-19\nsensor_count=1\n'
  self.assertFalse(thermal.validate(data)['sensor_mmio_requested'])
  for bad in [data.replace(b'enabled=0',b'enabled=1'),data.replace(b'activation_attempted=0',b'activation_attempted=1'),data.replace(b'activation_error=-19',b'activation_error=0'),data.replace(b'sensor_count=1',b'sensor_count=2')]:
   with self.assertRaises(Failure):thermal.validate(bad)
  command=thermal.command()
  for name in ['experimental_enable','temp1_input','interval','topaz_read_internal_temp_sens']:
   self.assertNotIn(name,command)
 def test_transport_writer_and_recovery_implementation_unchanged(self):
  def functions(path):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef)}
  old=functions(c.ROOT/'tools/f362_install_executor.py');new=functions(c.ROOT/'tools/f363_install_executor.py')
  for name in ['crc_command','read_command','write_command','ram_crc','flash_read','flash_crc','selector','protected','domain','transfer','write_image','boot_written']:
   self.assertEqual(old[name],new[name],name)
  source=(c.ROOT/'tools/f363_install_executor.py').read_text(encoding='utf-8');self.assertIn('from f362_recovery_delta import',source)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);a=ap.parse_args();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Delta));a.result.write_text(json.dumps(dict(passed=r.wasSuccessful(),tests=r.testsRun,hardware_actions=False),indent=2)+'\n',encoding='ascii');raise SystemExit(0 if r.wasSuccessful() else 1)
