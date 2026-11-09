"""Only changed F358/F340 profiles and critical adaptation paths; no full rerun."""
from pathlib import Path
from unittest.mock import patch
import argparse,ast,json,tempfile,unittest
import f358_install_executor as x
import f358_install_contract as c
import f358_install_test_fixture as f

class Adaptation(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.plan=dict(images=c.images(),protected=c.protected_backups(),bootargs=c.BOOTARGS,erased_prefix_crc32=c.crc(b'\xff'*c.PREFIX),erased_store_crc32=c.crc(b'\xff'*c.STORE_BYTES))
 def case(self,scenario):
  model=f.Model(self.plan,scenario);f.FakeHost.model=model
  with tempfile.TemporaryDirectory(prefix='f358-profile-') as directory:
   with patch.object(x.base.time,'sleep',lambda _:None):code=x.run(self.plan,Path(directory),f.FakeHost,f.FakeUart,f.FakeServer)
   result=json.loads((Path(directory)/'result.json').read_text(encoding='ascii'))
  self.assertLessEqual(model.writes,2);self.assertLessEqual(model.erases,2)
  expected=b'\xff'*c.STORE_BYTES if scenario!='store_not_erased' else b'\xff'*7+b'\0'+b'\xff'*(c.STORE_BYTES-8)
  self.assertEqual(model.flash[c.PREFIX:],expected);return model,code,result
 def test_install_new_f358_and_keep_it_without_arming(self):
  model,code,r=self.case('success');self.assertEqual(code,0);self.assertEqual(model.boots,['f358']);self.assertEqual((model.erases,model.writes),(1,1));self.assertEqual(r['status'],'PASS_F358_PERSISTENT_BASELINE');self.assertFalse(r['watchdog_arm_requested'])
 def test_failed_candidate_platform_restores_exact_f340_once(self):
  model,code,r=self.case('platform_fails');self.assertEqual(code,1);self.assertEqual(model.boots,['f358','f340']);self.assertEqual((model.erases,model.writes),(2,2));self.assertEqual(r['status'],'FAILED_F358_WITH_EXACT_F340_RETURN');self.assertEqual(bytes(model.flash),model.images['f340']+b'\xff'*(c.SLOT-len(model.images['f340'])))
 def test_early_store_mismatch_returns_f340_readonly(self):
  model,code,r=self.case('store_not_erased');self.assertEqual(code,1);self.assertEqual((model.erases,model.writes),(0,0));self.assertEqual(model.boots,['f340'])
 def test_unknown_write_completion_never_attempts_restore(self):
  model,code,r=self.case('write_timeout');self.assertEqual(code,1);self.assertEqual((model.erases,model.writes),(1,1));self.assertEqual(model.boots,[]);self.assertTrue(r['flash_command_in_flight']);self.assertTrue(r['retain_lease_required'])
 def test_network_change_after_erase_cannot_interrupt_ram_program(self):
  model,code,r=self.case('network_drifts_after_erase');self.assertEqual((model.erases,model.writes),(1,1));self.assertLess(model.events.index('write'),model.events.index('network-rejected'));self.assertTrue(bytes(model.flash).startswith(model.images['f358']))
 def test_new_and_fallback_kernel_identity_exact_without_tr(self):
  host=x.Host(self.plan,Path('.'));calls=[]
  for name,number in [('f358',358),('f340',340)]:
   raw=('boot_id=01234567-89ab-cdef-0123-456789abcdef\nuts=#'+str(number)+' @1790006400\nf340=F340_WATCHDOG_BASELINE\0\nf336=\n').encode()
   host.ssh=lambda cmd:calls.append(cmd) or raw;self.assertEqual(host.identity(name)['uts'].split()[0],'#'+str(number));self.assertIn(self.plan['images'][name]['version'],calls[-1]);self.assertNotIn('tr ',calls[-1])
  host.ssh=lambda cmd:b'boot_id=01234567-89ab-cdef-0123-456789abcdef\nuts=#350 @1790006400\nf340=F340_WATCHDOG_BASELINE\0\nf336=\n'
  with self.assertRaises(x.Failure):host.identity('f358')
 def test_flash_engine_and_order_are_unchanged_from_proven_f346(self):
  old=ast.parse((c.ROOT/'tools/f346_install_executor.py').read_text(encoding='utf-8'));new=ast.parse(Path(x.__file__).read_text(encoding='utf-8'))
  for name in ['ram_crc','flash_read','flash_crc','selector','protected','domain','transfer','write_image','boot_written']:
   a=next(n for n in old.body if isinstance(n,ast.FunctionDef) and n.name==name);b=next(n for n in new.body if isinstance(n,ast.FunctionDef) and n.name==name);self.assertEqual(ast.dump(a,include_attributes=False),ast.dump(b,include_attributes=False),name)
  for name in ['mutate','enable_writer','disable_writer']:
   a=next(n for n in next(v for v in old.body if isinstance(v,ast.ClassDef) and v.name=='Uart').body if isinstance(n,ast.FunctionDef) and n.name==name)
   b=next(n for n in next(v for v in new.body if isinstance(v,ast.ClassDef) and v.name=='Uart').body if isinstance(n,ast.FunctionDef) and n.name==name);self.assertEqual(ast.dump(a,include_attributes=False),ast.dump(b,include_attributes=False),name)
 def test_launcher_forces_desktop_powershell_with_normalized_modules(self):
  import run_f358_install as launcher
  with patch.object(launcher,'subprocess') as process,patch('sys.argv',['run_f358_install.py','--plan','fixture','--plan-sha256','a'*64]):
   process.run.return_value.returncode=0;self.assertEqual(launcher.main(),0);args,kwargs=process.run.call_args
   self.assertIn('WindowsPowerShell',args[0][0]);self.assertNotIn('-Execute',args[0]);self.assertIn('WindowsPowerShell',kwargs['env']['PSModulePath'])

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);a=ap.parse_args();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Adaptation));a.result.write_text(json.dumps(dict(tests=r.testsRun,passed=r.wasSuccessful(),hardware_actions=False,scope='changed profiles and critical adaptation paths only'),indent=2)+'\n',encoding='ascii');raise SystemExit(0 if r.wasSuccessful() else 1)
