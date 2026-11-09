"""Build current uClibc-ng for ARC750/MMUv2 with kernel-assisted atomics."""
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

def run(command,path,env):
    print('RUN '+path.name,flush=True)
    with path.open('xb') as log:
        subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,env=env,check=True,timeout=1200)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for k in ['inputs','toolchain','output']:p.add_argument('--'+k,type=Path,required=True)
    p.add_argument('--host-locales',type=Path,required=True)
    a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
    manifest=json.loads((a.inputs/'manifest.json').read_text());record=next(r for r in manifest['inputs'] if r['name']=='uclibc-ng')
    assert sha(a.inputs/'uclibc-ng.tar')==record['sha256']
    source=a.output/'source';shutil.copytree(record['source'],source)
    tc=str(a.toolchain/'bin/arc-snps-linux-uclibc-')
    assert sha(Path(tc+'gcc'))=='3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263'
    original=Path(subprocess.check_output([tc+'gcc','-print-sysroot'],text=True).strip()).resolve()
    headers=a.output/'kernel-headers';headers.mkdir()
    for name in ['linux','asm','asm-generic']:
        shutil.copytree(original/'usr/include'/name,headers/name,symlinks=True)
    config='''TARGET_arc=y
# CONFIG_ARC_HAS_ATOMICS is not set
CONFIG_ARC_PAGE_SIZE_8K=y
ARCH_LITTLE_ENDIAN=y
ARCH_WANTS_LITTLE_ENDIAN=y
UCLIBC_HAS_THREADS_NATIVE=y
# HAS_NO_THREADS is not set
UCLIBC_HAS_TLS=y
HAVE_SHARED=y
DOPIC=y
UCLIBC_HAS_SSP=y
UCLIBC_BUILD_RELRO=y
UCLIBC_BUILD_NOW=y
UCLIBC_HAS_IPV6=y
UCLIBC_USE_NETLINK=y
UCLIBC_SUPPORT_AI_ADDRCONFIG=y
UCLIBC_HAS_RESOLVER_SUPPORT=y
UCLIBC_HAS_LFS=y
UCLIBC_HAS_UTMPX=y
UCLIBC_HAS_UTMP=y
DO_C99_MATH=y
UCLIBC_HAS_CRYPT_IMPL=y
UCLIBC_HAS_CRYPT_SHA256=y
UCLIBC_HAS_CRYPT_SHA512=y
UCLIBC_HAS_WCHAR=y
UCLIBC_HAS_LOCALE=y
UCLIBC_BUILD_MINIMAL_LOCALE=y
UCLIBC_BUILD_MINIMAL_LOCALES="en_US es_ES"
RUNTIME_PREFIX="/"
DEVEL_PREFIX="/usr/"
MULTILIB_DIR="lib"
DOSTRIP=y
'''
    config+='KERNEL_HEADERS="'+str(headers)+'"\nCROSS_COMPILER_PREFIX="'+tc+'"\n'
    config+='UCLIBC_EXTRA_CFLAGS="-mcpu=arc700 -mno-lock -mno-atomic -mno-swape -Os -ffile-prefix-map='+str(a.output)+'=/usr/src/uclibc-ng-1.0.59"\n'
    (source/'.config').write_text(config)
    assert all((a.host_locales/name).is_dir() for name in ['en_US','en_US.UTF-8','es_ES','es_ES.UTF-8'])
    env=os.environ.copy();env.update(SOURCE_DATE_EPOCH='1792694400',LC_ALL='C',LOCPATH=str(a.host_locales))
    make=['make','-C',str(source),'CROSS_COMPILE='+tc]
    run(make+['olddefconfig'],a.output/'config.log',env)
    final=(source/'.config').read_text();assert '# CONFIG_ARC_HAS_ATOMICS is not set' in final
    assert 'UCLIBC_HAS_THREADS_NATIVE=y' in final and 'CONFIG_ARC_PAGE_SIZE_8K=y' in final
    # Make4.3 does not implement scoped .NOTPARALLEL. Generate host locale
    # headers serially before the parallel target build; retain ES/UTF-8.
    run(make+['-j1','locale_headers'],a.output/'locale-headers.log',env)
    run(make+['-j6'],a.output/'build.log',env)
    sysroot=a.output/'sysroot';sysroot.mkdir()
    run(make+['PREFIX='+str(sysroot),'install'],a.output/'install.log',env)
    for name in ['linux','asm','asm-generic']:
        target=sysroot/'usr/include'/name
        if not target.exists():shutil.copytree(headers/name,target,symlinks=True)
    binary=a.output/'hello';test=a.output/'hello.c';test.write_text('#include <stdio.h>\n#include <stdlib.h>\nint main(void){puts("OPENMITRASTAR_LIBC_1_0_59");return 0;}\n')
    run([tc+'gcc','--sysroot='+str(sysroot),'-mcpu=arc700','-mno-lock','-mno-atomic','-mno-swape','-static','-Os',str(test),'-o',str(binary)],a.output/'hello-build.log',env)
    libs=sorted(sysroot.glob('lib/*.so*'))+sorted(sysroot.glob('usr/lib/*.a'))
    checked=[]
    for f in [binary]+[x for x in libs if x.is_file() and not x.is_symlink()]:
        if f.suffix!='.a' and not f.read_bytes().startswith(b'\x7fELF'):continue
        asm=subprocess.check_output([tc+'objdump','-d',str(f)],text=True,stderr=subprocess.DEVNULL)
        assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm),f
        checked.append({'path':str(f.relative_to(a.output)),'bytes':f.stat().st_size,'sha256':sha(f)})
    assert any('libc.a' in r['path'] for r in checked)
    report={'schema':'openmitrastar.libc2026-arc750/v1','status':'PASS_LIBC_BUILD_NO_FORBIDDEN_INSTRUCTIONS',
            'hardware_accessed':False,'physical':'UNRUN','source':record,'config_sha256':sha(source/'.config'),
            'atomics':'Kernel arc_usr_cmpxchg syscall, UP only; no LLOCK/SCOND',
            'kernel_headers':'Existing pinned toolchain exported headers, unchanged Linux userspace ABI',
            'sysroot':str(sysroot),'checked':checked,'limits':['Physical libc syscall/thread/TLS runtime not yet tested.']}
    (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
