"""Actual F356 orchestration with fake hardware; actual shared Capture contracts."""
from pathlib import Path
from unittest.mock import patch,Mock
import argparse,hashlib,json,subprocess,tempfile,threading,unittest
import f356_observe_executor as x
import f356_protocol as p
from f325_ethernet_ram_gate import GateFailure
BOOT='01234567-89ab-cdef-0123-456789abcdef'
RAMBOOT='12345678-9abc-def0-1234-56789abcdef0'
PID=1234
TOKEN='a'*32
def owner(token=TOKEN,op=1):
    row=dict(schema='openmitrastar.f340-supervisor-state/v1',peer_verified=True,nonce=token,boot_id=RAMBOOT,owner_pid=PID,owner_start_ticks=123456,phase='',state='idle',op=op,ack_sequence=0,phase_sequence=0,pet_count=0,timeout_reported_seconds=0,last_pet_monotonic_ms=0,phase_deadline_monotonic_ms=0,session_deadline_monotonic_ms=0,error=False,fd_held=False,hardware_arm_confirmed=False,first_pet_confirmed=False)
    if op!=1:row.update(state='waiting-phase',ack_sequence=1,pet_count=1,timeout_reported_seconds=8,last_pet_monotonic_ms=1000,phase_deadline_monotonic_ms=6000,session_deadline_monotonic_ms=181000,fd_held=True,hardware_arm_confirmed=True,first_pet_confirmed=True)
    if op in (3,6):row.update(state='phase-active' if op==3 else 'ceased-fd-held',phase_sequence=1,phase=p.PHASE,phase_deadline_monotonic_ms=61000)
    return row
OBS=dict(status='observed',id='c22018',control='00000004',status_register=0,security_register=0,common_bp0=1,exact_part_verified=False)
MARK=b'OMF356 observe rc=0 id=c22018 control=00000004 status=00 security=00 valid=0f claimed=0 quarantined=0\n'
LOAD=b'load_rc=0\nloader_report=ok\nloader_stderr_present=0\nallow_hw=Y\nallow_program=N\nmodule_present=1\nnode_present=1\nboot_id='+RAMBOOT.encode()+b'\n'
UNLOAD=b'unload_rc=0\nmodule_present=0\nnode_present=0\n'
class Protocol(unittest.TestCase):
    def test_observe_accepts_readonly_protected_states_without_claiming_exact_part(self):
        for status,security in [(0,0),(0x04,0),(0,0x80),(0,0x60),(2,0)]:
            row=dict(OBS,status_register=status,security_register=security,common_bp0=int(not status&0x3f and not security&0x9c));out=p.observed(json.dumps(row).encode(),4)
            self.assertFalse(out['exact_part_verified']);self.assertFalse(out['claimed']);self.assertTrue(out['release_verified_by_pinned_cli'])
    def test_observe_rejects_unknown_id_control_wip_incomplete_and_false_types(self):
        for key,value in [('id','abcdef'),('control','00000000'),('status_register',1),('security_register',256),('common_bp0',True),('exact_part_verified',True),('status','saved')]:
            row=dict(OBS);row[key]=value
            with self.subTest(key=key),self.assertRaises(p.ProtocolError):p.observed(json.dumps(row).encode(),4)
        with self.assertRaises(p.ProtocolError):p.observed(b'{"status":"observed","status":"saved"}',4)
    def test_program_gate_and_release_required(self):
        p.loaded(LOAD,RAMBOOT);p.unloaded(UNLOAD)
        for raw in [LOAD.replace(b'allow_program=N',b'allow_program=Y'),LOAD.replace(b'allow_hw=Y',b'allow_hw=N'),LOAD.replace(b'load_rc=0',b'load_rc=1'),LOAD.replace(b'node_present=1',b'node_present=0')]:
            with self.assertRaises(p.ProtocolError):p.loaded(raw,RAMBOOT)
        with self.assertRaises(p.ProtocolError):p.unloaded(UNLOAD.replace(b'module_present=0',b'module_present=1'))
    def test_uart_marker_exact_and_partial_validity(self):
        row=p.marker_verified(MARK,OBS);self.assertEqual(row['valid_mask'],15)
        raw=MARK.replace(b'rc=0 id=c22018',b'rc=-95 id=abcdef').replace(b'valid=0f',b'valid=07');partial=p.marker_diagnostic(raw)['markers'][0]
        self.assertTrue(partial['read_validity']['id']);self.assertFalse(partial['read_validity']['security'])
        with self.assertRaises(p.ProtocolError):p.marker_verified(raw,OBS)
    def test_uart_marker_rejects_claim_quarantine_duplicate_and_mismatch(self):
        for raw in [MARK.replace(b'claimed=0',b'claimed=1'),MARK.replace(b'quarantined=0',b'quarantined=1'),MARK+MARK,MARK.replace(b'control=00000004',b'control=00000005'),MARK+b'Kernel panic\n']:
            with self.assertRaises(p.ProtocolError):p.marker_verified(raw,OBS)
    def test_diagnostic_never_saves_secrets_or_payload(self):
        row=p.diagnostic('observe',b'PSK=TOPSECRET',b'journal response rejected\nTOPSECRET\n',1,False)
        self.assertNotIn('TOPSECRET',json.dumps(row));self.assertEqual(row['known_errors'],['journal response rejected'])
        row=p.diagnostic('load',LOAD+b'password=TOPSECRET\n',b'',0,False);self.assertNotIn('TOPSECRET',json.dumps(row));self.assertEqual(row['fields']['allow_program'],'N')

