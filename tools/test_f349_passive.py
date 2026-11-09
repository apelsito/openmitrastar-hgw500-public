"""Offline validation of the actual F349 orchestration; no device/network IO."""
from pathlib import Path
from unittest.mock import patch,Mock
import argparse,copy,json,tempfile,unittest
import f349_protocol as p
import f349_probe_executor as x

BOOT='01234567-89ab-cdef-0123-456789abcdef'
TOKEN='a'*32
PID=1234
def owner_row(token=TOKEN,op=1):
    row=dict(schema='openmitrastar.f340-supervisor-state/v1',peer_verified=True,nonce=token,boot_id=BOOT,owner_pid=PID,owner_start_ticks=123456,phase='',state='idle',op=op,ack_sequence=0,phase_sequence=0,pet_count=0,timeout_reported_seconds=0,last_pet_monotonic_ms=0,phase_deadline_monotonic_ms=0,session_deadline_monotonic_ms=0,error=False,fd_held=False,hardware_arm_confirmed=False,first_pet_confirmed=False)
    if op!=1:
        row.update(state='waiting-phase',ack_sequence=1,pet_count=1,timeout_reported_seconds=8,last_pet_monotonic_ms=1000,phase_deadline_monotonic_ms=6000,session_deadline_monotonic_ms=181000,fd_held=True,hardware_arm_confirmed=True,first_pet_confirmed=True)
    if op in (3,6):row.update(state='phase-active' if op==3 else 'ceased-fd-held',phase_sequence=1,phase=p.PHASE,phase_deadline_monotonic_ms=61000)
    return row
def probe_rows():
    rows={k:'Y' for k in p.PARAMETERS[:4]};rows.update(map_register_value='12975',map_read_count='1',controller_value='128',controller_read_count='1',controller_write_count='0',transaction_provider_ready='N',load_rc='0',snapshot_rc='0',unload_rc='0',module_present='0',boot_id=BOOT,complete='1');return rows
def encode(rows):return ''.join(k+'='+v+'\n' for k,v in rows.items()).encode('ascii')
UART=b'\n'.join([b'[  1.0] OMSPICTRL map-read-begin address=0xe0000004',b'OMSPICTRL control-read-begin address=0xe2000004 map=0x32af',b'OMSPICTRL control-read-done value=0x80 map_reads=1 reads=1 writes=0 provider=0',b'OMSPICTRL released map_reads=1 reads=1 writes=0 provider=0'])+b'\n'

class Validators(unittest.TestCase):
    def test_live_owner_contract_and_safe_projection(self):
        old=p.owner(owner_row(),TOKEN,BOOT,PID);p.idle(old);self.assertNotIn('nonce',old);self.assertNotIn(TOKEN,json.dumps(old))
        for op in (2,3):p.armed(p.owner(owner_row(op=op),TOKEN,BOOT,PID,old),op)
        p.ceased(p.owner(owner_row(op=6),TOKEN,BOOT,PID,old))
    def test_owner_binding_rejects_snapshot_wrong_peer_nonce_boot_and_types(self):
        for key,value in [('peer_verified',False),('nonce','b'*32),('boot_id','other'),('owner_pid',PID+1),('owner_start_ticks',0),('fd_held',0),('phase','unknown'),('schema','wrong')]:
            row=owner_row();row[key]=value
            with self.subTest(key=key),self.assertRaises(p.ProtocolError):p.owner(row,TOKEN,BOOT,PID)
    def test_owner_cannot_change_identity_or_deadlines_after_arm(self):
        old=p.owner(owner_row(),TOKEN,BOOT,PID);row=owner_row(op=3);row['owner_start_ticks']+=1
        with self.assertRaises(p.ProtocolError):p.owner(row,TOKEN,BOOT,PID,old)
        row=p.owner(owner_row(op=3),TOKEN,BOOT,PID);row['phase_deadline_monotonic_ms']=row['last_pet_monotonic_ms']
        with self.assertRaises(p.ProtocolError):p.armed(row,3)
    def test_idle_and_cease_may_not_close_or_adopt_fd(self):
        row=p.owner(owner_row(),TOKEN,BOOT,PID);row['fd_held']=True
        with self.assertRaises(p.ProtocolError):p.idle(row)
        row=p.owner(owner_row(op=6),TOKEN,BOOT,PID);row['fd_held']=False
        with self.assertRaises(p.ProtocolError):p.ceased(row)
    def test_valid_probe_and_four_uart_markers(self):
        observation=p.probe(encode(probe_rows()),BOOT);proof=p.uart(UART,observation)
        self.assertEqual(len(proof['validated_lines']),4);self.assertEqual(observation['control_value'],'00000080')
    def test_zero_c_printf_hex_format(self):
        rows=probe_rows();rows.update(map_register_value='0',controller_value='0');raw=UART.replace(b'map=0x32af',b'map=0').replace(b'value=0x80',b'value=0');p.uart(raw,p.probe(encode(rows),BOOT))
    def test_no_missing_duplicate_extra_or_failed_probe_fields(self):
        for key,value in [('load_rc','1'),('snapshot_rc','1'),('unload_rc','1'),('module_present','1'),('map_read_count','2'),('controller_read_count','0'),('controller_write_count','1'),('transaction_provider_ready','Y'),('map_register_value',str(0x60000000)),('controller_value',str(1<<32)),('execute_read','N'),('boot_id','changed')]:
            rows=probe_rows();rows[key]=value
            with self.subTest(key=key),self.assertRaises(p.ProtocolError):p.probe(encode(rows),BOOT)
        for raw in [encode(probe_rows())+b'load_rc=0\n',encode(probe_rows())+b'extra=1\n',encode(probe_rows()).replace(b'complete=1\n',b'')]:
            with self.assertRaises(p.ProtocolError):p.probe(raw,BOOT)
    def test_uart_missing_reordered_duplicate_mismatch_and_fault(self):
        observation=p.probe(encode(probe_rows()),BOOT)
        for raw in [UART.replace(b'OMSPICTRL released',b'dropped released'),UART+UART,UART.replace(b'value=0x80',b'value=0x81'),b'Kernel panic\n'+UART,b'\n'.join(reversed(UART.splitlines()))]:
            with self.assertRaises(p.ProtocolError):p.uart(raw,observation)

