"""Preserve qualified32, bounded467 and recovered481/466/468 source/evidence."""
from pathlib import Path
import hashlib
import json
from preserve_hgw5g_progress_20261022_r13 import ROOT, REPO, ROWS, SOURCE_EXT, EVIDENCE_EXT, copy


def main():
    manifest=REPO/'manifests/preservation-checkpoint-20261022-consolidated32-cores-r1.json'
    assert not manifest.exists()
    qualified=ROOT/'outputs/rea/consolidated32-global-checkpoint-20261022T224200Z-r2/result.json'
    proof=json.loads(qualified.read_text())
    assert proof['status']=='PASS_OFFLINE_CONSOLIDATED32_SCANNER_RECORDS_PAIRED_MODULE_GLOBAL_CHECKPOINT'
    assert proof['offline_original_records_reconstructed']==32 and proof['remaining_original_records']==12
    assert hashlib.sha256(qualified.read_bytes()).hexdigest()=='9f1ed6287642e74e9f0cf64056feb735fdd3df6c9c70424f13ae118acee17c93'
    for name in ('consolidated32-source-20261022T222600Z-r2',
                 'dfs467-bounded-source-20261022T225000Z-r2',
                 'vopt481-recovered-core-20261022T201300Z-r1',
                 'vopt481-recovered-core-20261022T202100Z-r2',
                 'rbsdfs466468-recovered-core-20261022T232000Z-r2'):
        folder=ROOT/'outputs/rea'/name
        for source in sorted(folder.rglob('*')):
            if source.is_file()and(source.suffix in SOURCE_EXT or source.name in{'Makefile','Kconfig'}):
                copy(source,Path('candidates')/name/source.relative_to(folder))
    names=('consolidated32-global-checkpoint-20261022T224200Z-r2',
           'consolidated32-source-checkpoint-20261022T223600Z-r2',
           'consolidated32-pair-20261022T223400Z-r2',
           'consolidated32-residual-negative-20261022T224000Z-r2',
           'consolidated32-scanner-abi-20261022T223100Z-r2',
           'consolidated32-start-fixture-20261022T222700Z-r2',
           'consolidated32-next-end-fixture-20261022T222700Z-r2',
           'consolidated32-detach-fixture-20261022T223500Z-r2',
           'consolidated32-policy-fixture-20261022T224100Z-r2',
           'dfs467-bounded-qualification-20261022T225800Z-r2',
           'dfs467-bounded-handoff-20261022T230000Z-r2',
           'dfs467-root-independent-final-20261022T202400Z-r1',
           'vopt481-core-fixture-20261022T201500Z-r1',
           'vopt481-core-fixture-20261022T202200Z-r2',
           'vopt481-core-arc-20261022T203000Z-r3',
           'vopt481-r1-independent-byte-counterexample-20261022T202000Z-r1',
           'vopt481-r2-independent-byte-replay-20261022T202900Z-r1',
           'rbsdfs466468-core-fixture-20261022T232200Z-r1',
           'rbsdfs466468-core-arc-20261022T232400Z-r2',
           'rbsdfs466468-recovered-handoff-20261022T233000Z-r1',
           'windows-oem-vopt481-apply-20261022T200100Z-r1',
           'windows-oem-vopt481-policy-20261022T200100Z-r1',
           'windows-oem-vopt481-peer-classifier-20261022T200900Z-r1',
           'vopt482-calcmd-rea-20261022T203100Z-r1')
    for name in names:
        folder=ROOT/'outputs/rea'/name
        for source in sorted(folder.iterdir()):
            if source.is_file()and(source.suffix in EVIDENCE_EXT or source.name=='function.assembly.txt'):
                copy(source,Path('evidence')/name/source.name)
    for name in ('prepare_hgw5g_vopt481_core.py','prepare_hgw5g_vopt481_unsigned_r2.py',
                 'test_hgw5g_vopt481_core.py','test_hgw5g_vopt481_unsigned_r2.py',
                 'compile_hgw5g_vopt481_core.py','review_hgw5g_dfs467_bounded_root.py',
                 'prepare_hgw5g_rbsdfs_recovered_core.py','test_hgw5g_rbsdfs_recovered_core.py',
                 'compile_hgw5g_rbsdfs_recovered_core.py'):
        copy(ROOT/'tools'/name,Path('tools/integration/recovery32-cores')/name)
    folder=ROOT/'outputs/rea/consolidated32-comments-20261022T203500Z-r1'
    for source in sorted(folder.iterdir()):
        if source.is_file():copy(source,Path('evidence')/folder.name/source.name)
    for row in ROWS:
        assert hashlib.sha256((ROOT/row['source']).read_bytes()).hexdigest()==row['sha256']
        assert hashlib.sha256((REPO/row['path']).read_bytes()).hexdigest()==row['sha256']
    result={'schema':'openmitrastar.preservation-checkpoint/v1','files':ROWS,
            'hardware_accessed':False,'selected_combined_qualified_records':32,
            'remaining_original_records':12,'bounded467_records':1,
            'limits':'467 bounded separately on29;481/466/468 source cores only. No fullfunction/RF/physical/release count.'}
    manifest.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'files':len(ROWS),'bytes':sum(r['bytes']for r in ROWS),'all_copies_exact':True}))


if __name__=='__main__':main()