class Model:
    def __init__(self,scenario):self.scenario=scenario;self.actions=[];self.data=b'';self.ready=False;self.reset_times=[];self.failed=None;self.loads=0;self.observes=0;self.unloads=0;self.returns=0;self.ramboots=0;self.software=0;self.token=None;self.disk_low=False
    def reset(self):self.reset_times.append(1000+len(self.reset_times));self.data+=b'\nBoot reached stage 13\ntopaz> ';self.ready=True
class FakeHost:
    model=None
    def __init__(self,plan,out):self.s=self.model;self.plan=plan;self.out=out;self.servers=[]
    def guard(self):return self.s.scenario!='lease_fail'
    def identity(self,name):return dict(boot_id=(RAMBOOT if self.s.scenario!='boot_changed_while_ready' else BOOT) if name=='ram' else BOOT,uts='#350 @1790006400' if name=='ram' else '#340 @1790006400')
    def platform(self,name,out):
        self.s.actions.append('platform_ready')
        if self.s.scenario=='startup_not_ready':raise x.Failure('platform_gate')
        return dict(status='PASS',checks=27)
    def initial_binding(self,row):return self.s.scenario!='nonce_mismatch'
    def preflight(self):
        if self.s.scenario=='existing_owner':raise x.Failure('baseline_owner_or_loader')
        return dict(ready_for_arm=1,control='00000000')
    def storage_gate(self):return dict(persist_readonly=True)
    def devtmpfs_ready(self):
        if self.s.scenario=='missing_devtmpfs':raise x.Failure('devtmpfs_not_ready')
        return dict(filesystem='devtmpfs')
    def stage(self,run_id):self.s.actions.append('stage');self.stage_dir='/fixture/'+run_id
    def inspect_ram(self):
        if self.s.scenario=='wrong_guardian_profile':raise x.Failure('ram_watchdog_profile')
        return dict(kernel_profile_verified=1,required_kernel_version='#350 @1790006400')
    def launch_owner(self,token):
        self.s.token=token;self.s.actions.append('owner_launch')
        if self.s.scenario=='launch_reply_lost':raise x.Failure('ssh_deadline')
        return PID
    def status(self,token):return owner(token)
    def arm_begin(self,token):
        self.s.actions.append('arm')
        if self.s.scenario=='arm_reply_lost':raise x.Failure('ssh_deadline')
        return [owner(token,2),owner(token,3)]
    def load_provider(self):
        self.s.actions.append('load');self.s.loads+=1
        if self.s.scenario=='load_timeout':raise x.Failure('ssh_deadline')
        if self.s.scenario=='program_gate_wrong':return LOAD.replace(b'allow_program=N',b'allow_program=Y')
        if self.s.scenario=='load_failed':return LOAD.replace(b'load_rc=0',b'load_rc=1')
        return LOAD
    def observe_provider(self):
        self.s.actions.append('observe');self.s.observes+=1;raw=MARK;row=dict(OBS)
        if self.s.scenario=='quarantined':raw=raw.replace(b'rc=0',b'rc=-5').replace(b'quarantined=0',b'quarantined=1')
        if self.s.scenario=='claimed':raw=raw.replace(b'rc=0',b'rc=-5').replace(b'claimed=0',b'claimed=1')
        if self.s.scenario=='unknown_id':raw=raw.replace(b'rc=0 id=c22018',b'rc=-95 id=abcdef').replace(b'valid=0f',b'valid=07')
        if self.s.scenario=='duplicate_marker':raw+=MARK
        if self.s.scenario=='wrong_marker':raw=raw.replace(b'control=00000004',b'control=00000005')
        if self.s.scenario=='marker_missing':raw=b''
        if self.s.scenario=='uart_fatal':raw+=b'Kernel panic\n'
        self.s.data+=raw
        if self.s.scenario in ('reset_during_observe','reset_prompt_delayed'):
            self.s.reset()
            if self.s.scenario=='reset_prompt_delayed':self.s.ready=False
        if self.s.scenario in ('quarantined','claimed','unknown_id','observe_timeout'):raise x.Failure('ssh_deadline' if self.s.scenario=='observe_timeout' else 'ssh_failed')
        if self.s.scenario=='invalid_response':row['exact_part_verified']=True
        return json.dumps(row).encode()
    def unload_provider(self):
        self.s.actions.append('unload');self.s.unloads+=1
        if self.s.scenario=='unload_failed':return UNLOAD.replace(b'unload_rc=0',b'unload_rc=1')
        return UNLOAD
    def cease(self,token):
        self.s.actions.append('cease')
        if self.s.scenario=='cease_failed':raise x.Failure('ssh_failed')
        return owner(token,6)
    def reboot_to_prompt(self,uart,software_recovery=False):
        uart.stop_autoboot(120);uart.invalidate_prompt();self.s.actions.append('software_reboot' if software_recovery else 'initial_reboot')
        if software_recovery:self.s.software+=1
        if self.s.scenario=='no_recovery_prompt' and software_recovery:raise x.Failure('new_prompt_missing')
        self.s.reset()
    def contain(self):return self.s.scenario!='containment_failed'