class UartDrain(unittest.TestCase):
    def test_delayed_last_printk_is_received_without_device_action(self):
        uart=Mock(failed=None,reset_times=[])
        uart.since.side_effect=[UART[:UART.index(b'OMSPICTRL released')],UART]
        with patch.object(x.time,'monotonic',side_effect=[0.0,0.0]),patch.object(x.time,'sleep') as sleep:
            result=x.wait_probe_uart(uart,19,p.probe(encode(probe_rows()),BOOT),0)
        self.assertEqual(len(result['validated_lines']),4)
        self.assertEqual(uart.since.call_count,2);sleep.assert_called_once_with(.02)
        self.assertEqual({call[0] for call in uart.mock_calls},{'since'})
    def test_missing_last_printk_has_bounded_host_deadline(self):
        uart=Mock(failed=None,reset_times=[]);uart.since.return_value=b''
        with patch.object(x.time,'monotonic',side_effect=[0.0,2.0]),patch.object(x.time,'sleep') as sleep:
            with self.assertRaisesRegex(x.Failure,'probe_uart_deadline'):
                x.wait_probe_uart(uart,0,p.probe(encode(probe_rows()),BOOT),0)
        sleep.assert_not_called();uart.since.assert_called_once_with(0)
    def test_reader_error_reset_and_fatal_abort_without_wait(self):
        for failed,resets,raw in [('reader-error',[],b''),(None,[1],b''),(None,[],b'Kernel panic')]:
            uart=Mock(failed=failed,reset_times=resets);uart.since.return_value=raw
            with self.subTest(failed=failed,resets=resets),patch.object(x.time,'sleep') as sleep:
                with self.assertRaises((x.Failure,p.ProtocolError)):
                    x.wait_probe_uart(uart,0,p.probe(encode(probe_rows()),BOOT),0)
                sleep.assert_not_called()
    def test_complete_but_mismatched_capture_is_not_retried(self):
        uart=Mock(failed=None,reset_times=[]);uart.since.return_value=UART.replace(b'value=0x80',b'value=0x81')
        with patch.object(x.time,'sleep') as sleep:
            with self.assertRaisesRegex(p.ProtocolError,'uart_sysfs_mismatch'):
                x.wait_probe_uart(uart,0,p.probe(encode(probe_rows()),BOOT),0)
            sleep.assert_not_called();uart.since.assert_called_once_with(0)

class Model:
    def __init__(self,scenario):self.scenario=scenario;self.actions=[];self.data=b'';self.ready=False;self.reset_times=[];self.failed=None;self.token=None;self.arm=False;self.return_calls=0;self.software=0;self.probes=0
    def reset(self):self.reset_times.append(1000);self.data+=b'\nBoot reached stage 13\ntopaz> ';self.ready=True
