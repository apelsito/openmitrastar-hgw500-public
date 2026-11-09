"""Execute the real pre-module native preamble against real IPCv2, with slow local hashes."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
import f367_runtime_contract as old
import f367r2_runtime_contract as new
ROOT=Path(__file__).resolve().parents[1]
BASE=Path('/workspace/OpenMitraStar-build/f366/baseline-unused')
BASE=Path('/workspace/OpenMitraStar-build/f366/f366-components-20260922T093407Z/baseline-rootfs')
COMP=Path('/workspace/OpenMitraStar-build/f367-functional/f367-functional-components-20260922T120217Z/result.json')
SUP=ROOT/'outputs/kernel-port/f367-supervisor-20260922T115143Z/supervisor-test'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
HARNESS=r"""
from pathlib import Path
import hashlib,json,os,signal,subprocess,sys,tempfile,threading,time,shutil
base=Path(sys.argv[1]);binary=sys.argv[2];inputs=Path(sys.argv[3]);rows=[]
for version,delay,expect in [('old',6,'lease'),('old',0,'pass'),('new',6,'pass'),('new',None,'keeper_missing')]:
 with tempfile.TemporaryDirectory(prefix='f367-real-preamble-') as temp:
  root=Path(temp);state=root/'owner-state';state.mkdir(mode=0o700);owner=root/'wdt';owner.mkdir(mode=0o700);hardware=root/'wdt-fixture';helpers=base/version/'helpers';bindir=root/'bin';bindir.mkdir();radio=root/'radio';origin=root/'origin';origin.mkdir();cal=root/'cal';cal.mkdir();modules=root/'modules';modules.mkdir();share=root/'share';share.mkdir();sysroot=root/'sys';proc=root/'proc';power=root/'power';power.mkdir()
  token='0123456789abcdef0123456789abcdef'
  for n,v in {'token':token,'sequence':'0','phase':'between-phases'}.items():(state/n).write_text(v+'\n')
  fields={'/proc/device-tree/openmitrastar,f340-watchdog-baseline':'F340_WATCHDOG_BASELINE','/proc/device-tree/compatible':'mitrastar,hgw-500bna-qcv2','/proc/sys/kernel/random/boot_id':'01234567-89ab-cdef-0123-456789abcdef','/proc/sys/kernel/osrelease':'5.10.260-openmitrastar-radiohw','/proc/sys/kernel/version':'#358 @1790006400','/sys/class/watchdog/watchdog0/identity':'Topaz DesignWare watchdog','/sys/class/watchdog/watchdog0/state':'inactive','/sys/class/watchdog/watchdog0/nowayout':'1','/sys/class/watchdog/watchdog0/f340_control':'00000000','/sys/class/watchdog/watchdog0/f340_counter':'00000000'}
  for n,v in fields.items():p=hardware/n.lstrip('/');p.parent.mkdir(parents=True,exist_ok=True);p.write_text(v+'\n')
  for n in ('class/net/eth0','class/net/wlan0','class/net/br0/brif/eth0','class/net/br0/brif/wlan0','module/hwmon','module/temp_sens'):(sysroot/n).mkdir(parents=True,exist_ok=True)
  (proc/'device-tree').mkdir(parents=True);(proc/'device-tree/compatible').write_text('mitrastar,hgw-500bna-qcv2\n');(proc/'modules').write_text('')
  (origin/'ready').write_text('jffs2=validated\nsecrets=redacted\n');(origin/'runtime.conf').write_text('ORIGIN_MTD5_IMPORTED=1\nRADIO5G_SSID=FixtureOnly\n');(origin/'wireless_conf.txt').write_text('region=es&bw=80')
  (cal/'ready').write_text('schema=openmitrastar.qtn-calibration/v1\nsource=mtd1+mtd2-redundant-readonly\nprimary_crc=valid\nbackup_crc=valid\ncopies=match\nfiles_mode=0600\nflash_writes=0\n')
  for n in ('rx_iq.cal','dc_iq.cal','pdetector.cal'):(cal/n).write_text('synthetic-fixture\n');(cal/n).chmod(0o600)
  (root/'psk').write_text('FixtureOnly123\n');(root/'psk').chmod(0o600);(root/'mac').write_text('02:00:00:00:00:01\n');(root/'mac').chmod(0o600)
  for p in (inputs/'modules').iterdir():shutil.copyfile(p,modules/p.name)
  shutil.copyfile(inputs/'contract',share/'driver-contract.env');shutil.copyfile(inputs/'power',power/'tx_power_QSR1000_es.txt');shutil.copyfile(inputs/'loader',bindir/'loader');(bindir/'loader').chmod(0o755)
  (root/'beacon').write_text('Q3_RADIO5_BEACON_LIFETIME=1\n')
  catalog=[]
  for i in range(3):p=root/f'slow-{i}';p.write_text('synthetic read-only payload');catalog.append(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+str(p))
  (share/'artifacts.sha256').write_text('\n'.join(catalog)+'\n')
  def executable(n,text):p=bindir/n;p.write_text(text);p.chmod(0o755);return str(p)
  executable('uname','#!/bin/sh\nprintf "5.10.260-openmitrastar-radiohw\\n"\n')
  executable('sha256sum','#!/bin/sh\ncase "$1" in */slow-*) sleep 3;; esac\nexec /usr/bin/sha256sum "$@"\n')
  temphelper=executable('temperature','#!/bin/sh\n[ "$1" = require-module ]\n')
  env=dict(os.environ,F340_TEST_ROOT=str(hardware),F340_TEST_STATE=str(owner),F340_TEST_PET_MS='30',F340_TEST_HOLD_MS='10000',OM_F367_STATE=str(state),OM_F367_WDT=binary,OM_F367_STAGE=str(helpers/'usr/sbin/om-f367-stage'),OM_F367_STATUS=str(helpers/'usr/sbin/om-f367-status'),OM_F367_COMMON=str(helpers/'usr/libexec/openmitrastar/f367-shell-common'),OM_F367_KERNEL_STATE=str(root/'absent-kernel'),OM_F367_PROVIDER=str(root/'absent-provider'),OM_F367_KERNEL_CONTROL=str(root/'absent-control'),OM_F367_CONSOLE=str(root/'keeper-console'),OM_RADIO5_STATE=str(radio),OM_RADIO5_MODULE_DIR=str(modules),OM_RADIO5_SHARE=str(share),OM_RADIO5_ORIGIN=str(origin),OM_RADIO5_PSK_FILE=str(root/'psk'),OM_RADIO5_MAC_FILE=str(root/'mac'),OM_RADIO5_CALIBRATION=str(cal),OM_RADIO5_LOADER=str(bindir/'loader'),OM_RADIO5_SYS_ROOT=str(sysroot),OM_RADIO5_LOG_PATH=str(root/'native-console'),OM_RADIO5_STOP='/bin/true',OM_RADIO5_BEACON_LIFETIME_FEATURE=str(root/'beacon'),F367_FIX_BIN=str(bindir))
  for p in helpers.rglob('*'):
   if p.is_file():p.write_text(p.read_text().replace('#!/bin/ash\n','#!/bin/sh\n',1));p.chmod(0o755)
  native=(base/version/'prefix').read_text().replace('/sys/',str(sysroot)+'/').replace('/proc/',str(proc)+'/').replace('/etc/power_tables/',str(power)+'/').replace('/usr/sbin/om-f367-stage',str(helpers/'usr/sbin/om-f367-stage')).replace('/usr/sbin/om-temperature-f363',temphelper)
  native=native.replace('PATH=/sbin:/bin:/usr/sbin:/usr/bin','PATH="$F367_FIX_BIN:/sbin:/bin:/usr/sbin:/usr/bin"')
  prefix=root/'prefix.sh';prefix.write_text(native)
  keeper=[];delayed=None
  stdout=(root/'owner.stdout').open('w');stderr=(root/'owner.stderr').open('w')
  server=subprocess.Popen([binary,'--session',token,'5400000'],env=env,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr)
  def cli(*args):return subprocess.run([binary,'--request',token,*map(str,args)],env=env,capture_output=True,text=True,timeout=3)
  def status():return json.loads(subprocess.run([binary,'--status',token],env=env,capture_output=True,text=True,check=True,timeout=3).stdout)
  try:
   end=time.monotonic()+4
   while not(owner/'supervisor.sock').exists():assert server.poll() is None;assert time.monotonic()<end;time.sleep(.01)
   assert cli(1,'ARM').returncode==0
   phase='module-load' if version=='old' else 'preamble'
   begun=subprocess.run(['sh',str(helpers/'usr/sbin/om-f367-stage'),'begin',phase,'30000'],env=env,capture_output=True,text=True,check=True,timeout=3)
   initial=status();before=time.monotonic()
   if delay is not None:
    def launch():
     time.sleep(delay)
     log=(root/'keeper.log').open('w');keeper.append((subprocess.Popen(['sh',str(helpers/'usr/sbin/om-f367-keeper')],env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log),log))
    delayed=threading.Thread(target=launch);delayed.start()
   completed=subprocess.run(['sh',str(prefix)],env=env,capture_output=True,text=True,timeout=25)
   final=status();elapsed=time.monotonic()-before;console=(root/'native-console').read_text() if(root/'native-console').exists() else ''
   if expect=='pass':assert completed.returncode==0 and 'PREFIX_ADMISSION_PASS' in completed.stdout,(version,completed.returncode,completed.stdout,completed.stderr,console)
   else:assert completed.returncode!=0 and 'PREFIX_ADMISSION_PASS' not in completed.stdout,(version,completed.stdout)
   if expect=='lease':
    assert final['state']=='ceased-fd-held' and final['phase']=='module-load' and final['phase_sequence']==1
    now=int(time.monotonic()*1000);assert final['health_deadline_monotonic_ms']<now<final['phase_deadline_monotonic_ms']
   if expect=='keeper_missing':assert 'keeper-missing' in completed.stderr and final['state']=='phase-active' and final['phase']=='preamble'
   assert final['session_deadline_monotonic_ms']==initial['session_deadline_monotonic_ms']
   rows.append({'revision':version,'keeper_delay_seconds':delay,'expected':expect,'exit_code':completed.returncode,'elapsed_seconds':round(elapsed,3),'owner_state':final['state'],'owner_phase':final['phase'],'owner_phase_sequence':final['phase_sequence'],'phase_deadline_unchanged_in_same_phase':final['phase']!=initial['phase'] or final['phase_deadline_monotonic_ms']==initial['phase_deadline_monotonic_ms'],'total_deadline_unchanged':True,'stdout':completed.stdout[-1800:],'stderr':completed.stderr[-1800:],'native_console':console[-500:],'module_loads':0})
  finally:
   if delayed:delayed.join(timeout=8)
   (state/'stopping').touch()
   for process,log in keeper:
    if process.poll() is None:process.terminate()
    try:process.wait(timeout=3)
    except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
    log.close()
   if server.poll() is None:server.terminate()
   try:server.wait(timeout=2)
   except subprocess.TimeoutExpired:server.kill();server.wait(timeout=3)
   stdout.close();stderr.close()
