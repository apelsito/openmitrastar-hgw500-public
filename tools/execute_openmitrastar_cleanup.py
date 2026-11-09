"""Execute a reviewed local file cleanup; never follows links or accesses devices."""
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict
import argparse, hashlib, json, os, stat, shutil
from cleanup_openmitrastar_storage import ROOT
from plan_openmitrastar_cleanup import key, within, sha, DEVICE, FIRMWARE, KEEP_NAMES

ALLOWED=[ROOT/'work/mission-state', ROOT/'work/tftp',ROOT/'outputs/kernel-port',
 ROOT/'outputs/build',ROOT/'outputs/openmitrastar-images',ROOT/'outputs/emulation',
 ROOT/'versions',FIRMWARE,DEVICE/'analysis',Path('/workspace/OpenMitraStar-build')]

def checked_path(value):
 p=Path(os.path.abspath(value))
 assert any(within(p,r) and key(p)!=key(r) for r in ALLOWED),'outside allowed roots: '+str(p)
 assert not any(x in str(p).lower() for x in ('gpt2742','gpt-2742','ashkey','samsung')),'unrelated target'
 # Resolve and compare every ancestor: neither a junction nor a symlink may
 # redirect a deletion out of its exact inventoried path.
 for ancestor in [p,*p.parents]:
  st=ancestor.lstat()
  assert not st.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT,'reparse path: '+str(ancestor)
 assert key(p.resolve(strict=True))==key(p),'redirected path'
 assert p.is_file(),'only individual regular files may be removed'
 return p

def retained_baseline(plan):
 pins={}
 source_map=ROOT/'outputs/handoffs/hgw500-linux510-complete-20261022T125241562008Z/package/ORIGINAL_SOURCE_MAP.json'
 for row in json.loads(source_map.read_text()).values():
  path=Path(row['source'])
  if path.is_file():pins[key(path)]=dict(path=str(path),sha256=sha(path),handoff_historical_sha256=row['sha256'])
 install=ROOT/'outputs/preflight/f372-install-20261021T195348642022Z/plan.json'
 for path,digest in json.loads(install.read_text())['sources'].items():
  p=Path(path)
  if p.is_file():pins[key(p)]=dict(path=str(p),sha256=digest)
 for name in KEEP_NAMES:
  for p in (FIRMWARE/name).iterdir():
   if p.is_file():pins[key(p)]=dict(path=str(p),sha256=sha(p))
 oem=ROOT/'Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin'
 pins[key(oem)]=dict(path=str(oem),sha256='f39ed40cc66010287574bdc41c9fc18a6ba7d674f7c0acd7d7d47f8ab633a42f')
 for row in pins.values():assert sha(row['path'])==row['sha256'],'retained input drift: '+row['path']
 assert not {key(x['path']) for x in plan['delete']} & set(pins),'deletion conflicts with retained source pin'
 return list(pins.values())

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--plan',type=Path,required=True);ap.add_argument('--plan-sha256',required=True)
 ap.add_argument('--execute-authorized-cleanup',action='store_true')
 args=ap.parse_args();assert args.execute_authorized_cleanup,'explicit execution flag required'
 assert sha(args.plan)==args.plan_sha256,'plan drift'
 plan=json.loads(args.plan.read_text(encoding='utf-8'))
 assert plan['schema']=='openmitrastar.local-cleanup/v1' and plan['hardware_actions'] is False
 protected={key(x['path']) for x in plan['protected']}
 for row in plan['delete']:
  assert key(row['path']) not in protected,'protected path'
  p=checked_path(row['path']);st=p.stat()
  assert st.st_size==row['bytes'] and st.st_mtime_ns==row['mtime_ns'],'file changed since inventory: '+str(p)
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
 out=ROOT/'outputs/cleanup'/('executed-'+stamp);out.mkdir(parents=True,exist_ok=False)
 pins=retained_baseline(plan)
 (out/'retained-pins.json').write_text(json.dumps(pins,indent=2)+'\n',encoding='utf-8')
 volumes={d:dict(shutil.disk_usage(d+'/')._asdict()) for d in ('C:','D:')}
 print(json.dumps(dict(phase='retained_inputs_verified',pins=len(pins),files=len(plan['delete']),output=str(out))),flush=True)
 # Prehash the full deletion set and recheck all paths before the first unlink.
 selected=[]
 for i,row in enumerate(plan['delete']):
  p=checked_path(row['path']);st=p.stat()
  assert st.st_size==row['bytes'] and st.st_mtime_ns==row['mtime_ns'],'file drift during preparation'
  selected.append({**row,'sha256':sha(p)})
  if i and i%1000==0:print(json.dumps(dict(phase='hashing_deletion_set',files=i)),flush=True)
 (out/'deleted-manifest.json').write_text(json.dumps(selected,indent=2)+'\n',encoding='utf-8')
 totals=defaultdict(lambda:dict(files=0,bytes=0));errors=[]
 journal=out/'execution.jsonl'
 with journal.open('x',encoding='utf-8') as log:
  for i,row in enumerate(selected):
   try:
    p=checked_path(row['path']);st=p.stat()
    assert st.st_size==row['bytes'] and st.st_mtime_ns==row['mtime_ns'],'file drift before unlink'
    if not st.st_mode & stat.S_IWRITE:p.chmod(st.st_mode | stat.S_IWRITE)
    p.unlink();assert not p.exists()
    d=p.drive.upper();totals[d]['files']+=1;totals[d]['bytes']+=row['bytes']
    log.write(json.dumps(dict(path=row['path'],status='DELETED',bytes=row['bytes']))+'\n')
   except Exception as exc:
    errors.append(dict(path=row['path'],error=str(exc)))
    log.write(json.dumps(dict(path=row['path'],status='FAILED',error=str(exc)))+'\n')
    break
   if i and i%1000==0:
    log.flush();print(json.dumps(dict(phase='deleting',files=i,totals=dict(totals))),flush=True)
 retained_errors=[]
 for row in pins:
  if not Path(row['path']).is_file() or sha(row['path'])!=row['sha256']:retained_errors.append(row['path'])
 after={d:dict(shutil.disk_usage(d+'/')._asdict()) for d in volumes}
 result=dict(schema=plan['schema'],status='PASS_LOCAL_CLEANUP' if not errors and not retained_errors else 'PARTIAL_OR_FAILED',
  plan=str(args.plan.resolve()),plan_sha256=args.plan_sha256,hardware_actions=False,
  totals=dict(totals),deleted_files=sum(x['files'] for x in totals.values()),deleted_bytes=sum(x['bytes'] for x in totals.values()),
  retained_pins=len(pins),retained_pins_unchanged=not retained_errors,retained_errors=retained_errors,
  errors=errors,disk_usage_before=volumes,disk_usage_after=after,
  volume_free_delta={d:after[d]['free']-volumes[d]['free'] for d in volumes},
  notes=['Deletion manifest stores paths, hashes and byte counts, not firmware copies.',
         'Physical free-space delta can differ from logical bytes due to compression, hardlinks and concurrent work.'])
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(dict(output=str(out),**result)),flush=True)
 return int(bool(errors or retained_errors))

if __name__=='__main__':raise SystemExit(main())