class FakeHost:
    model=None
    def __init__(self,plan,out):self.s=self.model;self.plan=plan;self.out=out
    def guard(self):return self.s.scenario!='lease_fail'
    def identity(self,name):return dict(boot_id=BOOT,uts='#340',f340='F340_WATCHDOG_BASELINE')
    def initial_binding(self,identity):return self.s.scenario!='nonce_boot_changed'
    def preflight(self):
        if self.s.scenario=='existing_owner':raise x.Failure('supervisor_hash_or_existing_owner')
        return self.watchdog_inactive()
    def watchdog_inactive(self):return dict(control='00000000',ready_for_arm=1,device_opened=0)
    def stage(self,run_id):self.module_path='/fixture/'+run_id+'/probe.ko';self.s.actions.append('stage')
    def launch_owner(self,token):
        self.s.token=token;self.s.actions.append('launch')
        if self.s.scenario.startswith('launch_timeout'):raise x.Failure('ssh_deadline')
        return PID
    def status(self,token):
        self.s.actions.append('status')
        if self.s.scenario=='launch_timeout_missing':raise x.Failure('ssh_failed')
        row=owner_row(token)
        if self.s.scenario=='launch_timeout_armed':row=owner_row(token,3)
        return row
    def arm_begin(self,token):
        self.s.arm=True;self.s.actions.append('arm')
        if self.s.scenario=='arm_response_lost':raise x.Failure('ssh_deadline')
        return [owner_row(token,2),owner_row(token,3)]
    def passive_probe(self,boot):
        self.s.probes+=1;self.s.actions.append('probe');self.s.data+=UART
        if self.s.scenario in ('probe_reset','probe_fault_reset'):
            if self.s.scenario=='probe_fault_reset':self.s.data+=b'Kernel panic\n'
            self.s.reset();raise x.Failure('ssh_failed')
        if self.s.scenario=='probe_timeout':raise x.Failure('ssh_deadline')
        if self.s.scenario=='read_then_reset':self.s.reset()
        rows=probe_rows()
        if self.s.scenario=='probe_missing_read':rows['controller_read_count']='0'
        return encode(rows)
    def cease(self,token):
        self.s.actions.append('cease')
        if self.s.scenario=='cease_failure':raise x.Failure('ssh_failed')
        return owner_row(token,6)
    def clean_unarmed(self):self.s.actions.append('wait_idle_exit');return self.s.scenario!='launch_timeout_missing'
    def cleanup_stage(self):self.s.actions.append('cleanup_stage')
    def reboot_to_prompt(self,uart,software_recovery=False):self.s.software+=1;self.s.actions.append('software_reboot');self.s.reset()
    def contain(self):self.s.actions.append('contain');return self.s.scenario!='containment_failure'
class FakeUart:
    def __init__(self,plan,guard,out):self.s=FakeHost.model;self.guard=guard
    @property
    def reset_times(self):return self.s.reset_times
    @property
    def failed(self):return self.s.failed
    def open(self):self.s.actions.append('uart_open')
    def close(self):return dict(reader_stopped=True,port_closed=True,reader_error='reader_failure' if self.s.scenario=='reader_error' else None)
    def checkpoint(self):return len(self.s.data)
    def since(self,start):return self.s.data[start:]
    def invalidate_prompt(self):self.s.ready=False
    def stop_autoboot(self,seconds):self.s.actions.append('watch_reset')
    def has_prompt(self):return self.s.ready
    def wait_prompt(self,seconds):x.require(self.s.ready,'prompt_missing')

