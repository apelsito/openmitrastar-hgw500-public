"""Versioned VOPT34 full header builder wrapper, pin .inc source dependencies."""
import hashlib,os
from pathlib import Path
import subprocess,sys
def main():
 root=Path(__file__).resolve().parents[1];original=root/'tools/build_hgw5g_typed_header_closure.py';text=original.read_text();needle="x.suffix in('.c','.h')";assert text.count(needle)==1;text=text.replace(needle,"x.suffix in('.c','.h','.inc')",1);text=text.replace('Generic offline ARC QDRV/net80211 typed-header closure builder.','VOPT34 offline full closure including .inc source pins.',1);args=sys.argv[1:];idx=args.index('--output')+1;output=Path(args[idx]);runtime=output.parent/(output.name+'-builder');runtime.mkdir(parents=True,exist_ok=False);tool=runtime/'build-actual-vopt34.py';tool.write_text(text,newline='\n');env=os.environ.copy();env['PYTHONPATH']=str(root/'tools');r=subprocess.run([sys.executable,str(tool),*args],env=env);return r.returncode
if __name__=='__main__':raise SystemExit(main())