print(json.dumps({'status':'PASS_REAL_PREAMBLE_AND_IPCV2_PROTECTION','cases':rows,'hardware_backend':'F340_TEST_ONLY','preamble':'actual sealed/native-derived prefix through first module guard; external reads use explicit local fixtures','hardware_actions':False,'physical_keeper_failure_cause_uniquely_proven':False}))
"""
def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'outputs/preflight'/('f367r2-preamble-'+stamp);out.mkdir(parents=True,exist_ok=False)
 c=json.loads(COMP.read_text());old_hash=sha(BASE/'lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko');donor=(BASE/'usr/sbin/om-radio5-start').read_bytes();source_hashes={}
 for name,module in [('old',old),('new',new)]:
  body=module.native_start(donor,old_hash,c['artifacts']['qdrv']['sha256']);source_hashes[name]=hashlib.sha256(body).hexdigest()
  if name=='old':assert source_hashes[name]=='b2a1f2d7d0fa225cff018478084711ebf54d533db6faa8fbf136c98f8f46b271'
  (out/name).mkdir();cut=body.index(b'load_module qtn_pm_qos_compat.ko');(out/name/'prefix').write_bytes(body[:cut]+b"printf 'PREFIX_ADMISSION_PASS hardware_actions=0\\n'\nexit 0\n")
  for path,data in module.overlay().items():p=out/name/'helpers'/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)
 inputs=out/'inputs';(inputs/'modules').mkdir(parents=True)
 for name in ('wlan','board_compat','switch_emac','switch_tqe'):src=BASE/'lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g'/(name+'.ko');(inputs/'modules'/(name+'.ko')).write_bytes(src.read_bytes())
 for key,name in [('qdrv','qdrv.ko'),('provider','qtn_radar_f367.ko')]:(inputs/'modules'/name).write_bytes(Path(c['artifacts'][key]['path']).read_bytes())
 (inputs/'power').write_bytes((BASE/'etc/power_tables/tx_power_QSR1000_es.txt').read_bytes());(inputs/'loader').write_bytes((BASE/'usr/sbin/ram-insmod-qtn').read_bytes())
 contract=(BASE/'usr/share/openmitrastar/radio5g/driver-contract.env').read_text().splitlines();contract=[('QDRV_SHA256='+c['artifacts']['qdrv']['sha256']) if x.startswith('QDRV_SHA256=') else x for x in contract];contract+=['RADAR_F367_SHA256='+c['artifacts']['provider']['sha256']];(inputs/'contract').write_bytes(('\n'.join(contract)+'\n').encode())
 (out/'harness.py').write_bytes(HARNESS.encode());print(json.dumps({'started':str(out),'hardware_actions':False}),flush=True)
 r=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','python3',linux(out/'harness.py'),linux(out),linux(SUP),linux(inputs)],capture_output=True,text=True,timeout=80)
 (out/'stdout').write_text(r.stdout);(out/'stderr').write_text(r.stderr)
 result=json.loads(r.stdout) if not r.returncode else {'status':'FAIL','error':r.stderr[-6000:]}
 result.update(schema='openmitrastar.f367r2-preamble-test/v1',native_sha256=source_hashes,supervisor_test_sha256=sha(SUP),source_pins={str(p):sha(p) for p in (Path(__file__),ROOT/'tools/f367r2_runtime_contract.py')},helpers={n:hashlib.sha256(b).hexdigest() for n,b in new.overlay().items()})
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return r.returncode
if __name__=='__main__':raise SystemExit(main())
