"""Combine recovered source lineages for Linux7.3 adaptation, source-only.

Each merge uses the exact common predecessor. Conflicts are retained and stop
the next merge; no content is silently selected and no module is promoted.
"""
import argparse
from collections import Counter
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from catalog_hgw_firmware_comments import scan_comments

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    assert not a.output.exists();a.output.mkdir(parents=True)
    base=ROOT/'outputs/rea/consolidated32-source-20261022T222600Z-r2'
    seed=ROOT/'outputs/rea/mdid35-weather478-source37-20261023T000600Z-r1'
    for tree in('source','headers'):shutil.copytree(seed/tree,a.output/tree)
    merges=[('vopt481',base,ROOT/'outputs/rea/vopt34-linux-source-20261022T215800Z-r9'),
            ('bounded467',base,ROOT/'outputs/rea/consolidated32-plus-bounded467-source-20261022T231000Z-r1'),
            ('rbs466468',ROOT/'outputs/rea/weather478-source34-20261022T210000Z-r1',ROOT/'outputs/rea/rbsdfs466468-kernel-source-20261023T004300Z-r4')]
    steps=[];conflicts=[]
    for label,ancestor,theirs in merges:
        directory=a.output/'merge-evidence'/label;directory.mkdir(parents=True)
        for tree in('source','headers'):
            for incoming in sorted((theirs/tree).rglob('*')):
                if not incoming.is_file():continue
                relative=incoming.relative_to(theirs);old=ancestor/relative;dest=a.output/relative
                if old.exists() and old.read_bytes()==incoming.read_bytes():continue
                if not old.exists():
                    if dest.exists():assert dest.read_bytes()==incoming.read_bytes(),str(relative)
                    else:dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(incoming,dest)
                    continue
                assert dest.exists()
                # Exact file bytes remain the authority; git merge-file edits
                # neither predecessor nor incoming branch and returns merged stdout.
                r=subprocess.run(['git','merge-file','-p','-L','combined','-L',label+'-base','-L',label,
                                  str(dest),str(old),str(incoming)],capture_output=True)
                assert r.returncode>=0,r.stderr.decode(errors='replace')
                if r.returncode:
                    artifact=directory/(str(relative).replace('\\','_').replace('/','_')+'.conflict')
                    artifact.write_bytes(r.stdout)
                    conflicts.append({'merge':label,'file':relative.as_posix(),'artifact':str(artifact)})
                else:dest.write_bytes(r.stdout)
        steps.append({'lineage':label,'base':str(ancestor),'incoming':str(theirs),'result_sha256':sha(theirs/'result.json')})
        if conflicts:break
    comment_errors=[]
    for tree in('source','headers'):
        for old in(seed/tree).rglob('*'):
            if not old.is_file()or old.suffix not in('.c','.h','.inc'):continue
            new=a.output/old.relative_to(seed)
            commentbytes=lambda raw:Counter(raw[r['offset']:r['end_offset']]for r in scan_comments(raw))
            missing=commentbytes(old.read_bytes())-commentbytes(new.read_bytes())
            if missing:comment_errors.append(old.relative_to(seed).as_posix())
    files={f.relative_to(a.output).as_posix():sha(f)for tree in('source','headers')for f in(a.output/tree).rglob('*')if f.is_file()}
    proof={'status':'SOURCE_ONLY_ALL_OEM_TABLE_ENTRIES_COMBINED_PENDING_LINUX73'if not conflicts and not comment_errors else'SOURCE_MERGE_REQUIRES_EXPLICIT_CONFLICT_RESOLUTION',
           'target_kernel':'Linux7.3','hardware_accessed':False,'firmware_eligible':False,
           'source_original_records_expected':44 if not conflicts else None,
           'private_table_records_expected':610 if not conflicts else None,
           'Linux73_qualified_records':0,'merged_lineages':steps,'conflicts':conflicts,
           'old_comments_missing':comment_errors,'files':files,
           'limits':['Combined source is not a compiled Linux7.3driver.',
                     'Original607 table records plus3port additions are expected only after all exact source merges and table verification.',
                     '467 remains bounded5GHz/20MHz; RBS466468 frame provider unavailable, so4ops remain incomplete.',
                     'Full Quantenna Linux7.3 kernel/skbuff/board/DMA/PMQoS/crypto/Kbuild/provider integration is pending.',
                     'No physicalRF/client/traffic/persistentboot/rollback/release acceptance.']}
    (a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({'status':proof['status'],'conflicts':conflicts,'missing_comments':comment_errors}))


if __name__=='__main__':main()
