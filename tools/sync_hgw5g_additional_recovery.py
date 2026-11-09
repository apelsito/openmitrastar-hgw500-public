"""Preserve later OEM REA/source evidence in the private repo; new paths only."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
REPO=ROOT/'repos/openmitrastar-hgw500-quantenna-5ghz-driver'
def sha(raw):return hashlib.sha256(raw).hexdigest()
rows=[]
def copy(src,rel):
    dst=REPO/rel;raw=src.read_bytes()
    if dst.exists():
        assert dst.read_bytes()==raw,'existing artifact differs: '+str(dst)
    else:dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(raw)
    rows.append({'path':dst.relative_to(REPO).as_posix(),'source':src.relative_to(ROOT).as_posix(),'bytes':len(raw),'sha256':sha(raw)})
candidate=ROOT/'outputs/rea/named-cca-getters-candidate-20261022T133300Z-r2'
for p in sorted(candidate.rglob('*')):
    if p.is_file() and p.suffix in ('.c','.h','.json','.patch','.md'):
        copy(p,Path('candidates/named-cca-getters-r2')/p.relative_to(candidate))
for p in sorted((ROOT/'tools').glob('*.py')):
    if any(n in p.name for n in ('hgw5g_cca','hgw5g_named','wlan_readonly','oem_wlan','oem_qdrv','oem_abi3')):
        copy(p,Path('tools/integration')/p.name)
for folder in sorted((ROOT/'outputs/rea').iterdir()):
    if folder.is_dir() and (any(n in folder.name for n in ('oem-wlan-case-map','oem-wlan-44-recovered','oem-wlan-missingops','oem-qdrv','named-cca-getters-fixture'))):
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.suffix in ('.json','.md','.c','.txt','.asm'):
                copy(p,Path('evidence')/folder.name/p.name)
(REPO/'manifests/recovery-sync-20261022.json').write_text(json.dumps({'files':rows,'hardware_accessed':False,'all_copies_exact':True,'candidate_status':'SOURCE_AND_ACTUAL_FUNCTION_FIXTURE_PASS_FULL_PAIR_UNBUILT'},indent=2)+'\n',encoding='utf-8')
print(json.dumps({'files':len(rows),'bytes':sum(r['bytes'] for r in rows),'exact':True}))
