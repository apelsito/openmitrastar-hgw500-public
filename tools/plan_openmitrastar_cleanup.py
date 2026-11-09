"""Plan a local cleanup while retaining current source and artifact dependencies."""
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone
import hashlib, json, os, re, stat
from cleanup_openmitrastar_storage import ROOT

DEVICE=Path.home()/'.openmitrastar/devices/hgw500bna-qcv2-a2-primary'
FIRMWARE=DEVICE/'firmware'
REPORTS=[ROOT/'outputs/cleanup'/x for x in (
 'openmitrastar-20261022T133122526943Z','openmitrastar-20261022T133255284158Z',
 'openmitrastar-20261022T133338037337Z')]
KEEP_VERSIONS={314,365,367,369,371,372}
KEEP_NAMES={
 'f314-device-bound', 'f365-f364r3-temperature-data-device-bound',
 'f367r9-f365-transition-observation-device-bound',
 'f369-f367r9-store38-quarantine-device-bound',
 'f371-f365-normal-start-compat-device-bound',
 'f372-f371-auc-tqe-observation-device-bound'}
GENERATED_ENDINGS=('.bin','.vmlinux','.uimage','.cpio','.cpio.gz','.cpio.xz',
 '.squashfs','.lzma','.gz','.xz','.tar','.zip','.elf','.o','.ko','.img','.dtb')
SOURCE_ENDINGS={'.c','.h','.s','.asm','.py','.ps1','.sh','.patch','.diff','.dts','.dtsi',
 '.config','.conf','.json','.md','.txt','.env','.yaml','.yml','.symvers','.cmd','.js','.ts',
 '.tsx','.css','.html','.toml','.ini','.csv','.mk','.in','.map','.log'}
def key(path):return os.path.normcase(os.path.abspath(path))
def within(path,parent):return key(path)==key(parent) or key(path).startswith(key(parent)+os.sep)
def sha(path):
 h=hashlib.sha256()
 with open(path,'rb') as f:
  for block in iter(lambda:f.read(4*1024*1024),b''):h.update(block)
 return h.hexdigest()
def version(path):
 hits=re.findall(r'(?:^|[-_/\\])f(\d+)(?=[-_/\\r.]|$)',str(path),re.I)
 return int(hits[0]) if hits else None
def normalize(value):
 value=value.replace('\\','/')
 if value.startswith('/mnt/c/'):value='C:/'+value[7:]
 elif value.startswith('/mnt/d/'):value='D:/'+value[7:]
 if value.startswith(('C:/','D:/','c:/','d:/')):return Path(value)
 if value.startswith(('work/','outputs/','tools/','configs/','packages/','versions/')):return ROOT/value
 return None