class FakeUart:
    def __init__(self,plan,guard,out):self.s=FakeHost.model;self.guard=guard;self.auto_seen=set();self.auto_count=0
    @property
    def reset_times(self):return self.s.reset_times
    @property
    def failed(self):return self.s.failed
    def open(self):self.s.actions.append('uart_open')
    def close(self):return dict(reader_stopped=True,port_closed=True,reader_error='reader_failure' if self.s.scenario=='reader_failed' else None)
    def checkpoint(self):return len(self.s.data)
    def since(self,start):return self.s.data[start:]
    def invalidate_prompt(self):self.s.ready=False
    # Exercise the real deadline/floor code, not a permissive fake.
    def stop_autoboot(self,seconds):return x.ram.Capture.stop_autoboot(self,seconds)
    def has_prompt(self):return self.s.ready
    def wait_prompt(self,seconds,start=None):
        if self.s.scenario=='reset_prompt_delayed':self.s.actions.append('wait_fresh_prompt');self.s.ready=True
        x.require(self.s.ready,'prompt_missing')
class Pipeline(unittest.TestCase):
    def case(self,scenario):
        s=Model(scenario);FakeHost.model=s
        def ram_boot(uart,host,plan,out):
            s.ramboots+=1;s.actions.append('ram_boot')
            if scenario=='ram_bootm_returned':raise x.Failure('bootm_returned_no_retry')
            s.ready=False
            if scenario=='ram_silent':raise x.Failure('boot_identity_timeout')
            return dict(boot_id=RAMBOOT,uts='#350 @1790006400'),{'status':'PASS'}
        def reset(uart,count,seconds):
            if scenario in ('no_cleanup_reset','no_recovery_prompt'):return False
            if len(s.reset_times)==count:s.reset()
            return True
        def marker(uart,start,count):
            x.require(len(s.reset_times)==count,'reset_instead_of_observe');x.require(p.FATAL.search(uart.since(start)) is None,'fault_during_observe');x.require(p.MARKER.search(uart.since(start)),'observe_marker_deadline');return uart.since(start)
        def restore(*args,**kwargs):
            s.returns+=1;s.actions.append('return')
            if scenario=='disk_low_during_return':s.disk_low=True
            if scenario=='return_bootm_returned':raise x.Failure('bootm_returned_no_retry')
            return dict(identity={'boot_id':'new-f340'},platform={'checks':27},watchdog={'control':'00000000'},readback_error='flash_crc_mismatch' if scenario=='return_crc_failed' else None)
        original_floor=x.disk_floor
        def floor():
            if s.disk_low or (scenario=='disk_low_after_arm' and 'arm' in s.actions):raise x.Failure('evidence_disk_floor')
            return original_floor()
        original_save=x.save
        def write_evidence(path,value):
            if scenario=='evidence_failure_before_return' and path.name=='progress.json' and value.get('stage')=='readonly-f340-return':raise OSError('simulated disk error')
            if scenario=='evidence_failure_after_return' and path.name=='progress.json' and value.get('stage')=='complete':raise OSError('simulated disk error')
            return original_save(path,value)
        with tempfile.TemporaryDirectory(prefix='f356-offline-') as directory,patch.object(x,'save',write_evidence),patch.object(x,'disk_floor',floor),patch.object(x.previous,'wait_reset',reset),patch.object(x.previous,'return_f340',restore),patch.object(x,'wait_marker',marker),patch.object(x.ram,'inactive_hardware',lambda uart:dict(controls=[0,0],counters=[65535,65535])),patch.object(x.boot,'protected',lambda *a:dict(preserved=True)),patch.object(x.boot,'flash_crc',lambda *a:'2aa26ca6'):
            rc=x.run({'images':{'f340':{'full_slot_crc32':'2aa26ca6'}},'expected_spi_control':4},Path(directory),FakeHost,FakeUart,ram_boot)
            r=json.loads((Path(directory)/'result.json').read_text(encoding='ascii'))
            if s.token:self.assertNotIn(s.token,json.dumps(r))
        self.assertLessEqual(s.loads,1);self.assertLessEqual(s.observes,1);self.assertLessEqual(s.unloads,1);self.assertLessEqual(s.returns,1);self.assertLessEqual(s.ramboots,1)
        return s,rc,r
    def test_success_one_ram_boot_owner_before_load_one_observe_release_unload_return(self):
        s,rc,r=self.case('success');self.assertEqual(rc,0);self.assertEqual((s.loads,s.observes,s.unloads,s.returns),(1,1,1,1));self.assertLess(s.actions.index('arm'),s.actions.index('load'));self.assertLess(s.actions.index('observe'),s.actions.index('unload'));self.assertTrue(r['baseline_returned']);self.assertFalse(r['guardian_may_remain_armed'])
    def test_baseline_refusals_do_not_open_uart(self):
        for case in ('lease_fail','nonce_mismatch','existing_owner'):
            s,rc,r=self.case(case);self.assertEqual(rc,1);self.assertNotIn('uart_open',s.actions);self.assertEqual(s.loads,0)
    def test_ram_boot_failure_has_one_readonly_return_no_arm(self):
        for case in ('ram_bootm_returned','ram_silent','missing_devtmpfs','wrong_guardian_profile','startup_not_ready','boot_changed_while_ready'):
            s,rc,r=self.case(case);self.assertEqual(rc,1);self.assertEqual(s.returns,1);self.assertEqual(s.loads,0);self.assertNotIn('arm',s.actions)
    def test_lost_owner_launch_reconciles_then_reboots_without_module(self):
        s,rc,r=self.case('launch_reply_lost');self.assertEqual(rc,1);self.assertIn('owner_reconciled',r);self.assertEqual(s.loads,0);self.assertTrue(r['baseline_returned'])
    def test_lost_arm_reply_prevents_loading(self):
        s,rc,r=self.case('arm_reply_lost');self.assertEqual(rc,1);self.assertEqual(s.loads,0);self.assertTrue(r['baseline_returned'])
    def test_low_disk_after_arm_stops_new_work_but_keeps_cease_reset_and_return(self):
        s,rc,r=self.case('disk_low_after_arm');self.assertEqual(rc,1);self.assertEqual(r['error'],'evidence_disk_floor');self.assertEqual(s.loads,0);self.assertIn('cease',s.actions);self.assertTrue(r['baseline_returned']);self.assertFalse(r['guardian_may_remain_armed'])
    def test_low_disk_during_return_does_not_interrupt_it_or_small_final_evidence(self):
        s,rc,r=self.case('disk_low_during_return');self.assertEqual(rc,0);self.assertTrue(s.disk_low);self.assertTrue(r['baseline_returned']);self.assertFalse(r['retain_lease_required'])
    def test_real_evidence_error_preserved_while_recovering_first(self):
        s,rc,r=self.case('evidence_failure_before_return');self.assertEqual(rc,1);self.assertEqual(r['error'],'evidence_write_failed');self.assertTrue(r['baseline_returned']);self.assertEqual(s.returns,1);self.assertEqual(s.software,0)
    def test_final_progress_error_downgrades_pass_without_repeating_return(self):
        s,rc,r=self.case('evidence_failure_after_return');self.assertEqual(rc,1);self.assertEqual(r['status'],'FAILED');self.assertEqual(r['error'],'evidence_write_failed');self.assertTrue(r['baseline_returned']);self.assertEqual(s.returns,1);self.assertEqual(s.software,0)
    def test_load_failure_or_wrong_gate_never_observes_or_unloads(self):
        for case in ('load_timeout','load_failed','program_gate_wrong'):
            s,rc,r=self.case(case);self.assertEqual(rc,1);self.assertEqual((s.loads,s.observes,s.unloads),(1,0,0));self.assertTrue(r['baseline_returned'])
    def test_unknown_or_failed_observe_never_unloads_and_preserves_uart(self):
        for case in ('claimed','quarantined','unknown_id','observe_timeout','invalid_response','duplicate_marker','wrong_marker','marker_missing','uart_fatal','reset_during_observe'):
            s,rc,r=self.case(case);self.assertEqual(rc,1);self.assertEqual((s.loads,s.observes,s.unloads),(1,1,0));self.assertFalse(r['observe_pass']);self.assertTrue(r['baseline_returned']);self.assertIn('observe_uart_partial',r)
    def test_unknown_id_cache_never_fills_missing_security_as_valid(self):
        s,rc,r=self.case('unknown_id');row=r['observe_uart_partial']['markers'][0];self.assertEqual(row['id'],'abcdef');self.assertEqual(row['valid_mask'],7);self.assertFalse(row['read_validity']['security'])
    def test_reset_seen_before_prompt_waits_fresh_bootbase_without_new_reboot(self):
        s,rc,r=self.case('reset_prompt_delayed');self.assertEqual(rc,1);self.assertIn('wait_fresh_prompt',s.actions);self.assertEqual(s.software,0);self.assertTrue(r['baseline_returned']);self.assertEqual(s.unloads,0)
    def test_unload_or_cease_failure_remains_fail_after_return(self):
        for case in ('unload_failed','cease_failed'):
            s,rc,r=self.case(case);self.assertEqual(rc,1);self.assertTrue(r['observe_pass']);self.assertEqual(s.unloads,1);self.assertTrue(r['baseline_returned'])
    def test_missing_reset_allows_only_one_explicit_software_recovery(self):
        s,rc,r=self.case('no_cleanup_reset');self.assertEqual(rc,1);self.assertEqual(s.software,1);self.assertTrue(r['software_recovery']);self.assertTrue(r['baseline_returned'])
    def test_no_new_prompt_retains_possible_armed_guardian(self):
        s,rc,r=self.case('no_recovery_prompt');self.assertEqual(rc,1);self.assertEqual(s.returns,0);self.assertTrue(r['retain_lease_required']);self.assertTrue(r['guardian_may_remain_armed'])
    def test_crc_error_after_actual_return_does_not_reset_again(self):
        s,rc,r=self.case('return_crc_failed');self.assertEqual(rc,1);self.assertEqual(s.returns,1);self.assertEqual(s.software,0);self.assertTrue(r['baseline_returned']);self.assertFalse(r['guardian_may_remain_armed'])
    def test_return_bootm_is_never_retried(self):
        s,rc,r=self.case('return_bootm_returned');self.assertEqual(rc,1);self.assertEqual(s.returns,1);self.assertEqual(s.software,0);self.assertFalse(r['baseline_returned']);self.assertFalse(r['guardian_may_remain_armed'])
    def test_capture_or_containment_error_cannot_keep_pass(self):
        for case in ('containment_failed','reader_failed'):
            s,rc,r=self.case(case);self.assertEqual(rc,1);self.assertEqual(r['status'],'FAIL_CAPTURE_OR_CONTAINMENT')

