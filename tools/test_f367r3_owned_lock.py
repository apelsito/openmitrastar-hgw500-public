"""Delta-only real helper/IPC tests with no rmdir in PATH, plus cleanup failures."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
from f367r3_runtime_contract import overlay
ROOT=Path(__file__).resolve().parents[1];SUP=ROOT/'outputs/kernel-port/f367-supervisor-20260922T115143Z/supervisor-test'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
HARNESS=r"""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,os,shutil,subprocess,sys,tempfile,time
base=Path(sys.argv[1]);binary=sys.argv[2];stage=base/'stage';stage.write_text(stage.read_text().replace('#!/bin/ash\n','#!/bin/sh\n'));stage.chmod(0o755);checks=[]
with tempfile.TemporaryDirectory(prefix='f367r3-lock-') as d:
 root=Path(d);fixture=root/'fixture';state=root/'state';state.mkdir(mode=0o700);owner=root/'owner';owner.mkdir(mode=0o700);bin=root/'bin';bin.mkdir();token='f'*32;lock=state/'ipc-lock'
 for name in ('mkdir','cat','awk','sed','mv','cp','sleep'):
  target=shutil.which(name);assert target;os.symlink(target,bin/name)
 assert shutil.which('rmdir',path=str(bin)) is None
 fields={'/proc/device-tree/openmitrastar,f340-watchdog-baseline':'F340_WATCHDOG_BASELINE','/proc/device-tree/compatible':'mitrastar,hgw-500bna-qcv2','/proc/sys/kernel/random/boot_id':'01234567-89ab-cdef-0123-456789abcdef','/proc/sys/kernel/osrelease':'5.10.260-openmitrastar-radiohw','/proc/sys/kernel/version':'#358 @1790006400','/sys/class/watchdog/watchdog0/identity':'Topaz DesignWare watchdog','/sys/class/watchdog/watchdog0/state':'inactive','/sys/class/watchdog/watchdog0/nowayout':'1','/sys/class/watchdog/watchdog0/f340_control':'00000000','/sys/class/watchdog/watchdog0/f340_counter':'00000000'}
 for n,v in fields.items():p=fixture/n.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(v+'\n')
 for n,v in {'token':token,'sequence':'0','phase':'between-phases'}.items():(state/n).write_text(v+'\n')
 env=dict(os.environ,PATH=str(bin),F340_TEST_ROOT=str(fixture),F340_TEST_STATE=str(owner),F340_TEST_PET_MS='30',F340_TEST_HOLD_MS='20000',OM_F367_STATE=str(state),OM_F367_WDT=binary)
 server=subprocess.Popen([binary,'--session',token,'5400000'],env=env,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
 def raw(*args):return subprocess.run([binary,'--request',token,*map(str,args)],env=env,capture_output=True,text=True,timeout=3)
 def run(*args,script=stage,settings=env):return subprocess.run(['/bin/sh',str(script),*args],env=settings,capture_output=True,text=True,timeout=6)
 def renew():assert raw(1,'HEALTH','ok').returncode==0
 try:
  end=time.monotonic()+3
  while not(owner/'supervisor.sock').exists():assert server.poll() is None;assert time.monotonic()<end;time.sleep(.01)
  assert raw(1,'ARM').returncode==0
  p=run('begin','preamble','30000');assert p.returncode==0 and not lock.exists(),(p.stdout,p.stderr)
  checks.append('BEGIN releases owned lock without rmdir')
  def contender(n):
   for i in range(6):
    p=run('verify','preamble');assert p.returncode==0,(n,i,p.returncode,p.stderr)
  with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(contender,range(2)))
  assert not lock.exists();checks.append('12 concurrent actual HEALTH transactions release the lock')
  # A foreign lock is never adopted or removed after bounded acquisition failure.
  renew();lock.mkdir();(lock/'.owner').write_text('foreign-owner\n');p=run('verify','preamble')
  assert p.returncode==73 and (lock/'.owner').read_text()=='foreign-owner\n';checks.append('foreign owner retained on acquisition failure')
  (lock/'.owner').unlink();lock.rmdir()
  # Unexpected contents introduced after successful IPC make release fail closed.
  wrapper=root/'wdt-wrapper';wrapper.write_text('#!/bin/sh\n"$F367_REAL_WDT" "$@"\nrc=$?\nif [ "$rc" = 0 ] && [ "$1" = --request ] && [ "$4" = HEALTH ]; then\n case "$F367_INJECT" in entry) printf "preserve-me\\n" >"$OM_F367_STATE/ipc-lock/foreign";; owner) printf "other-owner\\n" >"$OM_F367_STATE/ipc-lock/.owner";; esac\nfi\nexit "$rc"\n');wrapper.chmod(0o755)
  for inject,reason in [('entry','unexpected-entry'),('owner','owner-mismatch')]:
   renew();settings=dict(env,OM_F367_WDT=str(wrapper),F367_REAL_WDT=binary,F367_INJECT=inject);p=run('verify','preamble',settings=settings)
   assert p.returncode==74 and 'reason='+reason in p.stderr and lock.exists(),(inject,p.returncode,p.stderr)
   if inject=='entry':assert (lock/'foreign').read_text()=='preserve-me\n';(lock/'foreign').unlink()
   else:assert (lock/'.owner').read_text()=='other-owner\n'
   (lock/'.owner').unlink();lock.rmdir();checks.append(reason+' refuses deletion explicitly')
  # Only the external rm dependency is replaced in this test copy. The cleanup
  # function and actual IPC remain unchanged; production uses verified /bin/rm.
  failing_rm=root/'rm-fails';failing_rm.write_text('#!/bin/sh\nif [ "$1" = -r ]; then exit 17; fi\nexec /bin/rm "$@"\n');failing_rm.chmod(0o755)
  failure_stage=root/'stage-rm-failure';failure_stage.write_text(stage.read_text().replace('/bin/rm',str(failing_rm)));failure_stage.chmod(0o755)
  renew();p=run('verify','preamble',script=failure_stage)
  assert p.returncode==74 and 'reason=empty-directory-remove' in p.stderr and lock.is_dir(),(p.returncode,p.stderr)
  assert not list(lock.iterdir());lock.rmdir();checks.append('rm failure overrides IPC success with explicit exit74')
  renew();foreign=root/'foreign';foreign.mkdir();(foreign/'keep').write_text('untouched');lock.symlink_to(foreign,target_is_directory=True);p=run('verify','preamble')
  assert p.returncode==73 and lock.is_symlink() and (foreign/'keep').read_text()=='untouched';lock.unlink();checks.append('symlink lock never removes target')
  renew();p=run('cease');assert p.returncode==0 and not lock.exists();checks.append('CEASE releases own lock')
 finally:
  server.kill();server.wait(timeout=3)
print(json.dumps({'status':'PASS_OWNED_LOCK_RELEASE_REAL_IPC_WITHOUT_RMDIR','checks':checks,'path_has_rmdir':False,'hardware_backend':'F340_TEST_ONLY','hardware_actions':False,'only_test_owned_directories_removed':True}))
"""
def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/preflight'/('f367r3-owned-lock-'+stamp);out.mkdir(parents=True,exist_ok=False)
 stage=overlay()['usr/sbin/om-f367-stage'];(out/'stage').write_bytes(stage);(out/'harness.py').write_bytes(HARNESS.encode())
 r=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(out/'harness.py'),linux(out),linux(SUP)],capture_output=True,text=True,timeout=35)
 (out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr);result=json.loads(r.stdout) if not r.returncode else {'status':'FAIL','error':r.stderr[-5000:]}
 result.update(schema='openmitrastar.f367r3-owned-lock-test/v1',stage_sha256=hashlib.sha256(stage).hexdigest(),supervisor_test_sha256=sha(SUP),source_sha256=sha(Path(__file__)))
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return r.returncode
if __name__=='__main__':raise SystemExit(main())