def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
 out=ROOT/'outputs/cleanup'/('plan-'+stamp);out.mkdir(parents=True,exist_ok=False)
 rows={}
 for report in REPORTS:
  for row in json.loads((report/'inventory.json').read_text(encoding='utf-8')):rows[key(row['path'])]=row
 protected={}; roots=[]
 def protect(path,reason):
  p=Path(path)
  if p.is_file():protected[key(p)]=dict(path=str(p),reason=reason,bytes=p.stat().st_size)
 def protect_tree(path,reason):
  roots.append(dict(path=str(path),reason=reason))
  for row in rows.values():
   if within(row['path'],path):protect(row['path'],reason)
 def references(data,reason):
  if isinstance(data,dict):
   for k,v in data.items():
    p=normalize(k)
    if p:protect(p,reason)
    references(v,reason)
  elif isinstance(data,list):
   for v in data:references(v,reason)
  elif isinstance(data,str):
   p=normalize(data)
   if p:protect(p,reason)
 for name in KEEP_NAMES:
  folder=FIRMWARE/name;protect_tree(folder,'current firmware, candidate, donor or exact recovery')
  m=folder/'manifest.json'
  if m.is_file():references(json.loads(m.read_text(encoding='utf-8-sig')),'direct immutable dependency of '+name)
 # Preserve the current handoff, all of its exact original source inputs and
 # current validation receipts; no historic source tree is replaced or edited.
 handoff=ROOT/'outputs/handoffs/hgw500-linux510-complete-20261022T125241562008Z'
 source_map=handoff/'package/ORIGINAL_SOURCE_MAP.json'
 references(json.loads(source_map.read_text(encoding='utf-8')),'current technical handoff source input')
 lineage=ROOT/'outputs/handoff/source-lineage-20261022T124550Z/SOURCE_LINEAGE.json'
 references(json.loads(lineage.read_text(encoding='utf-8')),'current source lineage')
 install_plan=ROOT/'outputs/preflight/f372-install-20261021T195348642022Z/plan.json'
 references(json.loads(install_plan.read_text(encoding='utf-8')),'current F372 installation contract pin')
 for path in (ROOT/'outputs/rea/arc700-20261021-r2',ROOT/'outputs/doom',
              ROOT/'work/kernel-port/versions',ROOT/'work/kernel-port/linux-5.10',
              ROOT/'work/kernel-port/initramfs',ROOT/'outputs/flash-backups',
              Path('/workspace/OpenMitraStar'),Path('/workspace/OpenMitraStar-build/f364')):
  protect_tree(path,'active development, source, original evidence or recovery')
 # Work currently running uses this exact generated kernel context.
 active_context=Path('/workspace/OpenMitraStar-build/f363/f363-components-20260921T203041Z')
 protect_tree(active_context,'active compilation kernel context and source')
 for report in REPORTS:
  for summary in json.loads((report/'summary.json').read_text(encoding='utf-8')):
   if 'rea' in summary['root'].lower():continue
 # Original OEM/provider and original verified physical dumps stay intact.
 for p in ROOT.glob('Firmware_para_HGW*'):protect(p,'original OEM provider firmware')
 for row in rows.values():
  p=Path(row['path'])
  if p.suffix.lower() in SOURCE_ENDINGS or p.name.lower() in ('makefile','kconfig','sha256sums','layout.md'):
   protect(p,'source, metadata or small immutable evidence')
 deletes=[]
 for row in rows.values():
  p=Path(row['path']);k=key(p)
  if k in protected:continue
  lower=p.name.lower();reason=None
  if within(p,FIRMWARE):
   name=p.relative_to(FIRMWARE).parts[0]
   if name not in KEEP_NAMES and lower.endswith(GENERATED_ENDINGS):reason='obsolete personalized firmware or generated image asset'
  elif within(p,DEVICE/'analysis'):
   n=version(p.relative_to(DEVICE/'analysis').parts[0])
   if (n is not None and n<367 or 'rejected' in str(p).lower()) and lower.endswith(GENERATED_ENDINGS):reason='obsolete analysis build image assets'
   elif lower.endswith(GENERATED_ENDINGS) and any(x in str(p).lower() for x in ('/a/assets/','/b/assets/','/a/build/','/b/build/','\\a\\assets\\','\\b\\assets\\','\\a\\build\\','\\b\\build\\')):reason='redundant analysis lanes; canonical candidate retained'
  elif within(p,ROOT/'work/mission-state'):
   if lower.endswith(GENERATED_ENDINGS):reason='historical full-image iteration or generated kernel payload'
  elif within(p,ROOT/'work/tftp'):
   if lower.endswith(GENERATED_ENDINGS):reason='historical TFTP firmware staging payload'
  elif within(p,ROOT/'outputs/kernel-port') or within(p,ROOT/'outputs/build') or within(p,ROOT/'outputs/openmitrastar-images'):
   n=version(p)
   if (n is None or n<358) and lower.endswith(GENERATED_ENDINGS):reason='historical generated image build'
  elif within(p,ROOT/'versions'):
   n=version(p)
   if n not in KEEP_VERSIONS and lower.endswith(GENERATED_ENDINGS):reason='obsolete version output binary; source and metadata retained'
  elif within(p,Path('/workspace/OpenMitraStar-build')):
   if lower.endswith(GENERATED_ENDINGS) and 'source' not in p.parts:reason='superseded generated build output; active context and source retained'
  elif within(p,ROOT/'outputs/emulation'):
   if p.suffix.lower()=='.log' and row['bytes']>1024*1024:reason='obsolete verbose QEMU execution log'
  if reason:
   deletes.append({**row,'reason':reason})
 # Large QEMU logs are intentional historical outputs; retain other evidence.
 for row in rows.values():
  p=Path(row['path'])
  if within(p,ROOT/'outputs/emulation') and p.suffix.lower()=='.log' and row['bytes']>1024*1024:
   protected.pop(key(p),None)
   deletes.append({**row,'reason':'obsolete verbose QEMU execution log'})
 deletes=list({key(x['path']):x for x in deletes}.values())
 # Do not classify partition readbacks, factory inputs or OEM data as generated
 # build rubbish, even when they use the same .bin extension.
 sensitive=re.compile(r'(?:^|[/\\_-])(?:mtd[0-6]|calibration|factory|physical|readback|backup|dump|original|oem|store)(?:[/\\_.-]|$)',re.I)
 excluded=[]
 for row in list(deletes):
  if sensitive.search(row['path']):
   deletes.remove(row);excluded.append(row['path']);protect(row['path'],'original data or physical readback preserved conservatively')
 totals=defaultdict(lambda:dict(files=0,bytes=0))
 for row in deletes:
  drive=Path(row['path']).drive.upper();totals[drive]['files']+=1;totals[drive]['bytes']+=row['bytes']
 plan=dict(schema='openmitrastar.local-cleanup/v1',created_utc=stamp,hardware_actions=False,
  authorized_scope='Delete obsolete local versions and duplicates in C and D; preserve OEM, current development, recovery and sources',
  delete=deletes,protected=list(protected.values()),protected_roots=roots,totals=dict(totals),sensitive_excluded=len(excluded),
  limitations=['Historical documents may reference removed generated outputs; retained metadata records history, not artifact availability.',
              'No source tree, private identity, calibration, original physical dump or active build context is selected.'])
 (out/'plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(dict(plan=str(out/'plan.json'),totals=dict(totals),protected=len(protected),reasons=dict(Counter(x['reason'] for x in deletes))),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
