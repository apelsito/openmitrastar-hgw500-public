"""New immutable481 revision: ARC ldb zero extension on four saved bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--assembly',type=Path,required=True)
    a=p.parse_args();assert not a.output.exists()
    assembly=a.assembly.read_text()
    assert '0x71244: ldb r2, [r2]'in assembly and '0x7125c: ldb r3, [r2]'in assembly
    assert '0x71280: ldb.x r2, [r3, 0xc]'in assembly
    shutil.copytree(a.parent,a.output)
    source=a.output/'openmitrastar_vopt481_recovered.c';old=source.read_text()
    new=re.sub(r'om_vopt_byte_value\(state->(saved_txbf|saved_pppc|saved_probe|saved_airfair)\)',r'(int)state->\1',old)
    assert new!=old and new.count('om_vopt_byte_value(')==2
    source.write_text(new,encoding='utf-8',newline='\n')
    proof=json.loads((a.parent/'result.json').read_text());proof['status']='SOURCE_ONLY_OEM481_CORE_R2_UNSIGNED_SAVED_BYTES'
    proof['source_files']={name:sha(a.output/name)for name in proof['source_files']}
    proof['correction']='Four saved OEM bytes use ldb zero extension; channel mode482 alone uses ldb.x sign extension.'
    proof['parent_result_sha256']=sha(a.parent/'result.json')
    proof['correction_pins']={str(path):sha(path)for path in[Path(__file__),a.assembly]}
    (a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({'status':proof['status'],'source_sha256':sha(source)}))


if __name__=='__main__':main()
