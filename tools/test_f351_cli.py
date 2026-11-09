"""Run native CLI processes with wrapped syscalls; never opens a real device."""
import argparse,json,os,subprocess
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('--binary',required=True,type=Path);p.add_argument('--result',required=True,type=Path);a=p.parse_args();cases=[]
 def run(name,verb=None,scenario='valid',data=b'',code=0,stdout=None,empty_stdout=False):
  env=dict(os.environ,F351_FAKE=scenario)
  r=subprocess.run([str(a.binary)]+([] if verb is None else [verb]),input=data,capture_output=True,env=env,timeout=5)
  ok=r.returncode==code and (stdout is None or r.stdout==stdout) and (not empty_stdout or not r.stdout)
  if verb!='load' and b'secret' in r.stdout+r.stderr:ok=False
  cases.append({'name':name,'passed':ok,'exit_code':r.returncode,'stdout_bytes':len(r.stdout),'stderr_bytes':len(r.stderr)})
  if not ok:raise AssertionError((name,r.returncode,r.stdout,r.stderr))
 run('default-no-device',scenario='noio');run('help-no-device','--help','noio')
 run('invalid-command-no-device','bad','noio',code=2,empty_stdout=True)
 run('observe','observe');run('inspect','inspect');run('load','load',stdout=b'secret\0')
 run('load4096','load','maxload',stdout=bytes(range(256))*16)
 run('save-binary','save',data=b'secret\0\n');run('save4096','save',data=bytes(range(256))*16)
 run('save-eintr','save','stdin_eintr',data=b'secret')
 run('empty-input-before-open','save','noio',code=2,empty_stdout=True)
 run('oversize-before-open','save','noio',data=b'x'*4097,code=2,empty_stdout=True)
 run('stdin-error-before-open','save','stdin_error',code=2,empty_stdout=True)
 run('empty-load','load','empty',code=3,empty_stdout=True)
 run('empty-inspect','inspect','empty',code=3,stdout=b'{"status":"empty"}\n')
 node=['symlink','regular','owner','group','mode','setuid','rdev','not_sysfs','sysfs_trailing','sysfs_negative','sysfs_huge','sysfs_major','sysfs_nul']
 for mode in node:run('node-'+mode,'load',mode,code=1,empty_stdout=True)
 bad=['untouched','ioctl_positive','ioctl_error','partial','header_only','truncated_payload','status','backend','journal','abi','op','flags','quarantine','claimed','exact_part','common','bool','id0','idff','wip','failure_phase','phase','sequence','slot','record0','record_over','length','tail','close_error']
 for mode in bad:run('response-'+mode,'load',mode,code=1,empty_stdout=True)
 for mode in ['commit','protection','witness','save_bool','length','status','backend','journal','exact_part','common']:
  run('save-'+mode,'save',mode,data=b'secret',code=1,empty_stdout=True)
 for mode in ['untouched','header_only','truncated_payload','tail','journal','phase']:
  run('observe-'+mode,'observe',mode,code=1,empty_stdout=True)
 a.result.write_text(json.dumps({'schema':'openmitrastar.f351-cli-tests/v1','status':'PASS','cases':cases,'count':len(cases),'real_device_opened':False},indent=2)+'\n')
 print(json.dumps({'status':'PASS','cases':len(cases)}))
if __name__=='__main__':main()
