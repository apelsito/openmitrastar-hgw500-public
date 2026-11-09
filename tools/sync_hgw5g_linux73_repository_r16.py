"""Preserve native-provider7.3 revision separately from sealed first package."""
from pathlib import Path
import hashlib
import json
from preserve_hgw5g_progress_20261022_r13 import ROOT,REPO,ROWS,copy


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    candidate=ROOT/'outputs/rea/linux73-full44-candidate-20261023T000500Z-r16'
    manifest=REPO/'manifests/preservation-checkpoint-20261022-linux73-native-r16.json'
    assert not manifest.exists();proof=json.loads((candidate/'result.json').read_text())
    for relative,digest in proof['files'].items():
        path=candidate/relative.replace('\\','/');assert sha(path)==digest
    for group in('source','headers','kernel-overlay','providers'):
        for source in sorted((candidate/group).rglob('*')):
            if source.is_file():
                assert source.suffix.lower()not in('.o','.ko','.elf','.exe','.key','.pem','.bin')
                copy(source,Path('src/linux-7.3-r16')/source.relative_to(candidate))
    for source in sorted(candidate.iterdir()):
        if source.is_file()and source.suffix in('.json','.patch','.txt')or source.name=='Kbuild':
            copy(source,Path('src/linux-7.3-r16')/source.name)
    for name in ('linux73-providers-ccmp-qualification-20261022T211400Z-r1',
                 'linux73-bridge-kernel-overlay-20261022T212200Z-r2',
                 'publication-license-review-20261022T222500Z-r1'):
        folder=ROOT/'outputs/rea'/name
        for source in folder.iterdir():
            if source.is_file()and source.suffix in('.json','.md','.c','.h','.patch'):
                destination=Path('evidence')/name/source.name
                if(REPO/destination).exists():assert (REPO/destination).read_bytes()==source.read_bytes()
                else:copy(source,destination)
    for row in ROWS:assert sha(ROOT/row['source'])==row['sha256']and sha(REPO/row['path'])==row['sha256']
    value={'schema':'openmitrastar.preservation-checkpoint/v1','files':ROWS,'hardware_accessed':False,
           'target_kernel':'Linux7.3','repository_visibility':'private','package':'src/linux-7.3-r16',
           'scope':'Nativeproviderssourceadded; actualfullmodule/newkernel/base/ABI/physicalgates pending.'}
    manifest.write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'files':len(ROWS),'bytes':sum(r['bytes']for r in ROWS),'all_copies_exact':True}))


if __name__=='__main__':main()
