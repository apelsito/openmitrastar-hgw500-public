"""Local Linux processes only, built from F340 with its fake watchdog backend.

Runs actual F349 Host launch/IPC methods, substituting only ssh transport with a
local shell and fixed /run paths with a private fixture. Never opens hardware.
"""
from pathlib import Path
import argparse,ctypes,json,os,signal,subprocess,tempfile,time
import f349_probe_executor as x
import f349_protocol as protocol

BOOT='01234567-89ab-cdef-0123-456789abcdef'
TOKEN='a'*32
def check(ok,code):
    if not ok:raise RuntimeError(code)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--binary',type=Path,required=True);ap.add_argument('--result',type=Path,required=True);args=ap.parse_args()
    binary=args.binary.resolve();check(b'F340_TEST_ROOT' in binary.read_bytes(),'fake_backend_required')
    check(os.geteuid()==0,'local_root_for_real_peercred_test');check(ctypes.CDLL(None).prctl(36,1,0,0,0)==0,'subreaper_required')
    passed=[]
    for scenario in ('detached-hup-arm-cease','launch-response-lost','arm-response-lost','second-owner-refused'):
        with tempfile.TemporaryDirectory(prefix='f349-native-') as directory:
            root=Path(directory);fixture=root/'root';state=root/'state';state.mkdir(mode=0o700);stage=root/'stage';stage.mkdir(mode=0o700)
            files={'/proc/device-tree/openmitrastar,f340-watchdog-baseline':'F340_WATCHDOG_BASELINE','/proc/device-tree/compatible':'mitrastar,hgw-500bna-qcv2','/proc/sys/kernel/random/boot_id':BOOT,'/sys/class/watchdog/watchdog0/identity':'Topaz DesignWare watchdog','/sys/class/watchdog/watchdog0/state':'inactive','/sys/class/watchdog/watchdog0/nowayout':'1','/sys/class/watchdog/watchdog0/f340_control':'00000000','/sys/class/watchdog/watchdog0/f340_counter':'0000ffff'}
            for name,value in files.items():
                path=fixture/name.lstrip('/');path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value+'\n',encoding='ascii')
            env=dict(os.environ,F340_TEST_ROOT=str(fixture),F340_TEST_STATE=str(state),F340_TEST_PET_MS='30',F340_TEST_HOLD_MS='500')
            host=x.Host.__new__(x.Host);host.stage_dir=str(stage);pid=None;transport_loss=False;phase='launch';owner=None;reaped=False
            def local_transport(command,data=b'',timeout=20,**kwargs):
                nonlocal transport_loss
                command=command.replace(x.SUPERVISOR,str(binary)).replace('/run/openmitrastar/watchdog',str(state))
                run=subprocess.run(['sh','-c',command],input=data,env=env,capture_output=True,timeout=timeout)
                check(run.returncode==0 and not run.stderr,'local_cli_failed')
                lose=(scenario=='launch-response-lost' and 'F349_OWNER_PID' in command) or (scenario=='arm-response-lost' and '1 ARM &&' in command)
                if lose and not transport_loss:transport_loss=True;raise x.Failure('ssh_deadline')
                return run.stdout
            host.ssh=local_transport
            try:
                try:pid=host.launch_owner(TOKEN)
                except x.Failure:check(scenario=='launch-response-lost','unexpected_launch_failure')
                deadline=time.monotonic()+3
                while not (state/'supervisor.sock').exists():check(time.monotonic()<deadline,'socket_deadline');time.sleep(.01)
                raw=host.status(TOKEN);actual=raw['owner_pid'];owner=protocol.owner(raw,TOKEN,BOOT,actual)
                if pid is not None:check(pid==actual,'launched_pid_mismatch')
                pid=actual;protocol.idle(owner)
                snapshot=json.loads((state/'state.json').read_text(encoding='ascii'))
                try:protocol.owner(snapshot,TOKEN,BOOT,pid);raise RuntimeError('snapshot_accepted')
                except protocol.ProtocolError:pass
                os.kill(pid,signal.SIGHUP);time.sleep(.05);protocol.idle(protocol.owner(host.status(TOKEN),TOKEN,BOOT,pid,owner))
                if scenario=='launch-response-lost':
                    # Test-only process cleanup: production waits for idle expiry.
                    check(transport_loss and not owner['fd_held'],'lost_reply_owner_not_idle');os.kill(pid,signal.SIGTERM)
                else:
                    if scenario=='second-owner-refused':
                        second=subprocess.run([str(binary),'--session',TOKEN,'180000'],env=env,capture_output=True,timeout=3);check(second.returncode!=0,'second_owner_accepted')
                    phase='arm'
                    try:
                        arm,begin=host.arm_begin(TOKEN);protocol.armed(protocol.owner(arm,TOKEN,BOOT,pid,owner),2);protocol.armed(protocol.owner(begin,TOKEN,BOOT,pid,owner),3)
                    except x.Failure:check(scenario=='arm-response-lost','unexpected_arm_failure')
                    current=protocol.owner(host.status(TOKEN),TOKEN,BOOT,pid,owner);check(current['state']=='phase-active' and current['fd_held'] and current['hardware_arm_confirmed'],'actual_owner_not_armed')
                    wrong=subprocess.run([str(binary),'--status','b'*32],env=env,capture_output=True,timeout=3);check(wrong.returncode!=0,'wrong_nonce_accepted')
                    ceased=protocol.owner(host.cease(TOKEN),TOKEN,BOOT,pid,owner);protocol.ceased(ceased)
                    time.sleep(.12);held=protocol.owner(host.status(TOKEN),TOKEN,BOOT,pid,owner);check(held['state']=='ceased-fd-held' and held['fd_held'] and held['pet_count']==ceased['pet_count'],'cease_did_not_hold_fd_without_pet')
                deadline=time.monotonic()+3
                while time.monotonic()<deadline:
                    found,status=os.waitpid(pid,os.WNOHANG)
                    if found:check(os.waitstatus_to_exitcode(status)==0,'fake_owner_exit');reaped=True;break
                    time.sleep(.01)
                check(reaped and not (state/'owner.lock').exists() and not (state/'supervisor.sock').exists(),'fake_owner_containment')
                passed.append(scenario)
            finally:
                if pid is None and (state/'owner.lock').exists():pid=int((state/'owner.lock').read_text().split()[0])
                if pid and not reaped:
                    # Only F340_TEST is accepted above; no production owner here.
                    try:os.kill(pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    deadline=time.monotonic()+3
                    while time.monotonic()<deadline:
                        try:found,status=os.waitpid(pid,os.WNOHANG)
                        except ChildProcessError:found=pid
                        if found:reaped=True;break
                        time.sleep(.01)
                    if not reaped:os.kill(pid,signal.SIGKILL);os.waitpid(pid,0);raise RuntimeError('fake_owner_cleanup_timeout')
    report=dict(schema='openmitrastar.f349-native-owner-tests/v1',passed=True,cases=passed,hardware_actions=False,watchdog_backend='F340_TEST',real_unix_peer_credentials=True,actual_f349_host_methods=True,production_owner_killed=False)
    args.result.write_text(json.dumps(report,indent=2)+'\n',encoding='ascii');print(json.dumps(dict(passed=len(passed),hardware_actions=False)))
if __name__=='__main__':main()
