"""Offline source-bound evidence and payload checks. No network calls."""
from pathlib import Path
import argparse,copy,json,subprocess,tempfile,unittest
import f367_aelita_harness as h

def fixture():
 c=json.loads(h.CONFIG.read_text(encoding='ascii'));c['image']={'version':'lyoko-fixture-f367-test'}
 run='1'*32;tag='2'*64
 client=dict(run_id=run,associated=True,bssid_match=True,channel=52,client_tag=tag,wifi_ipv4='192.168.1.50',control_verified=True,control_interface_index=6,wifi_interface_index=17,strong_host=True,control_unchanged=True)
 for key in ('download','upload','internet'):client[key]=dict(exit_code=0,http_code=200,local_ip='192.168.1.50',remote_ip='192.168.1.49' if key!='internet' else '20.112.250.133',bytes=4194304 if key!='internet' else 0)
 client['restore']=dict(profile_restored=True,profile_unchanged=True,test_profile_removed=True,control_unchanged=True)
 router=dict(run_id=run,firmware=c['image']['version'],boot_id='fixture-boot',wifi_rx_bytes=1,wifi_tx_bytes=1,stations=[dict(tag=tag,auth=True,assoc=True,authorized=True)])
 after=copy.deepcopy(router);after.update(wifi_rx_bytes=4194305,wifi_tx_bytes=4194305)
 return c,client,router,after

class Harness(unittest.TestCase):
 def test_future_image_and_control_are_explicit(self):
  c=json.loads(h.CONFIG.read_text(encoding='ascii'));h.validate_config(c);self.assertFalse(h.future_binding(c))
  for key,value in [('control_interface_index',17),('control_ipv4','192.168.1.1'),('ssh_host_key_mode','compat')]:
   bad=copy.deepcopy(c);bad['client'][key]=value
   with self.assertRaises(ValueError):h.validate_config(bad)

 def test_strict_wifi_source_and_bidirectional_bytes(self):
  args=fixture();self.assertEqual(h.evaluate(*args)['status'],'PASS_F367_CLIENT_SOURCE_BOUND_TRAFFIC')
  for key in ('download','upload','internet'):
   bad=copy.deepcopy(args);bad[1][key]['local_ip']='192.168.1.63'
   with self.assertRaises(ValueError):h.evaluate(*bad)
  bad=copy.deepcopy(args);bad[1]['strong_host']=False
  with self.assertRaises(ValueError):h.evaluate(*bad)
  bad=copy.deepcopy(args);bad[1]['upload']['bytes']=0
  with self.assertRaises(ValueError):h.evaluate(*bad)

 def test_same_client_authorized_and_same_boot_required(self):
  args=fixture()
  for change in ('authorization','tag','boot','run'):
   bad=copy.deepcopy(args)
   if change=='authorization':bad[3]['stations'][0]['authorized']=False
   elif change=='tag':bad[3]['stations'][0]['tag']='3'*64
   elif change=='boot':bad[3]['boot_id']='other-boot'
   else:bad[3]['run_id']='3'*32
   with self.assertRaises(ValueError):h.evaluate(*bad)

 def test_restore_and_counter_failures_cannot_pass(self):
  args=fixture()
  for key in args[1]['restore']:
   bad=copy.deepcopy(args);bad[1]['restore'][key]=False
   with self.assertRaises(ValueError):h.evaluate(*bad)
  bad=copy.deepcopy(args);bad[3]['wifi_tx_bytes']=1
  with self.assertRaises(ValueError):h.evaluate(*bad)

 def test_router_output_contains_tags_and_flags_only(self):
  text='OMF367_ROUTER run_id='+('1'*32)+' firmware=lyoko-fixture-f367-test boot_id=fixture wifi_rx_bytes=1 wifi_tx_bytes=2 target_bssid_tag='+('3'*64)+'\nOMF367_STATION tag='+('2'*64)+' auth=1 assoc=1 authorized=1\n'
  result=h.parse_router_snapshot(text);self.assertTrue(result['stations'][0]['authorized']);self.assertNotIn('mac',result['stations'][0])
  with self.assertRaises(ValueError):h.parse_router_snapshot(text+'client_mac=private\n')

 def test_powershell_parse_and_no_network_configuration_mutations(self):
  payload=h.ROOT/'tools/f367_aelita_client.ps1';text=payload.read_text(encoding='utf-8')
  for forbidden in ('Set-NetIPInterface','New-NetIPAddress','Remove-NetIPAddress','Set-NetRoute','New-NetRoute','Remove-NetRoute','Set-DnsClientServerAddress','Set-NetFirewall','Disable-NetAdapter','Enable-NetAdapter','key=clear','--location','--insecure'):
   self.assertNotIn(forbidden,text)
  self.assertIn("'--interface',$Source",text);self.assertIn("'--noproxy','*'",text);self.assertIn("local=%{local_ip}",text)
  self.assertIn('state.dpapi',text);self.assertIn('Start-ScheduledTask -TaskName $task',text);self.assertLess(text.index('Start-ScheduledTask -TaskName $task'),text.index("}elseif($Action -ceq 'Connect')"))
  restore=text[text.index('function Restore-Profile {'):text.index('function Bound-Curl(')];self.assertNotIn('Assert-Control',restore)
  self.assertIn('F367_STAGED_HASH',text)
  functions=h.reused_functions();self.assertNotIn('$beforeSsid =',functions)
  with tempfile.TemporaryDirectory(prefix='f367-parse-') as folder:
   library=Path(folder)/'reused.ps1';library.write_text(functions,encoding='utf-8')
   for path in (payload,library):
    quoted=str(path).replace("'","''");script="$errors=$null;$tokens=$null;[System.Management.Automation.Language.Parser]::ParseFile('"+quoted+"',[ref]$tokens,[ref]$errors)|Out-Null;if($errors.Count){$errors|ForEach-Object{$_.ToString()};exit 1}"
    completed=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,text=True,timeout=30);self.assertEqual(completed.returncode,0,completed.stdout+completed.stderr)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--result',type=Path,required=True);a=p.parse_args();r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Harness));a.result.write_text(json.dumps(dict(passed=r.wasSuccessful(),tests=r.testsRun,hardware_actions=False),indent=2)+'\n',encoding='ascii');raise SystemExit(0 if r.wasSuccessful() else 1)
