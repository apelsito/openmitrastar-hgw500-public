"""Remove verified exact duplicates from historic handoffs and extraction caches."""
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime, timezone
import argparse, hashlib, json, os, stat, shutil, zipfile
from cleanup_openmitrastar_storage import ROOT,inventory
from plan_openmitrastar_cleanup import key,within,sha

REPORTS=['openmitrastar-20261022T133122526943Z','openmitrastar-20261022T133255284158Z',
 'openmitrastar-20261022T133338037337Z','openmitrastar-20261022T134018162381Z',
 'openmitrastar-20261022T134145557735Z','openmitrastar-20261022T134516998618Z']
CURRENT=ROOT/'outputs/handoffs/hgw500-linux510-complete-20261022T125241562008Z'
LOCAL=ROOT/'.codex_tmp'
TEMP=Path.home()/'AppData/Local/Temp/qtn-research-20260819'
SCOPES=[ROOT/'outputs/handoffs',LOCAL,TEMP,ROOT/'work/tftp',ROOT/'outputs/emulation']

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--execute',action='store_true');a=ap.parse_args()
 out=ROOT/'outputs/cleanup'/('duplicates-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
 out.mkdir(parents=True,exist_ok=False)
 rows={}
 for name in REPORTS:
  for row in json.loads((ROOT/'outputs/cleanup'/name/'inventory.json').read_text(encoding='utf-8')):
   p=Path(row['path'])
   if p.is_file():rows[key(p)]=row
 protected=set()
 finalpins=ROOT/'outputs/cleanup/executed-20261022T134114956984Z/retained-pins.json'
 for row in json.loads(finalpins.read_text()):protected.add(key(row['path']))
 for row in json.loads((ROOT/'outputs/cleanup/plan-20261022T133713967430Z/plan-reviewed-v2.json').read_text())['protected']:
  if row['reason'] not in ('source, metadata or small immutable evidence','original data or physical readback preserved conservatively'):
   protected.add(key(row['path']))
 candidates=[];buckets=defaultdict(list)
 for row in rows.values():
  p=Path(row['path'])
  if within(p,CURRENT):continue
  candidate=any(within(p,scope) for scope in SCOPES) and key(p) not in protected
  # Originals, recovery/readbacks, GPL repositories and active work are excluded.
  if any(word in str(p).lower() for word in ('calibration','recovery','privatekey','known_hosts','.git','vendor/legacy-gpl')):candidate=False
  if candidate:candidates.append(row)
  else:buckets[row['bytes']].append(row)
 # Current handoff files offer canonical identical content but retain its ZIP.
 for row in rows.values():
  if within(row['path'],CURRENT):buckets[row['bytes']].append(row)
 hashes={};deletes=[]
 def digest(row):
  k=key(row['path'])
  if k not in hashes:hashes[k]=sha(row['path'])
  return hashes[k]
 for i,row in enumerate(sorted(candidates,key=lambda r:-r['bytes'])):
  p=Path(row['path']);st=p.stat()
  if st.st_size!=row['bytes'] or st.st_mtime_ns!=row['mtime_ns']:continue
  same=buckets.get(row['bytes'],[])
  if not same:continue
  h=digest(row);canonical=None
  # Try same basename first to avoid reading unrelated large files.
  for ref in sorted(same,key=lambda r:(Path(r['path']).name!=p.name,not within(r['path'],ROOT/'work'),r['path'])):
   if key(ref['path'])==key(p):continue
   if digest(ref)==h:canonical=ref;break
  if canonical:deletes.append({**row,'sha256':h,'canonical':canonical['path'],'reason':'verified exact duplicate; canonical file retained'})
  else:buckets[row['bytes']].append(row)
  if i and i%1000==0:print(json.dumps(dict(phase='comparing_exact_duplicates',examined=i,duplicates=len(deletes))),flush=True)
 plan=dict(schema='openmitrastar.exact-duplicates/v1',hardware_actions=False,delete=deletes,
  bytes=sum(x['bytes'] for x in deletes),files=len(deletes),sources_preserved='Every deletion has a retained equal SHA-256 canonical file')
 (out/'plan.json').write_text(json.dumps(plan,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(dict(output=str(out),phase='plan_ready',files=plan['files'],bytes=plan['bytes'])),flush=True)
 if not a.execute:return
 before={d:shutil.disk_usage(d+'/').free for d in ('C:','D:')};deleted=[];errors=[]
 with (out/'execution.jsonl').open('x',encoding='utf-8') as journal:
  for row in deletes:
   p=Path(row['path']);canonical=Path(row['canonical'])
   try:
    assert any(within(p,scope) and key(p)!=key(scope) for scope in SCOPES)
    assert key(p) not in protected and not within(p,CURRENT)
    for ancestor in [p,*p.parents]:assert not ancestor.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT,'link traversal'
    assert key(p.resolve(strict=True))==key(p)
    assert p.stat().st_size==row['bytes'] and sha(p)==sha(canonical)==row['sha256'],'duplicate drift'
    mode=p.stat().st_mode
    if not mode & stat.S_IWRITE:p.chmod(mode|stat.S_IWRITE)
    p.unlink();deleted.append(row);journal.write(json.dumps(dict(path=row['path'],canonical=row['canonical'],bytes=row['bytes'],status='DELETED'))+'\n')
   except Exception as exc:
    errors.append(dict(path=row['path'],error=str(exc)));break
  journal.flush()
 result=dict(schema=plan['schema'],status='PASS_EXACT_DUPLICATES_REMOVED' if not errors else 'PARTIAL',
  files=len(deleted),bytes=sum(x['bytes'] for x in deleted),errors=errors,
  volumes={d:dict(free_before=before[d],free_after=shutil.disk_usage(d+'/').free) for d in before},hardware_actions=False)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(dict(output=str(out),**result)),flush=True)

if __name__=='__main__':main()
