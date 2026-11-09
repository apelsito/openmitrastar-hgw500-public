"""Runexact staticREA function with isolatedWindowsARC lab andexistingJavaNode."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime,timezone


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
 p=argparse.ArgumentParser();p.add_argument('--lab',type=Path,required=True);p.add_argument('--target',type=Path,required=True);p.add_argument('--procedure',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 manifest=json.loads((a.lab/'manifest.json').read_text());a.output.mkdir(parents=True,exist_ok=False);target=a.target.resolve();before=sha(target)
 runtime=Path(manifest['runtime']).resolve();view=Path(manifest['ghidra']).resolve();java=Path(manifest['java']);node=Path(manifest['node'])
 env=os.environ.copy();env.update(GHIDRA_INSTALL_DIR=str(view),JAVA_HOME=str(java),REA_GHIDRA_LANGUAGE_ID=manifest['language_id'],REA_GHIDRA_COMPILER_SPEC_ID=manifest['compiler_spec_id'],REA_GHIDRA_STARTUP_TIMEOUT_MS='900000')
 env['PATH']=str(node.parent)+os.pathsep+str(java/'bin')+os.pathsep+env.get('PATH','')
 command=[str(node),str(runtime/'scripts/rea.mjs'),'function',str(target),'--procedure',a.procedure,'--provider','ghidra','--format','json','--full-output']
 started=datetime.now(timezone.utc).isoformat();print(json.dumps(dict(started=started,procedure=a.procedure,target_sha256=before)),flush=True)
 with(a.output/'rea.json').open('wb')as out,(a.output/'rea.stderr').open('wb')as err:proc=subprocess.run(command,env=env,stdout=out,stderr=err,timeout=900)
 result=dict(started_utc=started,finished_utc=datetime.now(timezone.utc).isoformat(),command=command,exit_code=proc.returncode,target_sha256=before,target_unchanged=before==sha(target),hardware_accessed=False,installed_runtime_modified=False,lab_manifest_sha256=sha(a.lab/'manifest.json'),rea_output_sha256=sha(a.output/'rea.json'))
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True);returnproc=proc.returncode;return returnproc


if __name__=='__main__':raise SystemExit(main())
