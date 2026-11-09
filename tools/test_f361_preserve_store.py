"""Focused regression: firmware install/rollback must preserve a committed store."""
from pathlib import Path
from unittest.mock import patch
import argparse,json,tempfile,unittest
import f361_install_executor as x
import f361_install_contract as c
import f361_install_test_fixture as f
class Preserve(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.store=c.store_binding();cls.bytes=Path(cls.store['path']).read_bytes();cls.plan=dict(images=c.images(),protected=c.protected_backups(),store=cls.store,bootargs=c.BOOTARGS,erased_prefix_crc32=c.crc(b'\xff'*c.PREFIX))
 def case(self,scenario):
  model=f.Model(self.plan,scenario);f.FakeHost.model=model
  class Uart(f.FakeUart):
   def command(self,command,timeout=15,handoff=False):
    reply=super().command(command,timeout,handoff)
    if scenario=='erase_overrun' and command==x.ERASE_COMMAND:self.s.flash[c.PREFIX:c.PREFIX+65536]=b'\xff'*65536
    return reply
  with tempfile.TemporaryDirectory(prefix='f361-journal-') as directory:
   with patch.object(x.base.time,'sleep',lambda _:None):code=x.run(self.plan,Path(directory),f.FakeHost,Uart,f.FakeServer)
   r=json.loads((Path(directory)/'result.json').read_text(encoding='ascii'))
  return model,code,r
 def test_operational_fullslot_uses_store_not_manifest_ff_padding(self):
  baseline=self.plan['images']['f358'];self.assertEqual(baseline['full_slot_crc32'],'3e8db0dc');self.assertEqual(baseline['manifest_ff_full_slot_crc32'],'4d006632');self.assertEqual(baseline['prefix_crc32'],'df453410')
  self.assertFalse(all(x==255 for x in self.bytes[:65536]));self.assertEqual(baseline['preserved_store_sha256'],self.store['sha256'])
 def test_install_preserves_non_ff_store_and_checks_it_after_erase(self):
  model,code,r=self.case('success');self.assertEqual(code,0);self.assertEqual(model.boots,['f361']);self.assertEqual(bytes(model.flash[c.PREFIX:]),self.bytes)
  erase=model.commands.index(x.ERASE_COMMAND);program=next(i for i,v in enumerate(model.commands) if v.startswith('spi_flash write'))
  self.assertIn(x.read_command(c.STORE,c.STORE_BYTES),model.commands[erase+1:program]);self.assertEqual((model.erases,model.writes),(1,1))
 def test_rollback_restores_only_f358_prefix_with_same_journal(self):
  model,code,r=self.case('platform_fails');self.assertEqual(code,1);self.assertEqual(model.boots,['f361','f358']);self.assertEqual(bytes(model.flash[c.PREFIX:]),self.bytes);self.assertEqual((model.erases,model.writes),(2,2));self.assertEqual(c.crc(bytes(model.flash)),'3e8db0dc')
 def test_simulated_extra_sector_is_detected_before_any_program(self):
  model,code,r=self.case('erase_overrun');self.assertEqual(code,1);self.assertEqual(model.erases,1);self.assertEqual(model.writes,0);self.assertFalse(r['rollback_attempted'])
 def test_actual_boot_state_requires_journal_seq1_active_hash_and_backend(self):
  host=x.Host({'boot_acceptance':{'payload_sha256':'a'*64}},Path('.'));data=('ready=F361_READY\nslot=A\nsequence=1\nsha256='+'a'*64+'\nsource=journal\nactive_sha256='+'a'*64+'\nallow_hw=Y\nallow_program=Y\n').encode()
  host.ssh=lambda command:data;self.assertEqual(host.verify_configuration()['sequence'],1)
  for invalid in [data.replace(b'sequence=1',b'sequence=2'),data.replace(b'source=journal',b'source=fallback'),data.replace(b'allow_program=Y',b'allow_program=N')]:
   host.ssh=lambda command:invalid
   with self.assertRaises(x.Failure):host.verify_configuration()
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);a=ap.parse_args();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Preserve));a.result.write_text(json.dumps(dict(passed=r.wasSuccessful(),tests=r.testsRun,hardware_actions=False,scope='mutable store preservation only'),indent=2)+'\n',encoding='ascii');raise SystemExit(0 if r.wasSuccessful() else 1)
