"""No router operations: native helper + fake CLI + existing CGI auth path."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,tempfile,time,unittest

MOCK=r'''#!/usr/bin/env python3
import json,os,re,sys,time
args=sys.argv[1:];mode=os.environ.get('F335_MOCK_MODE','normal')
cmd=args[4:];data=sys.stdin.read() if not cmd else ''
pin='';operation=cmd[0] if cmd else 'interactive';valid=True
if data:
 m=re.fullmatch(r'wps_pin(?:_bss wifi0)? any ([0-9]{4}|[0-9]{8}) 120\nquit\n',data)
 a=re.fullmatch(r'wps_ap_pin(?:_bss wifi0)? set ([0-9]{8}) 120\nquit\n',data)
 if m:operation='pin';pin=m[1]
 elif a:operation='ap-pin';pin=a[1]
 elif data in ('wps_ap_pin disable\nquit\n','wps_ap_pin_bss wifi0 disable\nquit\n'):operation='ap-pin-disable'
 else:valid=False
with open(os.environ['F335_MOCK_LOG'],'a') as f:f.write(json.dumps({'args':args,'operation':operation,'stdin_valid':valid,'pin_length':len(pin)})+'\n')
if not valid:print('FAIL');sys.exit(1)
if cmd and cmd[0] in ('raw','wps_status'):
 if cmd[0]=='raw' and cmd!=['raw','WPS_GET_STATUS']:print('FAIL');sys.exit(1)
 if mode=='hang_status':time.sleep(5)
 if mode=='stderr':print('mock error',file=sys.stderr);sys.exit(1)
 if mode=='unknown_cli':print("Unknown command 'raw'");sys.exit(1)
 if mode=='legacy_unknown_zero':print("Unknown command 'wps_get_status'");sys.exit(0)
 if mode=='unknown_substring':print("prefix Unknown command 'wps_get_status' suffix");sys.exit(0)
 if mode=='legacy_baseline':print('UNKNOWN COMMAND');sys.exit(0)
 if mode=='unsupported':print('UNKNOWN COMMAND');sys.exit(0)
 if mode=='disabled':print('FAIL');sys.exit(0)
 if mode=='bad_status':print('unexpected');sys.exit(0)
 if cmd[0]=='wps_status':print(os.environ.get('F335_MOCK_STATUS5','0(WPS_INITIAL)'))
 else:print(os.environ.get('F335_MOCK_STATUS2','PBC Status: Disabled\nLast WPS result: None\nPeer Address: 02:00:00:00:00:01'))
 sys.exit(0)
if mode in ('hang_command','slow_command'):time.sleep(5 if mode=='hang_command' else .5)
if mode=='fail_command' or (mode=='fail_ap_pin' and operation=='ap-pin'):print('FAIL');sys.exit(0)
if mode=='exit_error':print('OK');sys.exit(7)
if mode=='overflow':print('X'*10000);sys.exit(0)
if operation=='ap-pin':print('Interactive mode\n> '+data.splitlines()[0]+'\n'+pin+'\n> ')
elif operation=='pin':print('Interactive mode\n> '+data.splitlines()[0]+'\nOK\n> ')
else:print('OK')
'''

class WpsTests(unittest.TestCase):
    helper=None;api=None;workspace=None
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.cli=self.root/'fake-hostapd-cli';self.cli.write_text(MOCK);self.cli.chmod(0o755)
        self.feature=self.root/'feature';self.feature.write_text('OPENMITRASTAR_WPS=1\n')
        self.log=self.root/'calls.jsonl'
        self.env=dict(os.environ,F335_TEST_CLI_2G=str(self.cli),F335_TEST_CLI_5G=str(self.cli),
                      F335_TEST_FEATURE=str(self.feature),F335_TEST_LOCK_DIR=str(self.root/'locks'),
                      F335_MOCK_LOG=str(self.log),F335_TEST_TIMEOUT_MS='300')
        self.env.pop('F335_MOCK_MODE',None)
    def tearDown(self):self.tmp.cleanup()
    def run_helper(self,band='2g',action='status',data=b'',**env):
        p=subprocess.run([str(self.helper),band,action],input=data,capture_output=True,env=dict(self.env,**env),timeout=4)
        self.assertEqual(p.stderr,b'');return p,json.loads(p.stdout)
    def calls(self):return [json.loads(s) for s in self.log.read_text().splitlines()] if self.log.exists() else []
    def test_status2_redacts_peer(self):
        p,d=self.run_helper();self.assertEqual(p.returncode,0);self.assertEqual(d['state'],'idle');self.assertNotIn(b'02:00',p.stdout)
        self.assertEqual(self.calls()[0]['args'],['-p','/run/openmitrastar/radio2g/ctrl','-i','wlan0','raw','WPS_GET_STATUS'])
    def test_status5_enum_table(self):
        names=['WPS_INITIAL','WPS_START','WPS_SUCCESS','WPS_ERROR','WPS_TIMEOUT','WPS_OVERLAP','WPS_M2_SEND','WPS_M8_SEND','WPS_STA_CANCEL','WPS_STA_PIN_ERR','WPS_AP_PIN_SUC','WPS_AP_PIN_ERR','WPS_PIN_TIMEOUT']
        for n,name in enumerate(names):
            with self.subTest(code=n):
                p,d=self.run_helper('5g',F335_MOCK_STATUS5=f'{n}({name})');self.assertEqual(p.returncode,0);self.assertTrue(d['available'])
        self.assertEqual(self.calls()[0]['args'],['-p','/var/run/hostapd','-i','wifi0','wps_status'])
    def test_status5_mismatched_enum_refused(self):
        p,d=self.run_helper('5g',F335_MOCK_STATUS5='0(WPS_SUCCESS)');self.assertNotEqual(p.returncode,0);self.assertEqual(d['error'],'status-contract')
    def test_status_timeout_overlap_success(self):
        for pbc,state,last in [('Active','active','None'),('Timed-out','timed_out','None'),('Overlap','overlap','Failure'),('Disabled','success','Success')]:
            with self.subTest(pbc=pbc):
                p,d=self.run_helper(F335_MOCK_STATUS2=f'PBC Status: {pbc}\nLast WPS result: {last}\nPeer Address: REDACT');self.assertEqual(d['state'],state)
    def test_status_unknown_and_disabled(self):
        for mode,state in [('unsupported','unsupported'),('disabled','disabled'),('unknown_cli','unsupported')]:
            p,d=self.run_helper(F335_MOCK_MODE=mode);self.assertEqual(p.returncode,0);self.assertFalse(d['available']);self.assertEqual(d['state'],state)
    def test_status_without_feature_is_read_only(self):
        self.feature.unlink();p,d=self.run_helper();self.assertEqual(p.returncode,0);self.assertFalse(d['control_enabled']);self.assertFalse((self.root/'locks').exists())
    def test_baseline_daemon_unsupported_via_raw(self):
        self.feature.unlink();p,d=self.run_helper(F335_MOCK_MODE='legacy_baseline');self.assertEqual(p.returncode,0)
        self.assertFalse(d['available']);self.assertEqual(d['state'],'unsupported');self.assertFalse(d['control_enabled']);self.assertFalse((self.root/'locks').exists())
        self.assertEqual(self.calls()[0]['args'][4:],['raw','WPS_GET_STATUS'])
    def test_real_old_cli_unknown_zero_negative(self):
        p,d=self.run_helper(F335_MOCK_MODE='legacy_unknown_zero');self.assertEqual(p.returncode,0);self.assertFalse(d['available']);self.assertEqual(d['state'],'unsupported')
    def test_unknown_cli_requires_exact_response(self):
        p,d=self.run_helper(F335_MOCK_MODE='unknown_substring');self.assertEqual(p.returncode,4);self.assertEqual(d['error'],'status-contract')
    def test_feature_blocks_mutation(self):
        self.feature.unlink();p,d=self.run_helper(action='pbc');self.assertEqual(p.returncode,2);self.assertFalse(self.calls())
    def test_pbc_commands(self):
        for band,args in [('2g',['wps_pbc']),('5g',['wps_pbc','wifi0'])]:
            p,d=self.run_helper(band,'pbc');self.assertEqual(p.returncode,0);self.assertTrue(d['accepted']);self.assertFalse(d['enrolled']);self.assertEqual(self.calls()[-1]['args'][4:],args)
    def test_cancel_clears_registrar_and_ap_pin(self):
        for band,args in [('2g',['wps_cancel']),('5g',['wps_cancel','wifi0'])]:
            p,d=self.run_helper(band,'cancel');self.assertEqual(p.returncode,0);self.assertEqual(d['window_seconds'],0)
            calls=self.calls();self.assertEqual(calls[-2]['args'][4:],args);self.assertEqual(calls[-1]['operation'],'ap-pin-disable')
    def test_pin_stdin_not_argv_or_output(self):
        for band in ('2g','5g'):
            p,d=self.run_helper(band,'pin',b'12345670');self.assertEqual(p.returncode,0);self.assertNotIn(b'12345670',p.stdout)
            self.assertEqual(self.calls()[-1]['args'][4:],[]);self.assertTrue(self.calls()[-1]['stdin_valid']);self.assertNotIn('12345670',self.log.read_text())
    def test_pin_four_digits(self):
        p,d=self.run_helper(action='pin',data=b'1234');self.assertEqual(p.returncode,0);self.assertEqual(self.calls()[-1]['pin_length'],4)
    def test_bad_pin_refused_without_mutation(self):
        for pin in (b'12345678',b'123',b'12;3',b'1234\n9876',b'12345670\nextra'):
            with self.subTest(pin_length=len(pin)):
                p,d=self.run_helper(action='pin',data=pin);self.assertEqual(p.returncode,2);self.assertEqual(self.calls()[-1]['operation'],'raw')
    def test_ap_pin_bounded_and_not_disclosed(self):
        for band in ('2g','5g'):
            p,d=self.run_helper(band,'ap-pin',b'12345670');self.assertEqual(p.returncode,0);self.assertEqual(d['window_seconds'],120);self.assertNotIn(b'12345670',p.stdout)
            self.assertEqual(self.calls()[-1]['operation'],'ap-pin');self.assertEqual(self.calls()[-1]['pin_length'],8)
    def test_ap_pin_failure_rolls_back_only_disable(self):
        p,d=self.run_helper('5g','ap-pin',b'12345670',F335_MOCK_MODE='fail_ap_pin');self.assertEqual(p.returncode,4);self.assertEqual(d['error'],'ap-pin-start-failed-rolled-back')
        self.assertEqual([x['operation'] for x in self.calls()],['wps_status','ap-pin','ap-pin-disable'])
    def test_ap_pin_disable(self):
        p,d=self.run_helper('5g','ap-pin-disable');self.assertEqual(p.returncode,0);self.assertEqual(d['window_seconds'],0)
    def test_active_prevents_restart_but_allows_cancel(self):
        env={'F335_MOCK_STATUS5':'1(WPS_START)'}
        p,d=self.run_helper('5g','pbc',**env);self.assertEqual(p.returncode,3)
        p,d=self.run_helper('5g','cancel',**env);self.assertEqual(p.returncode,0)
    def test_failure_ack_exit_and_output_limit(self):
        for mode in ('fail_command','exit_error','overflow','stderr','bad_status'):
            with self.subTest(mode=mode):
                p,d=self.run_helper(action='pbc',F335_MOCK_MODE=mode);self.assertNotEqual(p.returncode,0);self.assertFalse(d['ok'])
    def test_deadlines_status_and_command(self):
        for mode in ('hang_status','hang_command'):
            started=time.monotonic();p,d=self.run_helper(action='pbc',F335_MOCK_MODE=mode,F335_TEST_TIMEOUT_MS='60');self.assertLess(time.monotonic()-started,1);self.assertEqual(d['error'],'control-timeout')
    def test_per_band_lock_blocks_overlapping_control(self):
        env=dict(self.env,F335_MOCK_MODE='slow_command',F335_TEST_TIMEOUT_MS='1500')
        first=subprocess.Popen([str(self.helper),'2g','pbc'],stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
        try:
            deadline=time.monotonic()+1
            while time.monotonic()<deadline and not any(c['operation']=='wps_pbc' for c in self.calls()):time.sleep(.01)
            p,d=self.run_helper('2g','cancel');self.assertEqual(p.returncode,3);self.assertEqual(d['error'],'busy')
            stdout,stderr=first.communicate(timeout=3);self.assertEqual(first.returncode,0);self.assertEqual(stderr,b'');self.assertTrue(json.loads(stdout)['accepted'])
        finally:
            if first.poll() is None:first.kill();first.wait()
    def test_configuration_no_enrollment(self):
        for band in ('2g','5g'):
            p=subprocess.run([str(self.helper),band,'config'],capture_output=True,env=self.env,check=True)
            self.assertIn(b'wps_state=2\n',p.stdout);self.assertIn(b'ap_setup_locked=1\n',p.stdout);self.assertIn(b'wps_cred_processing=1\n',p.stdout)
            self.assertNotIn(b'wps_pbc',p.stdout);self.assertNotIn(b'ap_pin=',p.stdout)
            self.assertEqual(b'ap_pin_fail_method=default' in p.stdout,band=='5g')
        self.assertFalse(self.calls())
    def test_configuration_disabled_without_feature(self):
        self.feature.unlink();p=subprocess.run([str(self.helper),'2g','config'],capture_output=True,env=self.env,check=True);self.assertEqual(p.stdout,b'wps_state=0\n')
    def test_startup_delta_only_wps_and_log_privacy(self):
        base=self.workspace/'versions/f335-wps-control/baseline/usr/sbin';new=self.workspace/'versions/f335-wps-control/overlay/usr/sbin'
        radio2=(new/'om-radio-start').read_text().replace('/usr/sbin/om-wpsctl 2g config >>"$state/hostapd.conf" || refuse wps-config\n','').replace('"$hostapd" -q -f','"$hostapd" -f')
        radio5=(new/'om-radio5-start').read_text().replace('/usr/sbin/om-wpsctl 5g config >>"$conf" || refuse wps-config\n','').replace('/usr/sbin/hostapd-qtn -q -f','/usr/sbin/hostapd-qtn -dd -f')
        self.assertEqual(radio2,(base/'om-radio-start').read_text());self.assertEqual(radio5,(base/'om-radio5-start').read_text())
        self.assertNotIn(' -B ',(new/'om-radio-start').read_text());self.assertNotIn(' -B ',(new/'om-radio5-start').read_text())
        self.assertFalse((new/'om-rtlctl').exists())
        rtl=(base/'om-rtlctl').read_text();self.assertIn('[HT40+]',rtl);self.assertIn('[HT40-]',rtl)
    def api_call(self,endpoint,method='GET',body=b'',authenticated=True,csrf=True,content_type='application/x-www-form-urlencoded'):
        sessions=self.root/'sessions';sessions.mkdir(exist_ok=True);token='a'*64;secret='b'*64;remote='127.0.0.1'
        (sessions/token).write_text(f'expires={int(time.time())+3600}\naddr_sha256={hashlib.sha256(remote.encode()).hexdigest()}\ncsrf={secret}\n')
        env=dict(self.env,OM_WEB_SESSION_DIR=str(sessions),OM_WPSCTL=str(self.helper),REQUEST_METHOD=method,
                 CONTENT_LENGTH=str(len(body)),CONTENT_TYPE=content_type,REMOTE_ADDR=remote,
                 HTTP_COOKIE='OMSESSION='+token if authenticated else '',HTTP_X_OM_CSRF=secret if csrf else 'wrong')
        env.pop('OM_API_AUTH_BYPASS',None)
        p=subprocess.run(['sh',str(self.api),endpoint],input=body,capture_output=True,env=env,timeout=4)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stderr,b'');return p.stdout
    def test_api_auth_and_csrf_before_commands(self):
        self.assertIn(b'403 Forbidden',self.api_call('radios/2g/wps',authenticated=False));self.assertFalse(self.calls())
        self.assertIn(b'403 Forbidden',self.api_call('radios/5g/wps/pbc','POST',csrf=False));self.assertFalse(self.calls())
    def test_api_methods_and_paths(self):
        self.assertIn(b'405 Method',self.api_call('radios/2g/wps/pbc'))
        self.assertIn(b'405 Method',self.api_call('radios/2g/wps','POST'))
        self.assertIn(b'404 Not',self.api_call('radios/6g/wps'))
        self.assertFalse(self.calls())
    def test_api_status_and_mutation(self):
        data=self.api_call('radios/5g/wps');self.assertIn(b'"state":"idle"',data)
        data=self.api_call('radios/2g/wps/pbc','POST');self.assertIn(b'"accepted":true',data)
        data=self.api_call('radios/5g/wps/pin','POST',b'pin=12345670');self.assertIn(b'"accepted":true',data);self.assertNotIn(b'12345670',data)
        data=self.api_call('radios/5g/wps/ap-pin','POST',b'pin=12345670');self.assertIn(b'"accepted":true',data);self.assertNotIn(b'12345670',data)
    def test_api_bad_pin_bodies_and_content_type(self):
        for body in (b'pin=12;3',b'pin=1234&x=1',b'wrong=1234'):
            self.assertIn(b'400 Bad',self.api_call('radios/2g/wps/pin','POST',body))
        self.assertIn(b'415 Unsupported',self.api_call('radios/2g/wps/pin','POST',b'pin=1234',content_type='application/json'))
        self.assertFalse(self.calls())
    def test_api_cancel_and_ap_disable(self):
        self.assertIn(b'"accepted":true',self.api_call('radios/5g/wps/cancel','POST'))
        self.assertIn(b'"accepted":true',self.api_call('radios/5g/wps/ap-pin-disable','POST'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--helper',type=Path,required=True);p.add_argument('--api',type=Path,required=True);p.add_argument('--workspace',type=Path,required=True);p.add_argument('--result',type=Path,required=True);args=p.parse_args()
    WpsTests.helper=args.helper;WpsTests.api=args.api;WpsTests.workspace=args.workspace
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(WpsTests))
    args.result.write_text(json.dumps({'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'hardware_actions':False,'success':result.wasSuccessful()},indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
