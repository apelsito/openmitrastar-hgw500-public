"""Actual supervisor/client processes with only the F340_TEST watchdog backend."""
from pathlib import Path
import argparse,json,os,subprocess,tempfile,time

TOKEN='0123456789abcdef0123456789abcdef'
BOOT='01234567-89ab-cdef-0123-456789abcdef'

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--binary',required=True);ap.add_argument('--result',type=Path,required=True);args=ap.parse_args()
    binary=str(Path(args.binary).resolve());passed=[]
    def run_case(name,fn,mutate=None):
        with tempfile.TemporaryDirectory(prefix='f340-test-') as tmp:
            root=Path(tmp);fixture=root/'root';state=root/'state';state.mkdir(mode=0o700)
            files={
                '/proc/device-tree/openmitrastar,f340-watchdog-baseline':'F340_WATCHDOG_BASELINE',
                '/proc/device-tree/compatible':'mitrastar,hgw-500bna-qcv2',
                '/proc/sys/kernel/random/boot_id':BOOT,
                '/proc/sys/kernel/osrelease':'5.10.260-openmitrastar-radiohw',
                '/proc/sys/kernel/version':'#350 @1790006400',
                '/sys/class/watchdog/watchdog0/identity':'Topaz DesignWare watchdog',
                '/sys/class/watchdog/watchdog0/state':'inactive',
                '/sys/class/watchdog/watchdog0/nowayout':'1',
                '/sys/class/watchdog/watchdog0/f340_control':'00000000',
                '/sys/class/watchdog/watchdog0/f340_counter':'00000000'}
            if mutate:mutate(files)
            for file,value in files.items():
                p=fixture/file.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(value+'\n')
            env=dict(os.environ,F340_TEST_ROOT=str(fixture),F340_TEST_STATE=str(state),F340_TEST_PET_MS='30',F340_TEST_HOLD_MS='1000',F356_TEST_OPEN_TRACE=str(state/'device-opened'))
            server=subprocess.Popen([binary,'--session',TOKEN,'180000'],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            def cli(*command,ok=True,token=TOKEN):
                argv=[binary,'--status',token] if not command else [binary,'--request',token,*map(str,command)]
                p=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=3)
                assert (p.returncode==0)==ok,(name,command,p.returncode,p.stdout,p.stderr)
                return json.loads(p.stdout) if p.stdout else None
            try:
                deadline=time.monotonic()+3
                while not (state/'supervisor.sock').exists():
                    assert server.poll() is None,(name,server.communicate());assert time.monotonic()<deadline;time.sleep(.01)
                fn(cli,server,state,env)
                passed.append(name)
            finally:
                if server.poll() is None:server.terminate()
                try:out,err=server.communicate(timeout=3)
                except subprocess.TimeoutExpired:server.kill();out,err=server.communicate();raise AssertionError('test-mode server containment')
                assert server.returncode==0,(name,server.returncode,out,err)

    def inspect(cli,server,state,env):
        s=cli();assert not s['fd_held'] and not s['hardware_arm_confirmed'] and s['peer_verified']
        p=subprocess.run([binary,'--inspect'],env=env,capture_output=True,text=True,check=True)
        assert not json.loads(p.stdout)['device_opened'] and json.loads(p.stdout)['kernel_profile_verified']==1
    run_case('status-and-inspect-do-not-open',inspect)
    def success(cli,server,state,env):
        s=cli(1,'ARM');assert s['fd_held'] and s['hardware_arm_confirmed'] and s['first_pet_confirmed'] and s['ack_sequence']==1 and s['phase_sequence']==0
        s=cli(1,'BEGIN','module-load',30000);deadline=s['phase_deadline_monotonic_ms'];assert s['phase_sequence']==1
        s=cli(1,'HEALTH','ok');assert s['phase_deadline_monotonic_ms']==deadline
        cli(1,'COMPLETE','module-load');cli(2,'BEGIN','qdrv-core-start',30000)
        s=cli(2,'CEASE');count=s['pet_count'];assert s['state']=='ceased-fd-held' and s['fd_held']
        time.sleep(.12);s=cli();assert s['pet_count']==count and s['fd_held']
        cli(3,'BEGIN','retry',1000,ok=False)
    run_case('arm-phases-cease-holds-fd-no-more-pets',success)
    def wrong_nonce(cli,server,state,env):
        cli(1,'ARM');cli(1,'BEGIN','module-load',30000)
        cli(1,'CEASE',ok=False,token='a'*32);assert cli()['state']=='phase-active';cli(1,'CEASE')
    run_case('wrong-nonce-cannot-change-session',wrong_nonce)
    def deadline(cli,server,state,env):
        cli(1,'ARM');cli(1,'BEGIN','blocked-qdrv',300);time.sleep(.5)
        s=cli();assert s['state']=='ceased-fd-held';count=s['pet_count'];time.sleep(.1);assert cli()['pet_count']==count
    run_case('blocked-phase-stops-local-pets',deadline)
    def unhealthy(cli,server,state,env):
        cli(1,'ARM');cli(1,'BEGIN','module-load',30000);s=cli(1,'HEALTH','fail');assert s['state']=='ceased-fd-held'
    run_case('health-failure-stops-local-pets',unhealthy)
    def duplicate(cli,server,state,env):
        cli(1,'ARM');cli(1,'BEGIN','module-load',30000);cli(1,'BEGIN','module-load',30000,ok=False);assert cli()['state']=='ceased-fd-held'
    run_case('duplicate-phase-cannot-renew',duplicate)
    def second_owner(cli,server,state,env):
        p=subprocess.run([binary,'--session',TOKEN,'180000'],env=env,capture_output=True,timeout=3);assert p.returncode!=0;assert not cli()['fd_held']
    run_case('second-supervisor-refused',second_owner)
    def refused_arm(cli,server,state,env):
        cli(1,'ARM',ok=False);s=cli();assert not s['hardware_arm_confirmed'] and not s['fd_held']
    run_case('wrong-kernel-cannot-arm',refused_arm,lambda x:x.update({'/proc/device-tree/openmitrastar,f340-watchdog-baseline':'F336_WDT_RAM_ONLY'}))
    run_case('already-armed-cannot-adopt',refused_arm,lambda x:x.update({'/sys/class/watchdog/watchdog0/f340_control':'00000001'}))
    def wrong_profile(cli,server,state,env):
        cli(1,'ARM',ok=False);s=cli();assert not s['fd_held'] and not s['hardware_arm_confirmed']
        assert not (state/'device-opened').exists()
        p=subprocess.run([binary,'--inspect'],env=env,capture_output=True,text=True,check=True)
        row=json.loads(p.stdout);assert row['kernel_profile_verified']==0 and row['ready_for_arm']==0 and row['device_opened']==0
    run_case('f340-uts-refused-before-open',wrong_profile,lambda x:x.update({'/proc/sys/kernel/version':'#340 @1790006400'}))
    run_case('wrong-release-refused-before-open',wrong_profile,lambda x:x.update({'/proc/sys/kernel/osrelease':'5.10.260-other'}))
    run_case('wrong-build-timestamp-refused-before-open',wrong_profile,lambda x:x.update({'/proc/sys/kernel/version':'#350 @0'}))
    run_case('missing-uts-refused-before-open',wrong_profile,lambda x:x.pop('/proc/sys/kernel/version'))
    report={'schema':'openmitrastar.f356-supervisor-tests/v1','passed':True,'process_cases':passed,'hardware_actions':False}
    args.result.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':len(passed),'hardware_actions':False}));return 0
if __name__=='__main__':raise SystemExit(main())