class Pipeline(unittest.TestCase):
    def case(self,scenario):
        s=Model(scenario);FakeHost.model=s
        def wait_reset(uart,count,seconds):
            if scenario in ('no_cleanup_reset','no_recovery_prompt'):return False
            if len(s.reset_times)==count:s.reset()
            return True
        def restore(uart,host,plan,old,out):
            s.return_calls+=1;s.actions.append('return')
            if scenario=='bootm_returned':raise x.Failure('bootm_returned_no_retry')
            return dict(identity={'boot_id':'new'},platform={'checks':27},watchdog={'control':'00000000'},readback_error='flash_crc_mismatch' if scenario=='return_readback_error' else None)
        if scenario=='no_recovery_prompt':
            def reboot(*args,**kwargs):s.software+=1;raise x.Failure('new_prompt_missing')
        else:reboot=FakeHost.reboot_to_prompt
        with tempfile.TemporaryDirectory(prefix='f349-offline-') as directory,patch.object(x,'wait_reset',wait_reset),patch.object(x,'return_f340',restore),patch.object(x,'inactive_hardware',lambda uart:dict(control=0,counter=65535)),patch.object(FakeHost,'reboot_to_prompt',reboot):
            rc=x.run({},Path(directory),FakeHost,FakeUart);r=json.loads((Path(directory)/'result.json').read_text(encoding='ascii'))
            if r.get('probe_uart_artifact'):
                text=Path(r['probe_uart_artifact']['path']).read_text(encoding='ascii');self.assertEqual(text.count('OMSPICTRL'),4)
            self.assertNotIn(s.token or 'token-does-not-exist',json.dumps(r))
        self.assertLessEqual(s.probes,1);self.assertLessEqual(s.return_calls,1);self.assertLessEqual(s.software,1)
        return s,rc,r
    def test_success_has_real_owner_probe_cease_reset_and_return(self):
        s,rc,r=self.case('success');self.assertEqual(rc,0);self.assertEqual(s.probes,1);self.assertTrue(r['probe_read_pass']);self.assertTrue(r['baseline_returned']);self.assertFalse(r['guardian_may_remain_armed']);self.assertFalse(r['software_recovery']);self.assertEqual(s.return_calls,1)
    def test_preconditions_refuse_before_launch_or_probe(self):
        for scenario in ('lease_fail','nonce_boot_changed','existing_owner'):
            s,rc,r=self.case(scenario);self.assertEqual(rc,1);self.assertNotIn('launch',s.actions);self.assertEqual(s.probes,0)
    def test_lost_launch_reply_reconciles_idle_owner_then_waits_expiry(self):
        s,rc,r=self.case('launch_timeout_idle');self.assertEqual(rc,1);self.assertIn('guardian_reconciled',r);self.assertFalse(r['guardian_may_remain_armed']);self.assertIn('wait_idle_exit',s.actions);self.assertIn('cleanup_stage',s.actions);self.assertNotIn('arm',s.actions)
    def test_unreconciled_owner_is_not_killed_or_cleaned(self):
        s,rc,r=self.case('launch_timeout_missing');self.assertEqual(rc,1);self.assertTrue(r['retain_lease_required']);self.assertNotIn('cleanup_stage',s.actions)
    def test_lost_launch_reply_with_live_armed_peer_recovers(self):
        s,rc,r=self.case('launch_timeout_armed');self.assertEqual(rc,1);self.assertTrue(r['baseline_returned']);self.assertFalse(r['guardian_may_remain_armed']);self.assertEqual(s.probes,0)
    def test_arm_response_lost_never_loads_probe(self):
        s,rc,r=self.case('arm_response_lost');self.assertEqual(rc,1);self.assertEqual(s.probes,0);self.assertTrue(r['baseline_returned'])
    def test_fault_reset_timeout_and_missing_reads_are_never_pass(self):
        for scenario in ('probe_reset','probe_fault_reset','probe_timeout','read_then_reset','probe_missing_read'):
            s,rc,r=self.case(scenario);self.assertEqual(rc,1);self.assertTrue(r['baseline_returned']);self.assertFalse(r['probe_read_pass'])
    def test_cease_ack_failure_is_fail_even_after_recovery(self):
        s,rc,r=self.case('cease_failure');self.assertEqual(rc,1);self.assertFalse(r['guardian_cease_confirmed']);self.assertTrue(r['baseline_returned'])
    def test_no_cleanup_reset_uses_one_software_recovery_without_pass(self):
        s,rc,r=self.case('no_cleanup_reset');self.assertEqual(rc,1);self.assertEqual(s.software,1);self.assertTrue(r['software_recovery']);self.assertTrue(r['baseline_returned'])
    def test_no_new_prompt_retains_possible_armed_owner(self):
        s,rc,r=self.case('no_recovery_prompt');self.assertEqual(rc,1);self.assertEqual(s.return_calls,0);self.assertTrue(r['guardian_may_remain_armed']);self.assertTrue(r['retain_lease_required'])
    def test_readback_error_after_verified_return_never_reboots_again(self):
        s,rc,r=self.case('return_readback_error');self.assertEqual(rc,1);self.assertEqual(s.return_calls,1);self.assertEqual(s.software,0);self.assertTrue(r['baseline_returned']);self.assertFalse(r['guardian_may_remain_armed']);self.assertFalse(r['retain_lease_required'])
    def test_bootm_return_is_not_retried_and_inactive_proof_is_preserved(self):
        s,rc,r=self.case('bootm_returned');self.assertEqual(rc,1);self.assertEqual(s.return_calls,1);self.assertEqual(s.software,0);self.assertFalse(r['baseline_returned']);self.assertFalse(r['guardian_may_remain_armed'])
    def test_capture_or_containment_failure_downgrades_success(self):
        for scenario in ('containment_failure','reader_error'):
            s,rc,r=self.case(scenario);self.assertEqual(rc,1);self.assertEqual(r['status'],'FAIL_CAPTURE_OR_CONTAINMENT')

