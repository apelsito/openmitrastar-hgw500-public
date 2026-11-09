"""Versioned OEM481 fixture correction; original r1 fixture remains untouched."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
    parent=Path(__file__).with_name('test_hgw5g_vopt481_core.py');text=parent.read_text()
    assert '{0,78,-1}'in text and '{0,195,-128}'in text
    text=text.replace('{0,78,-1}','{0,78,255}').replace('{0,195,-128}','{0,195,128}')
    script=a.output/'unsigned-fixture-generator.py';script.write_text(text,encoding='utf-8',newline='\n')
    command=[sys.executable,str(script),'--candidate',str(a.candidate),'--compiler',str(a.compiler),'--output',str(a.output/'run')]
    r=subprocess.run(command,capture_output=True);(a.output/'run.stdout').write_bytes(r.stdout);(a.output/'run.stderr').write_bytes(r.stderr)
    assert r.returncode==0,r.stderr
    result=json.loads((a.output/'run/result.json').read_text())
    result['correction_pins']={str(path):sha(path)for path in[Path(__file__),parent,script]}
    result['status']='PASS_OEM481_R2_UNSIGNED_SAVED_BYTES_AND_STATE_CALL_FIXTURE'
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
