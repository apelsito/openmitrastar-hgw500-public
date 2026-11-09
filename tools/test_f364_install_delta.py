"""Three identity/recovery checks; do not rerun the inherited hardware suites."""
from pathlib import Path
import argparse,ast,json,unittest
import f364_install_contract as c
class Delta(unittest.TestCase):
 def test_real_candidate_and_accepted_F363_with_same_store(self):
  images=c.images();c.validate_proofs();self.assertEqual(images['f364']['full_slot_crc32'],'d7a19077');self.assertEqual(images['f363']['full_slot_crc32'],'b8f8acc1');self.assertEqual(c.store_binding()['crc32'],'5d2ee646');self.assertEqual(images['f364']['kernel_build'],'#358')
 def test_firmware_writer_and_recovery_functions_unchanged(self):
  def funcs(name):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse((c.ROOT/'tools'/name).read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef)}
  old=funcs('f363_install_executor.py');new=funcs('f364_install_executor.py')
  for name in ['crc_command','read_command','write_command','ram_crc','flash_read','flash_crc','selector','protected','domain','transfer','write_image','boot_written']:self.assertEqual(old[name],new[name],name)
 def test_thermal_and_ethernet_acceptance_are_reused(self):
  def methods(name):
   tree=ast.parse((c.ROOT/'tools'/name).read_text(encoding='utf-8'));host=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='Host');return {n.name:ast.dump(n,include_attributes=False) for n in host.body if isinstance(n,ast.FunctionDef)}
  old=methods('f363_install_executor.py');new=methods('f364_install_executor.py')
  for name in ['verify_thermal_disabled','verify_ethernet','verify_store','verify_configuration','watchdog_inactive']:self.assertEqual(old[name],new[name],name)
  source=(c.ROOT/'tools/f364_install_executor.py').read_text(encoding='utf-8');self.assertIn('import f363_thermal_status as thermal',source);self.assertIn('from f362_recovery_delta import',source);self.assertNotIn('experimental_enable',source)
  self.assertIn('from f364_ethernet_identity import',source)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);a=ap.parse_args();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Delta));a.result.write_text(json.dumps(dict(passed=r.wasSuccessful(),tests=r.testsRun,hardware_actions=False),indent=2)+'\n',encoding='ascii');raise SystemExit(0 if r.wasSuccessful() else 1)
