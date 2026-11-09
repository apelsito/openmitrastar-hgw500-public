"""Append qualified seven-entry and later source-only branches to private repo."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1];REPO=ROOT/'repos/openmitrastar-hgw500-quantenna-5ghz-driver'
rows=[]
def copy(p,rel):
    raw=p.read_bytes();dest=REPO/rel
    if dest.exists():assert dest.read_bytes()==raw
    else:dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
    rows.append({'path':dest.relative_to(REPO).as_posix(),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'source':p.relative_to(ROOT).as_posix()})
for name in ('build_hgw5g_seven_getter_module_pair.py','qualify_hgw5g_seven_getter_module_pair.py','test_qualify_hgw5g_seven_getter_module_pair.py','prepare_hgw5g_devmode_and_unsupported.py','test_hgw5g_devmode_candidate.py','prepare_hgw5g_nac_getter_prototype.py','test_hgw5g_nac_getter_prototype.py'):
    p=ROOT/'tools'/name
    if p.exists():copy(p,Path('tools/integration')/name)
for name in ('driver5g-ops-20261022-seven-module-pair-r2','driver5g-ops-20261022-seven-pair-qualification-r5','driver5g-ops-20261022-seven-pair-fault-tests-r1','devmode-unsupported-fixture-20261022T141100Z-r1','nac-getter-fixture-20261022T141600Z-r1','maxbw-aliases-fixture-20261022T143600Z-r1'):
    folder=ROOT/'outputs/rea'/name
    if folder.exists():
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.suffix in ('.json','.md','.c','.txt'):copy(p,Path('evidence')/name/p.name)
for name in ('devmode-unsupported-candidate-20261022T141000Z-r1','nac-getter-prototype-20261022T141500Z-r1','maxbw-aliases-candidate-20261022T143500Z-r1'):
    folder=ROOT/'outputs/rea'/name
    if folder.exists():
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.suffix in ('.c','.h','.json','.patch','.md'):copy(p,Path('candidates')/name/p.name)
modules=ROOT/'outputs/rea/driver5g-ops-20261022-seven-module-pair-r2/a'
for component in ('qdrv','wlan'):
    copy(modules/component/(component+'.ko'),Path('local-only/modules')/('seven-'+component+'.ko'))
(REPO/'manifests/recovery-seven-pair-sync-20261022.json').write_text(json.dumps({'files':rows,'all_copies_exact':True,'hardware_accessed':False},indent=2)+'\n',encoding='utf-8')
print(json.dumps({'files':len(rows),'bytes':sum(r['bytes'] for r in rows)}))
