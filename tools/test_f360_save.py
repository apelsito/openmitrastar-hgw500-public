"""Minimal first-SAVE adaptation tests; no hardware and no historical reruns."""
from pathlib import Path
from unittest.mock import patch
import argparse,hashlib,json,tempfile,unittest
import f360_save_executor as x
import f360_protocol as p
import test_f356_observe as old
PAYLOAD={'bytes':586,'sha256':'a'*64}
EXPECTED={'original':{'store_sha256':'b'*64},'expected_after_save':{'firmware_prefix_crc32':'df453410','full_slot_crc32':'3e8db0dc'},'artifacts':{'expected-dc-dd.bin':{'sha256':'c'*64},'expected-store.bin':{'sha256':'d'*64,'crc32':'31bf4416'}}}
class SaveAdaptation(unittest.TestCase):
 def test_cli_metadata_and_load_hash_are_exact(self):
  self.assertEqual(p.saved(b'{"status":"saved","sequence":1,"slot":0,"bytes":586}',PAYLOAD)['slot'],0)
  for data in [b'{"status":"saved","sequence":2,"slot":0,"bytes":586}',b'{"status":"saved","sequence":1,"slot":1,"bytes":586}']:
   with self.assertRaises(p.ProtocolError):p.saved(data,PAYLOAD)
  p.loaded_payload(('readback_rc=0\nstderr_present=0\nbytes=586\nsha256='+'a'*64+'\n').encode(),PAYLOAD)
 def case(self,fail=False):
  model=old.Model('save-failed' if fail else 'success');old.FakeHost.model=model;model.saves=0;model.readbacks=0;prior_owner=old.owner
  class Host(old.FakeHost):
   def identity(self,name):return dict(boot_id=old.BOOT,uts='#358 @1790006400')
   def inspect_current(self):return dict(kernel_profile_verified=1)
   def current_payload(self):return dict(current=True)
   def store_snapshot(self,tag):return dict(all_pair_ff=True,store_sha256='b'*64)
   def save_config(self):
    model.saves+=1
    if fail:raise x.Failure('ssh_failed')
    return b'{"status":"saved","sequence":1,"slot":0,"bytes":586}'
   def load_config(self):model.readbacks+=1;return ('readback_rc=0\nstderr_present=0\nbytes=586\nsha256='+'a'*64+'\n').encode()
  def owner(token=old.TOKEN,op=1):
   row=prior_owner(token,op);row['boot_id']=old.BOOT
   if row['phase']:row['phase']=p.PHASE
   return row
  def reset(uart,count,seconds):
   if len(model.reset_times)==count:model.reset()
   return True
  def restored(*args,**kwargs):model.returns+=1;return dict(readback_error=None,persisted_expected_record=not fail,physical_ff_restore_performed=False)
  with tempfile.TemporaryDirectory() as directory,patch.object(old,'owner',owner),patch.object(old,'LOAD',old.LOAD.replace(old.RAMBOOT.encode(),old.BOOT.encode()).replace(b'allow_program=N',b'allow_program=Y')),patch.object(x,'wait_reset',reset),patch.object(x,'return_after_save',restored),patch.object(x.ram,'inactive_hardware',lambda uart:dict(controls=[0,0],counters=[65535,65535])):
   code=x.run({'images':{'f358':{}},'payload':PAYLOAD,'expected':EXPECTED},Path(directory),Host,old.FakeUart);r=json.loads((Path(directory)/'result.json').read_text(encoding='ascii'))
  return model,code,r
 def test_one_save_one_load_and_controlled_return(self):
  m,code,r=self.case();self.assertEqual(code,0);self.assertEqual((m.saves,m.readbacks,m.unloads,m.returns),(1,1,1,1));self.assertEqual(r['status'],'PASS_F360_CONFIG_SAVED_AND_PERSISTED')
 def test_failed_save_never_loads_unloads_erases_or_retries(self):
  m,code,r=self.case(True);self.assertEqual(code,1);self.assertEqual((m.saves,m.readbacks,m.unloads,m.returns),(1,0,0,1));self.assertEqual(r['status'],'FAIL_SAVE_WITH_F358_RETURN_NO_REERASE');self.assertFalse(r['return']['physical_ff_restore_performed'])
 def test_return_uses_new_store_crc_and_archives_partial_without_reerase(self):
  calls=[]
  class Host:
   def platform(self,*args):return dict(checks=27)
   def watchdog_inactive(self):return dict(control='00000000')
   def owner_files_gone(self):return True
   def store_snapshot(self,tag):return dict(pair_sha256='c'*64,store_sha256='d'*64,all_pair_ff=False,expected_pair_byte_equal=True)
  def crc(uart,offset,length,expected=None):
   calls.append((offset,length,expected));return '31bf4416' if offset==x.contract.STORE else ('df453410' if length==x.contract.PREFIX else '3e8db0dc')
  with patch.object(x.ram,'inactive_hardware',lambda u:{}),patch.object(x.boot,'protected',lambda *a:{}),patch.object(x.boot,'flash_crc',crc),patch.object(x.boot,'boot_written',lambda *a,**kw:dict(boot_id='new')):
   result=x.return_after_save(object(),Host(),{'expected':EXPECTED},old.BOOT,Path('.'),True);self.assertTrue(result['persisted_expected_record']);self.assertIsNone(result['readback_error'])
   host=Host();host.store_snapshot=lambda tag:dict(pair_sha256='e'*64,store_sha256='f'*64,all_pair_ff=False,expected_pair_byte_equal=False)
   result=x.return_after_save(object(),host,{'expected':EXPECTED},old.BOOT,Path('.'),False);self.assertEqual(result['journal_state'],'partial-or-unverified-journal');self.assertFalse(result['physical_ff_restore_performed'])
  self.assertTrue(all(value!='4d006632' for _,_,value in calls))
 def test_loader_enables_program_only_and_save_uses_stdin(self):
  host=x.Host.__new__(x.Host);host.plan={'provider':{'sha256':'a'*64},'payload':PAYLOAD,'cli':{'sha256':'b'*64}};host.stage_dir='/run/fixture';host.module_path='/fixture/provider.ko';host.cli='/run/fixture/cli';host.payload_path='/run/fixture/payload';calls=[]
  host.capture=lambda kind,cmd,timeout=20:calls.append((kind,cmd)) or b'';host.load_provider();self.assertIn("'allow_hw=1 allow_program=1'",calls[0][1]);self.assertNotIn('/bin/insmod',calls[0][1])
  host.save_config();self.assertTrue(calls[-1][1].endswith('save </run/fixture/payload'));self.assertEqual(calls[-1][1].count(' save '),1)
 def test_no_bootbase_erase_and_no_secret_diagnostic(self):
  plan={'images':{'f358':{'bytes':5361664}},'protected':{'parts':[]},'bootargs':x.contract.BOOTARGS}
  self.assertFalse(any('erase' in cmd or 'write' in cmd for cmd in x.vocabulary(plan)))
  d=p.diagnostic('save',b'password=TOPSECRET',b'journal response rejected\nTOPSECRET',1,False);self.assertNotIn('TOPSECRET',json.dumps(d))
 def test_actual_mtd_capture_is_bounded_private_and_byte_compared(self):
  with tempfile.TemporaryDirectory() as directory:
   folder=Path(directory);expected=folder/'expected.bin';dc=(b'SECRET'+b'\0'*65536)[:65536];dd=b'\xff'*65536;expected.write_bytes(dc+dd)
   host=x.Host.__new__(x.Host);host.out=folder;host.plan={'expected':{'artifacts':{'expected-dc-dd.bin':{'path':str(expected)}}}};calls=[];acls=[]
   def ssh(command,timeout=20):
    calls.append(command)
    if command=='cat /proc/mtd':return b'dev: size erasesize name\nmtd4: 001c0000 00010000 "lyoko_store"\n'
    if command.endswith('/flags'):return b'0x800\n'
    if command.startswith('[ -c '):return b'MTDCHAR'
    if command.startswith('dd '):return dc if 'skip=0' in command else dd
    return b'a'*64+b'  /dev/mtd4\n'
   host.ssh=ssh
   with patch.object(x,'restrict_acl',lambda path,directory:acls.append((path,directory))):r=host.store_snapshot('after')
   self.assertTrue(r['expected_pair_byte_equal']);self.assertEqual(r['pair_bytes'],131072);self.assertEqual(r['pair_sha256'],hashlib.sha256(dc+dd).hexdigest());self.assertTrue(acls[0][1]);self.assertTrue(all('private' in v['path'] for v in r['parts']));self.assertNotIn('SECRET',json.dumps(r));self.assertEqual(sum(command.startswith('dd ') for command in calls),2)
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);a=ap.parse_args();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(SaveAdaptation));x.save(a.result,dict(passed=r.wasSuccessful(),tests=r.testsRun,hardware_actions=False,historical_batteries_rerun=False));raise SystemExit(0 if r.wasSuccessful() else 1)
