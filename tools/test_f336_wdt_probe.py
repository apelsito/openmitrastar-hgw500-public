"""Exercise actual F336 userspace state machine with fake driver, no hardware."""
from pathlib import Path
import argparse,json,os,subprocess,tempfile,unittest
class ProbeTests(unittest.TestCase):
    binary=None
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        values={'proc/device-tree/openmitrastar,f336-wdt-ram':b'F336_WDT_RAM_ONLY\0','proc/device-tree/compatible':b'mitrastar,hgw-500bna-qcv2\0quantenna,topaz\0',
                'sys/class/watchdog/watchdog0/identity':b'Topaz DesignWare watchdog\n','sys/class/watchdog/watchdog0/state':b'inactive\n',
                'sys/class/watchdog/watchdog0/nowayout':b'1\n','sys/class/watchdog/watchdog0/f336_control':b'00000000\n','sys/class/watchdog/watchdog0/f336_counter':b'40000000\n'}
        for name,data in values.items():p=self.root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
        self.env=dict(os.environ,F336_TEST_ROOT=str(self.root),F336_TEST_SESSION_MS='200',F336_TEST_OBSERVE_MS='60',F336_TEST_SAMPLE_MS='10')
    def tearDown(self):self.temp.cleanup()
    def run_probe(self,commands=None,extra=None,args=None):
        argv=[str(self.binary)]+(args if args is not None else ['--session'] if commands is not None else [])
        p=subprocess.run(argv,input=commands.encode() if commands is not None else b'',env=dict(self.env,**(extra or {})),capture_output=True,timeout=2)
        self.assertEqual(p.stderr,b'');return p,[json.loads(s) for s in p.stdout.splitlines()]
    def test_default_does_not_open_device(self):
        p,r=self.run_probe();self.assertEqual(p.returncode,0);self.assertEqual(r[0]['ready_for_arm'],1);self.assertEqual(r[-1]['device_opens'],0);self.assertEqual(r[-1]['ioctls'],0)
    def test_session_status_does_not_open_device(self):
        p,r=self.run_probe('STATUS\n');self.assertEqual(p.returncode,0);self.assertEqual(r[-1]['device_opens'],0)
    def test_prearmed_hardware_refused_despite_inactive_framework(self):
        (self.root/'sys/class/watchdog/watchdog0/f336_control').write_text('00000001\n')
        p,r=self.run_probe('ARM\n');self.assertNotEqual(p.returncode,0);self.assertEqual(r[-1]['device_opens'],0)
    def test_wrong_ram_marker_refused(self):
        (self.root/'proc/device-tree/openmitrastar,f336-wdt-ram').write_text('F321')
        p,r=self.run_probe('ARM\n');self.assertEqual(r[-1]['device_opens'],0)
    def test_wrong_driver_refused(self):
        (self.root/'sys/class/watchdog/watchdog0/identity').write_text('Other watchdog')
        p,r=self.run_probe('ARM\n');self.assertEqual(r[-1]['device_opens'],0)
    def test_framework_active_refused(self):
        (self.root/'sys/class/watchdog/watchdog0/state').write_text('active\n')
        p,r=self.run_probe('ARM\n');self.assertEqual(r[-1]['device_opens'],0)
    def test_missing_counter_refused(self):
        (self.root/'sys/class/watchdog/watchdog0/f336_counter').unlink()
        p,r=self.run_probe('ARM\n');self.assertEqual(r[-1]['device_opens'],0)
    def test_expiry_keeps_fd_until_negative_verdict(self):
        p,r=self.run_probe('ARM\nPET\nSTATUS\nCEASE\nPET\n')
        self.assertEqual(p.returncode,3);self.assertEqual(r[-1]['device_opens'],1);self.assertEqual(r[-1]['device_closes'],1);self.assertEqual(r[-1]['program_pets'],2)
        verdict=next(i for i,v in enumerate(r) if v.get('event')=='verdict');closed=next(i for i,v in enumerate(r) if v.get('event')=='close_after_verdict')
        self.assertLess(verdict,closed);self.assertEqual(r[verdict]['result'],'NO_RESET_WITHIN_WINDOW');self.assertTrue(r[verdict]['fd_held'])
        self.assertTrue(any(v.get('event')=='sample' for v in r));self.assertEqual(r[-1]['ioctls'],6)
    def test_repeated_arm_never_reopens(self):
        p,r=self.run_probe('ARM\nARM\nCEASE\n');self.assertEqual(r[-1]['device_opens'],1);self.assertEqual(r[-1]['program_pets'],1)
    def test_abort_is_not_watchdog_success(self):
        p,r=self.run_probe('ARM\nABORT\n');self.assertEqual(p.returncode,2);self.assertTrue(any(v.get('result')=='OPERATOR_ABORT_NOT_WDT_PASS' for v in r))
    def test_unknown_cli_argument_never_opens(self):
        p,r=self.run_probe(args=['--arm']);self.assertEqual(p.returncode,2);self.assertEqual(r[-1]['device_opens'],0)
    def test_counter_reload_reported_without_hidden_pet(self):
        p,r=self.run_probe('ARM\nCEASE\n',{'F336_TEST_RELOAD':'1'})
        verdict=next(v for v in r if v.get('event')=='verdict');self.assertGreater(verdict['unexplained_counter_increases'],0);self.assertEqual(r[-1]['program_pets'],1)
    def test_postopen_ioctl_error_reports_unknown_and_closes_after_verdict(self):
        p,r=self.run_probe('ARM\n',{'F336_TEST_IOCTL_FAIL':'1'});self.assertNotEqual(p.returncode,0);self.assertEqual(r[-1]['device_opens'],1);self.assertEqual(r[-1]['program_pets'],0)
        self.assertTrue(any(v.get('result')=='ARM_NOT_QUALIFIED' for v in r));self.assertTrue(any(v.get('hardware_state')=='unknown' for v in r))
    def test_input_loss_without_cease_is_not_success(self):
        p,r=self.run_probe('ARM\n');self.assertEqual(p.returncode,3);self.assertTrue(any(v.get('result')=='SESSION_INCOMPLETE' for v in r))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--binary',type=Path,required=True);ap.add_argument('--result',type=Path,required=True);args=ap.parse_args();ProbeTests.binary=args.binary
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProbeTests));args.result.write_text(json.dumps({'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'passed':result.wasSuccessful(),'hardware_actions':False})+'\n');raise SystemExit(0 if result.wasSuccessful() else 1)
