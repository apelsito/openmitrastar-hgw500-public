"""Preserve qualified34 and reviewed32+bounded467 without including binaries."""
from pathlib import Path
import hashlib
import json
from preserve_hgw5g_progress_20261022_r13 import ROOT, REPO, ROWS, SOURCE_EXT, EVIDENCE_EXT, copy


def main():
    manifest=REPO/'manifests/preservation-checkpoint-20261022-weather34-bounded467-r1.json'
    assert not manifest.exists()
    qualified=ROOT/'outputs/rea/weather478-qualification-20261023T000100Z-r1/result.json'
    proof=json.loads(qualified.read_text());assert proof['complete_original_records']==34
    assert hashlib.sha256(qualified.read_bytes()).hexdigest()=='1c6296d7ee0111d757d19d9147971d3635df0d7c4e73c665ee5ad8bdea0187e7'
    for name in ('weather478-source34-20261022T210000Z-r1','consolidated32-plus-bounded467-source-20261022T231000Z-r1'):
        folder=ROOT/'outputs/rea'/name
        for source in sorted(folder.rglob('*')):
            if source.is_file()and(source.suffix in SOURCE_EXT or source.name in{'Makefile','Kconfig'}):
                copy(source,Path('candidates')/name/source.relative_to(folder))
    names=('weather478-qualification-20261023T000100Z-r1',
           'weather478-pair-20261022T234500Z-r1',
           'weather478-all-abi-20261022T234000Z-r1',
           'weather478-default-proof-20261022T235200Z-r1',
           'weather478-actual-consumers-20261022T210300Z-r2',
           'weather478-negative-20261022T235700Z-r2',
           'weather478-handoff-20261023T000500Z-r1',
           'weather478-root-independent-review-20261022T212000Z-r1',
           'weather478-final-root-supplement-20261023T000700Z-r1',
           'consolidated32-plus-bounded467-qualification-20261022T232300Z-r1',
           'consolidated32-plus-bounded467-root-review-20261022T211000Z-r1',
           'consolidated32-plus-bounded467-handoff-20261022T232900Z-r1')
    for name in names:
        folder=ROOT/'outputs/rea'/name
        for source in sorted(folder.iterdir()):
            if source.is_file()and source.suffix in EVIDENCE_EXT:
                copy(source,Path('evidence')/name/source.name)
    for name in ('prepare_hgw5g_weather478_source.py','test_hgw5g_weather478_consumers.py',
                 'review_hgw5g_weather478_root.py','review_consolidated32_bounded467_root.py',
                 'audit_hgw5g_weather478_modules.py','qualify_hgw5g_weather478.py'):
        copy(ROOT/'tools'/name,Path('tools/integration/weather34-reviewed')/name)
    for row in ROWS:
        assert hashlib.sha256((ROOT/row['source']).read_bytes()).hexdigest()==row['sha256']
        assert hashlib.sha256((REPO/row['path']).read_bytes()).hexdigest()==row['sha256']
    result={'schema':'openmitrastar.preservation-checkpoint/v1','files':ROWS,
            'hardware_accessed':False,'selected_combined_qualified_records':34,
            'remaining_original_records':10,'bounded467_records':1,
            'limits':'467 remains separately integrated on32; not yet combined with34. No physical/functional/release claim.'}
    manifest.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'files':len(ROWS),'bytes':sum(r['bytes']for r in ROWS),'all_copies_exact':True}))


if __name__=='__main__':main()