class ActualHelpers(unittest.TestCase):
    def test_preflight_requires_pr_info_console_before_arm_without_setting_it(self):
        host=x.Host.__new__(x.Host);host.plan={'supervisor':{'sha256':'a'*64}};commands=[]
        host.storage_gate=lambda:None;host.watchdog_inactive=lambda:dict(device_opened=0)
        for level in (7,6):
            host.ssh=lambda cmd:commands.append(cmd) or ((str(level)+' 4 1 7\n').encode() if cmd=='cat /proc/sys/kernel/printk' else b'a'*64+b'  /usr/sbin/om-watchdog-supervisor\n')
            if level==7:self.assertEqual(host.preflight()['console_loglevel'],7)
            else:
                with self.assertRaises(x.Failure):host.preflight()
        self.assertFalse(any('>' in cmd for cmd in commands))
    def test_actual_host_probe_emits_one_insmod_and_rmmod_only(self):
        host=x.Host.__new__(x.Host);host.plan={'probe':{'sha256':'a'*64}};host.stage_dir='/run/openmitrastar/f349/'+'b'*32;host.module_path=host.stage_dir+'/probe.ko';captured=[]
        host.ssh=lambda cmd,**kw:captured.append(cmd) or b'';host.passive_probe(BOOT);text=captured[0]
        self.assertEqual(text.count('/bin/insmod '),1);self.assertEqual(text.count('/bin/rmmod '),1)
        self.assertNotIn('/sbin/insmod',text);self.assertNotIn('|| true',text);self.assertIn('execute_read=1',text)
    def test_actual_owner_launch_detaches_hup_and_binds_pid(self):
        host=x.Host.__new__(x.Host);host.stage_dir='/run/openmitrastar/f349/'+'b'*32;captured=[]
        host.ssh=lambda cmd:captured.append(cmd) or b'F349_OWNER_PID=1234\n';self.assertEqual(host.launch_owner(TOKEN),PID)
        self.assertIn("(trap '' HUP; exec /usr/sbin/om-watchdog-supervisor --session",captured[0]);self.assertNotIn('nohup',captured[0])
    def test_arm_begin_share_one_ssh_shell_and_failstop_and(self):
        host=x.Host.__new__(x.Host);captured=[];host.ssh=lambda cmd,**kw:captured.append(cmd) or b'{}\n{}\n';host.arm_begin(TOKEN)
        self.assertEqual(len(captured),1);self.assertIn('1 ARM && ',captured[0]);self.assertIn('1 BEGIN spi-control-read 60000',captured[0])
    def test_readonly_return_preserves_error_after_successful_boot(self):
        calls=[];host=type('H',(),{'platform':lambda *a:dict(checks=27),'watchdog_inactive':lambda *a:dict(control='00000000'),'owner_files_gone':lambda *a:True})()
        with patch.object(x,'inactive_hardware',lambda u:dict(control=0)),patch.object(x.prior,'protected',side_effect=x.Failure('flash_crc_mismatch')),patch.object(x.prior,'boot_written',lambda *a,**kw:calls.append(kw) or {'boot_id':'new'}):
            result=x.return_f340(object(),host,{},BOOT,Path('fixture'))
        self.assertEqual(len(calls),1);self.assertEqual(calls[0],{'prefix_only':True});self.assertEqual(result['readback_error'],'flash_crc_mismatch');self.assertEqual(result['identity']['boot_id'],'new')
    def test_allowlist_only_flash_reads_volatile_bootargs_and_direct_boot(self):
        plan=dict(images={'f340':{'bytes':5349376}},protected={'parts':[{'offset':0,'bytes':0x20000}]},bootargs=x.c.BOOTARGS)
        allowed=x.vocabulary(plan)
        for command in allowed:
            self.assertNotIn('write',command);self.assertNotIn('erase',command);self.assertNotIn('saveenv',command);self.assertNotIn('unlock',command);self.assertNotIn('tftp',command);self.assertNotIn('run ',command)
        self.assertIn('bootm 0x83000000',allowed);self.assertNotIn('bootselect',allowed)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--result',type=Path,required=True);a=ap.parse_args()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__)))
    a.result.write_text(json.dumps(dict(passed=result.wasSuccessful(),tests=result.testsRun,hardware_actions=False,actual_run_function=True),indent=2)+'\n',encoding='ascii')
    return 0 if result.wasSuccessful() else 1
if __name__=='__main__':raise SystemExit(main())