class ActualContracts(unittest.TestCase):
    def test_actual_uart_wait_accepts_delayed_marker_without_any_device_action(self):
        uart=Mock(failed=None,reset_times=[]);uart.since.side_effect=[b'',MARK[:40],MARK]
        with patch.object(x.time,'sleep',lambda _:None):self.assertEqual(x.wait_marker(uart,0,0),MARK)
        self.assertEqual(uart.since.call_count,3)
    def test_actual_uart_wait_refuses_timeout_reset_and_fatal(self):
        uart=Mock(failed=None,reset_times=[]);uart.since.return_value=b''
        with patch.object(x.time,'monotonic',side_effect=[0,3]),self.assertRaisesRegex(x.Failure,'observe_marker_deadline'):x.wait_marker(uart,0,0)
        uart.reset_times=[1]
        with self.assertRaisesRegex(x.Failure,'reset_instead_of_observe'):x.wait_marker(uart,0,0)
        uart.reset_times=[];uart.since.return_value=b'Kernel panic\n'
        with self.assertRaisesRegex(x.Failure,'fault_during_observe'):x.wait_marker(uart,0,0)
    def test_actual_ram_watchdog_inspection_requires_kernel350_and_visible_printk(self):
        host=x.Host.__new__(x.Host);host.supervisor='/run/fixture/supervisor'
        row=dict(event='inspect',ready_for_arm=1,device_opened=0,kernel_profile_verified=1,required_kernel_version='#350 @1790006400',control_valid=1,control='00000000')
        host.ssh=lambda cmd:b'7 4 1 7\n' if cmd=='cat /proc/sys/kernel/printk' else json.dumps(row).encode();self.assertEqual(host.inspect_ram()['console_loglevel'],7)
        row['required_kernel_version']='#340 @1790006400'
        with self.assertRaises(x.Failure):host.inspect_ram()
    def test_real_capture_stop_autoboot_accepts_120_rejects_150(self):
        capture=x.ram.Capture.__new__(x.ram.Capture);capture.lock=threading.Lock();capture.total=57;capture.auto_seen={1};capture.auto_count=3
        capture.stop_autoboot(120);self.assertEqual(capture.auto_floor,57);self.assertEqual(capture.auto_count,0);self.assertEqual(capture.auto_seen,set())
        with self.assertRaises(x.Failure):capture.stop_autoboot(150)
    def test_actual_ram_identity_uses_cat_nul_and_exact_kernel350(self):
        host=x.Host.__new__(x.Host);host.plan={'images':{'f340':{'version':'fixture'}}};commands=[]
        row=('boot_id='+RAMBOOT+'\nuts=#350 @1790006400\nrelease=5.10.260-openmitrastar-radiohw\nmarker=F340_WATCHDOG_BASELINE\0\n').encode();host.ssh=lambda cmd:commands.append(cmd) or row
        self.assertEqual(host.identity('ram')['uts'],'#350 @1790006400');self.assertNotIn('tr ',commands[0]);self.assertIn('cat /proc/device-tree/',commands[0])
        host.ssh=lambda cmd:row.replace(b'#350',b'#340')
        with self.assertRaises(x.Failure):host.identity('ram')
    def test_devtmpfs_real_parser_rejects_wrong_or_ambiguous_mount(self):
        host=x.Host.__new__(x.Host)
        for text,ok in [(b'devtmpfs /dev devtmpfs rw,relatime 0 0\n',True),(b'tmpfs /dev tmpfs rw 0 0\n',False),(b'devtmpfs /dev devtmpfs ro 0 0\n',False),(b'',False)]:
            host.ssh=lambda cmd:text
            if ok:self.assertEqual(host.devtmpfs_ready()['filesystem'],'devtmpfs')
            else:
                with self.assertRaises(x.Failure):host.devtmpfs_ready()
    def test_loader_actual_whole_parameter_string_and_no_busybox(self):
        host=x.Host.__new__(x.Host);host.stage_dir='/run/openmitrastar/f356/'+'b'*32;host.module_path=host.stage_dir+'/provider.ko';host.plan={'provider':{'sha256':'a'*64}};calls=[]
        host.capture=lambda kind,command:calls.append((kind,command)) or b'';host.load_provider();text=calls[0][1]
        self.assertEqual(text.count(x.LOADER+' '+host.module_path+" 'allow_hw=1 allow_program=0'"),1);self.assertNotIn('/bin/insmod',text);self.assertIn(x.LOADER_SHA,text);self.assertNotIn('/bin/rmmod',text)
    def test_actual_cli_only_observe_after_readback_of_program_gate(self):
        host=x.Host.__new__(x.Host);host.cli='/run/fixture/journal-cli';host.plan={'cli':{'sha256':'a'*64}};calls=[];host.capture=lambda kind,command:calls.append((kind,command)) or b'';host.observe_provider();text=calls[0][1]
        self.assertIn('allow_program)" = N',text);self.assertTrue(text.endswith('exec /run/fixture/journal-cli observe'));self.assertNotIn(' save',text);self.assertNotIn(' inspect',text)
    def test_actual_capture_timeout_keeps_safe_partial_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            host=x.Host.__new__(x.Host);host.out=Path(directory);host.children=[];host.network_guard=lambda:True;host.ssh_argv=lambda cmd:['fake'];child=Mock(returncode=255);child.poll.side_effect=[None,255];child.communicate.side_effect=[subprocess.TimeoutExpired('fake',20,output=b'load_rc=1\n'),(b'load_rc=1\nPSK=TOPSECRET\n',b'TOPSECRET')]
            with patch.object(x.subprocess,'Popen',return_value=child) as factory,self.assertRaises(x.Failure):host.capture('load','fake')
            self.assertEqual(factory.call_count,1);self.assertEqual(child.kill.call_count,1);saved=(Path(directory)/'load-diagnostic.json').read_text();self.assertNotIn('TOPSECRET',saved);self.assertEqual(json.loads(saved)['fields']['load_rc'],'1')
    def test_bootbase_vocabulary_cannot_program_or_change_persistent_environment(self):
        plan=dict(kernel={'path':'F356-RAM.bin','bytes':1234},images={'f340':{'bytes':5349376}},protected={'parts':[]},bootargs=x.contract.BOOTARGS)
        for cmd in x.vocabulary(plan):self.assertFalse(any(word in cmd for word in ['spi_flash write','spi_flash erase','saveenv','unlock','bootselect','run ']))
        self.assertIn('tftpboot 0x83000000 F356-RAM.bin',x.vocabulary(plan))

