"""Focal guard/readonly tests with fake PS/SSH children; no hardware."""
from pathlib import Path
import hashlib,json,subprocess,tempfile,time,unittest
from unittest.mock import patch
import f367_readonly_guard_v3 as gate

TOKEN='a'*32
BOOT='11111111-2222-3333-4444-555555555555'

class Process:
    next_pid=1000
    def __init__(self,out=b'',err=b'',code=0,timeout=False,uncontained=False):
        Process.next_pid+=1;self.pid=Process.next_pid;self.out=out;self.err=err
        self.code=code;self.returncode=None;self.timeout=timeout;self.uncontained=uncontained;self.killed=False
    def communicate(self,*args,**kwargs):
        if self.timeout and (not self.killed or self.uncontained):
            raise subprocess.TimeoutExpired('FAKE_ROLE_ONLY',kwargs.get('timeout',0),output=self.out,stderr=self.err)
        self.returncode=-9 if self.killed else self.code
        return self.out,self.err
    def poll(self):return self.returncode
    def kill(self):
        if self.uncontained:raise OSError('FAKE_UNCONTAINED')
        self.killed=True;self.returncode=-9

class Rig:
    def __init__(self,folder,guards):
        self.folder=Path(folder);self.guards=list(guards);self.guard_calls=0;self.status_calls=0;self.owner_calls=0;self.control_calls=0
        source=self.folder/'source';source.write_text('bound')
        self.host=gate.Host({'sources':{str(source):hashlib.sha256(source.read_bytes()).hexdigest()}},self.folder)
        self.host.owner_token=TOKEN;self.host.owner_total_deadline=5550611
        self.host.installed_receipt={'boot_id':BOOT}
        self.host.ssh_argv=lambda command:['FAKE_SSH',command]
    def popen(self,args,**kwargs):
        if '-File' in args:
            mode=self.guards[self.guard_calls];self.guard_calls+=1
            if mode=='timeout':return Process(timeout=True)
            if mode=='uncontained':return Process(timeout=True,uncontained=True)
            if mode=='fail':return Process(err=b'F367_CONTEXT_SCOPE\n',code=1)
            if mode=='invalid':return Process(out=b'UNEXPECTED\n')
            return Process(out=b'PASS_F367_CAMPAIGN_CONTEXT\n')
        command=args[1]
        if command=='/usr/sbin/om-f367-control status':
            self.status_calls+=1
            row={key:0 for key in gate.core.campaign_logic.PROVIDER_FIELDS}
            row.update(schema='openmitrastar.f367-state/v1',provider_started=1,provider_hardware_ready=1,
                       monotonic_ms=self.status_calls,jobs_completed=self.status_calls*100,native_callbacks=0)
            return Process(out=json.dumps(row).encode())
        if command=='/usr/sbin/om-watchdog-supervisor-f367 --status '+TOKEN:
            self.owner_calls+=1
            row=dict(schema='openmitrastar.f367-supervisor-state/v1',nonce=TOKEN,boot_id=BOOT,
                     peer_verified=True,fd_held=True,hardware_arm_confirmed=True,first_pet_confirmed=True,
                     error=False,state='phase-active',phase_sequence=25,session_deadline_monotonic_ms=5550611)
            return Process(out=json.dumps(row).encode())
        self.control_calls+=1
        return Process(out=b'OMF367_ERROR reason=synthetic\n',timeout=True)
    def receipts(self):
        return [json.loads(path.read_text()) for path in (self.folder/'host-observations').glob('*.json')]

class ReadonlyGuardTests(unittest.TestCase):
    def test_owner_guard_timeout_restarts_full_sample_with_fresh_state(self):
        with tempfile.TemporaryDirectory() as folder:
            rig=Rig(folder,['pass','timeout','pass','pass'])
            with patch.object(gate.subprocess,'Popen',side_effect=rig.popen):
                row=rig.host.snapshot()
            self.assertEqual((rig.guard_calls,rig.status_calls,rig.owner_calls),(4,2,1))
            self.assertEqual(row['monotonic_ms'],2)
            retries=[row for row in rig.receipts() if row['schema']=='openmitrastar.f367-read-retry/v1']
            self.assertEqual(len(retries),1);self.assertTrue(retries[0]['partial_state_discarded'])
            self.assertEqual(retries[0]['trigger_operation'],'owner')
    def test_second_guard_timeout_aborts(self):
        with tempfile.TemporaryDirectory() as folder:
            rig=Rig(folder,['timeout','timeout'])
            with patch.object(gate.subprocess,'Popen',side_effect=rig.popen):
                with self.assertRaises(gate.GuardTimeout):rig.host.snapshot()
            self.assertEqual((rig.guard_calls,rig.status_calls),(2,0))
    def test_real_failure_and_invalid_output_never_retry(self):
        for mode in ('fail','invalid'):
            with tempfile.TemporaryDirectory() as folder:
                rig=Rig(folder,[mode])
                with patch.object(gate.subprocess,'Popen',side_effect=rig.popen):
                    with self.assertRaises(gate.core.Failure):rig.host.snapshot()
                self.assertEqual((rig.guard_calls,rig.status_calls),(1,0))
    def test_uncontained_timeout_never_retries(self):
        with tempfile.TemporaryDirectory() as folder:
            rig=Rig(folder,['uncontained'])
            with patch.object(gate.subprocess,'Popen',side_effect=rig.popen):
                with self.assertRaises(gate.GuardTimeout):rig.host.snapshot()
            self.assertEqual(rig.guard_calls,1)
    def test_control_guard_and_ambiguous_control_are_not_retried(self):
        for mode,expected_controls in [('timeout',0),('pass',1)]:
            with tempfile.TemporaryDirectory() as folder:
                rig=Rig(folder,[mode])
                with patch.object(gate.subprocess,'Popen',side_effect=rig.popen):
                    with self.assertRaises(gate.core.Failure):rig.host.raw_control('enter-dfs')
                self.assertEqual(rig.guard_calls,1);self.assertEqual(rig.control_calls,expected_controls)
    def test_expired_existing_deadline_blocks_retry_without_extending(self):
        with tempfile.TemporaryDirectory() as folder:
            rig=Rig(folder,['timeout'])
            def popen(*args,**kwargs):
                rig.host._scope().deadline=time.monotonic()-1
                return rig.popen(*args,**kwargs)
            with rig.host.read_budget(time.monotonic()+30):
                with patch.object(gate.subprocess,'Popen',side_effect=popen):
                    with self.assertRaises(gate.core.Failure):rig.host.snapshot()
            self.assertEqual(rig.guard_calls,1)

if __name__=='__main__':unittest.main()
