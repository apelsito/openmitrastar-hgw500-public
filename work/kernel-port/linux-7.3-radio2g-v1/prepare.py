#!/usr/bin/env python3
"""Three-way port of the exact HGW 5.10 Realtek changes onto upstream7.3.
Creates an isolated source candidate and review artifacts; no hardware access.
"""
from pathlib import Path
import argparse,hashlib,json,subprocess
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
REPO=ROOT/'outputs/rea/movistar-port-20261022T1327175411798Z/realtek-repo'
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 a.output.mkdir(parents=True,exist_ok=False);tree=a.output/'overlay';records=[]
 comparison=json.loads((REPO/'evidence/port-linux-7.3/source-comparison.json').read_text())
 for row in comparison['comparisons']:
  relative=row['path'];new=REPO/'src/linux-7.3'/relative;old=REPO/'original/linux-5.10.260'/relative;base=REPO/'src/baseline-exact'/relative
  assert sha(new.read_bytes())==row['upstream_7_3_sha256'],relative
  assert sha(old.read_bytes())==row['upstream_5_10_sha256'],relative
  assert sha(base.read_bytes())==row['baseline_sha256'],relative
  target=tree/relative;target.parent.mkdir(parents=True,exist_ok=True)
  record={'path':relative,'upstream73_sha256':row['upstream_7_3_sha256'],'hgw510_sha256':row['baseline_sha256'],'changed':row['hgw_changed_from_upstream_5_10']}
  if row['hgw_changed_from_upstream_5_10']:
   result=subprocess.run(['git','merge-file','-p','--diff3','-L','linux7.3','-L','upstream5.10','-L','HGW5.10',str(new),str(old),str(base)],capture_output=True)
   assert result.returncode>=0 and result.returncode<=127,result.stderr.decode()
   target.write_bytes(result.stdout);record['merge_conflicts']=result.returncode
  else:target.write_bytes(new.read_bytes());record['merge_conflicts']=0
  record['candidate_sha256']=sha(target.read_bytes());records.append(record)
 (a.output/'MERGE_RESULT.json').write_text(json.dumps({'schema':'openmitrastar.radio2g73-source-merge/v1','hardware_accessed':False,
  'upstream_commit':'c03c1a14507dfaf8b856c2608f9ac216021fc222','records':records,'conflicted_files':[r['path'] for r in records if r['merge_conflicts']],
  'status':'SOURCE_CONFLICTS_REQUIRE_REVIEW' if any(r['merge_conflicts'] for r in records) else 'SOURCE_MERGED_BUILD_UNRUN'},indent=2)+'\n')
 print(json.dumps({'files':len(records),'changed':sum(r['changed'] for r in records),'conflicts':[(r['path'],r['merge_conflicts']) for r in records if r['merge_conflicts']]},indent=2))
if __name__=='__main__':main()