class RamTransport(unittest.TestCase):
    def case(self,scenario):
        actions=[]
        def reply(command,*lines):return (command+'\r\n'+'\r\n'.join(lines)+'\r\ntopaz> ').encode()
        class Server:
            def __init__(self,**kwargs):self.closed=False
            def start(self,payload,**kwargs):actions.append('server-start');self.payload=payload
            def finish(self):actions.append('server-finish');return dict(status='PASS_TFTP_SINGLE_TRANSFER')
            def close(self):actions.append('server-close');self.closed=True;return scenario!='server-close-failed'
        class Uart:
            def command(self,command,timeout=15,handoff=False):
                actions.append(command)
                if command.startswith('tftpboot'):
                    n=4095 if scenario=='short-transfer' else 4096;return reply(command,f'Bytes transferred = {n} (0x{n:x})')
                if handoff:return 7
                if command.startswith('printenv '):
                    name=command.split()[1];values={'ipaddr':'192.168.1.90','serverip':'192.168.1.49','bootargs':x.contract.BOOTARGS};return reply(command,name+'='+values[name])
                return reply(command)
        host=Mock();host.servers=[];host.transfer_guard=lambda:True
        host.wait_identity=lambda name,uart,start:dict(boot_id=RAMBOOT,uts='#350 @1790006400')
        with tempfile.TemporaryDirectory(prefix='f356-transport-') as directory:
            root=Path(directory);kernel=root/'F356-RAM.bin';kernel.write_bytes(b'K'*4096)
            plan=dict(kernel={'path':str(kernel),'bytes':4096,'sha256':hashlib.sha256(kernel.read_bytes()).hexdigest(),'crc32':'12345678'},bootargs=x.contract.BOOTARGS)
            with patch.object(x.boot,'ram_crc',lambda *a:'87654321' if scenario=='crc-failed' else '12345678'),patch.object(x.ram,'iminfo',lambda u:actions.append('validated-iminfo')),patch.object(x.ram,'inactive_hardware',lambda u:actions.append('validated-inactive-watchdog')):
                if scenario=='success':identity,receipt=x.boot_ram(Uart(),host,plan,root,Server);self.assertEqual(identity['boot_id'],RAMBOOT)
                else:
                    with self.assertRaises((x.Failure,ValueError,GateFailure)):x.boot_ram(Uart(),host,plan,root,Server)
        self.assertEqual(actions.count('server-start'),1);self.assertGreaterEqual(actions.count('server-close'),1)
        self.assertLessEqual(actions.count('bootm 0x83000000'),1);return actions
    def test_actual_ram_transport_closes_server_checks_ram_then_handoffs_once(self):
        actions=self.case('success');self.assertLess(actions.index('server-close'),actions.index('validated-iminfo'));self.assertLess(actions.index('validated-inactive-watchdog'),actions.index('bootm 0x83000000'));self.assertIn('printenv ipaddr',actions);self.assertIn('printenv serverip',actions);self.assertIn('printenv bootargs',actions)
    def test_actual_ram_transport_failures_never_boot_or_retry(self):
        for scenario in ('short-transfer','crc-failed','server-close-failed'):
            actions=self.case(scenario);self.assertNotIn('bootm 0x83000000',actions)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);a=ap.parse_args();result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__)))
    x.save(a.result,dict(passed=result.wasSuccessful(),tests=result.testsRun,hardware_actions=False,actual_run_function=True,shared_capture_deadline_executed=True));return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
