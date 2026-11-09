"""Record current complete source trees and compare exact input pins afterward."""
import argparse, datetime, hashlib, json
from pathlib import Path

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,action='append',required=True)
    parser.add_argument('--file',type=Path,action='append',default=[])
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--compare',type=Path)
    args=parser.parse_args()
    assert not args.output.exists()
    files={}
    for root in args.root:
        assert root.is_dir(),root
        for path in sorted(root.rglob('*')):
            if path.is_file() and '.git' not in path.relative_to(root).parts:
                files[str(path.resolve())]=sha(path)
    for path in args.file:
        files[str(path.resolve())]=sha(path)
    proof={'status':'PASS_INPUT_PIN_SNAPSHOT','observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
           'files':files,'file_count':len(files),'hardware_accessed':False}
    if args.compare:
        prior=json.loads(args.compare.read_text())['files']
        changed=sorted(k for k in files.keys()|prior.keys() if files.get(k)!=prior.get(k))
        proof.update(status='PASS_INPUT_PIN_UNCHANGED' if not changed else 'NO_GO_INPUT_PINS_CHANGED',changed_files=changed)
    args.output.write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({'status':proof['status'],'file_count':len(files),'output':str(args.output)},indent=2))

if __name__=='__main__':main()
