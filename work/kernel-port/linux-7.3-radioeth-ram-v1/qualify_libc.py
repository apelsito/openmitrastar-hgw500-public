"""Install and qualify a completed current no-atomic ARC libc build."""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['build','toolchain','output']:p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 tc=str(a.toolchain/'bin/arc-snps-linux-uclibc-');tree=a.build/'source'
 config=(tree/'.config').read_text();assert '# CONFIG_ARC_HAS_ATOMICS is not set' in config and 'DO_C99_MATH=y' in config
 assert 'UCLIBC_BUILD_MINIMAL_LOCALES="en_US es_ES"' in config and (tree/'lib/libuClibc-1.0.59.so').is_file()
 env=os.environ|{'SOURCE_DATE_EPOCH':'1792694400','LC_ALL':'C','LOCPATH':str(a.build.parent/'host-locales-isolated-v1/locales')}
 sysroot=a.output/'sysroot';sysroot.mkdir()
 with (a.output/'install.log').open('xb') as f:
  subprocess.run(['make','-C',str(tree),'CROSS_COMPILE='+tc,'PREFIX='+str(sysroot),'install'],stdout=f,stderr=subprocess.STDOUT,env=env,check=True,timeout=300)
 for name in ['linux','asm','asm-generic']:
  target=sysroot/'usr/include'/name
  if not target.exists():shutil.copytree(a.build/'kernel-headers'/name,target,symlinks=True)
 test=a.output/'hello.c';test.write_text('#include <stdio.h>\n#include <locale.h>\n#include <stdlib.h>\nint main(void){if(!setlocale(LC_ALL,"es_ES.UTF-8"))return 2;puts("OPENMITRASTAR_LIBC_1_0_59");printf("%.2f\\n",-1.25);return 0;}\n')
 binary=a.output/'hello'
 with (a.output/'hello-build.log').open('xb') as f:
  subprocess.run([tc+'gcc','--sysroot='+str(sysroot),'-mcpu=arc700','-mno-lock','-mno-atomic','-mno-swape','-static','-Os',str(test),'-o',str(binary)],stdout=f,stderr=subprocess.STDOUT,check=True,timeout=60)
 candidates=[binary]+[f for directory in ['lib','usr/lib'] for f in (sysroot/directory).iterdir() if f.is_file() and not f.is_symlink() and (f.suffix=='.a' or f.read_bytes().startswith(b'\x7fELF'))]
 checked=[]
 for f in candidates:
  asm=subprocess.check_output([tc+'objdump','-d',str(f)],text=True,stderr=subprocess.DEVNULL)
  assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm),f
  checked.append({'path':str(f.relative_to(a.output)),'bytes':f.stat().st_size,'sha256':sha(f),'forbidden_instructions':0})
 assert any('libc.a' in r['path'] for r in checked)
 report={'schema':'openmitrastar.libc2026-qualification/v1','status':'PASS_LIBC_SHARED_STATIC_NO_FORBIDDEN_INSTRUCTIONS',
  'hardware_accessed':False,'physical':'UNRUN','config_sha256':sha(tree/'.config'),'checked':checked,
  'sysroot':str(sysroot),'atomics':'Kernel arc_usr_cmpxchg syscall; UP-only target',
  'locales':['en_US','es_ES','en_US.UTF-8','es_ES.UTF-8'],'limits':['Link and disassembly qualification, physical libc/thread execution not yet tested.']}
 (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
