"""Offline-only loaded-continuation binding and parser rejection checks."""
from pathlib import Path
import importlib.util,json,unittest
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('continuation',HERE/'executor.py')
e=importlib.util.module_from_spec(spec);spec.loader.exec_module(e)
class Tests(unittest.TestCase):
 def test_exact_local_and_prior_receipt(self):
  config=json.loads((e.ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/eth73-reset-artifact-v2/CONFIG.json').read_text())
  self.assertEqual(e.m.preflight(config)['bytes'],3052800)
  self.assertIn('eth73-reset-physical-v2',e.inherited(config))
 def test_wrong_image_prior_binding_rejected(self):
  config={'sha256':'0'*64}
  with self.assertRaises(e.m.m.Refusal):e.inherited(config)
 def test_continuation_has_no_transfer_or_reboot(self):
  import inspect
  body=inspect.getsource(e.Flow.run)
  self.assertNotIn("self.command('loady",body);self.assertNotIn('reboot_once(',body);self.assertNotIn('modem.send(',body)
  self.assertLess(body.index('self.verify_ram()'),body.index("b'bootm 83000000"))
 def test_environment_and_word_rejection(self):
  with self.assertRaises(e.m.m.Refusal):e.m.m.parse_environment(b'bootcmd=bootselect\nbootselect=1\n')
  with self.assertRaises(e.m.m.Refusal):e.m.m.parse_word(b'84000000: 00000000\n84000000: 12345678\n','84000000')
if __name__=='__main__':unittest.main()
