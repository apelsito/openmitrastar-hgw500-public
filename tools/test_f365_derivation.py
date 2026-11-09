"""Focused F365 import and metadata wiring checks; no plan or hardware access."""
from pathlib import Path
import argparse,ast,json,unittest
from unittest.mock import patch
import derive_f365_installer as d

RESULT=Path('/workspace/user-home/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/analysis/f365-fullimage-20260921T215511Z/result.json')

class Derivation(unittest.TestCase):
 def test_shared_ethernet_import_and_test_name_stay_f364(self):
  source='from f364_ethernet_identity import ethernet_command, verify_ethernet_response\nfrom f362_recovery_delta import serial_reboot_to_prompt, clear_pending_break\nimport f364_install_contract as c\ntest="test_f364_ethernet_identity.py"\n'
  result=d.shift(source);tree=ast.parse(result)
  self.assertEqual(tree.body[0].module,'f364_ethernet_identity');self.assertEqual(tree.body[1].module,'f362_recovery_delta');self.assertEqual(tree.body[2].names[0].name,'f365_install_contract');self.assertIn('test_f364_ethernet_identity.py',result)
  self.assertNotIn('f365_ethernet_identity',result)

 def test_real_candidate_metadata_and_exact_parent_are_bound(self):
  old=json.loads((d.ROOT/'work/kernel-port/versions/f364-installer/inputs.json').read_text(encoding='ascii'));q=json.loads(RESULT.read_text(encoding='ascii'));binding=d.candidate_binding(RESULT,old)
  self.assertEqual(binding['candidate']['sha256'],q['artifact']['sha256']);self.assertEqual(binding['fallback'],old['candidate']);self.assertEqual(binding['candidate']['kernel_build'],q['recovery']['kernel_build']);self.assertEqual(binding['qualification']['sha256'],d.sha(RESULT));self.assertFalse(binding['thermal_default']['sensor_mmio'])
  for key in ('automatic_sensor_activation','kernel_config_dt_qdrv_unchanged'):
   bad={**q,key:not q[key]}
   with patch.object(d.json,'loads',return_value=bad),self.assertRaisesRegex(ValueError,'candidate_diagnostic_scope'):d.candidate_binding(RESULT,old)

 def test_preparer_pins_diagnostic_source_and_its_actual_test_counts(self):
  source=(d.ROOT/'tools/prepare_f364_install.py').read_text(encoding='utf-8');result=d.prepare_template(source);ast.parse(result)
  for name in ('temp_sens.c','temp_diag.h'):self.assertIn('work/kernel-port/versions/f365-temperature-data-diagnostic/'+name,result)
  self.assertIn("'test_f365_derivation.py'",result);self.assertIn("'derivation',3)",result);self.assertIn("'delta',4)",result);self.assertIn("adaptation_tests=sum(item['count'] for item in tests.values())",result)
  self.assertNotIn('f365_ethernet_identity',result);self.assertNotIn('f364-temperature-diagnostic',result)
  self.assertIn(d.STABLE_DTB,result);self.assertIn('test_f364_ethernet_identity.py',result);self.assertIn("'ethernet-identity',6)",result)
  self.assertIn("Path(m.__file__).resolve() for m in sys.modules.values()",result)

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);a=ap.parse_args();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Derivation));a.result.write_text(json.dumps(dict(passed=r.wasSuccessful(),tests=r.testsRun,hardware_actions=False),indent=2)+'\n',encoding='ascii');raise SystemExit(0 if r.wasSuccessful() else 1)
