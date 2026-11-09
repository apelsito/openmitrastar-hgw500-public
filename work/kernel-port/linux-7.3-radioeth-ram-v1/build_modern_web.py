"""Build pinned current uhttpd/TLS and dependencies against the new ARC libc."""
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
 with path.open('xb') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,env=env,check=True,timeout=1200)

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['inputs','extra-inputs','sysroot','toolchain','cmake','output']:p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 tc=str(a.toolchain/'bin/arc-snps-linux-uclibc-');assert sha(Path(tc+'gcc'))=='3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263'
 assert (a.sysroot/'usr/lib/libc.a').is_file()
 records=json.loads((a.inputs/'manifest.json').read_text())['inputs']+json.loads((a.extra_inputs/'manifest.json').read_text())['inputs']
 source_records={r['name']:r for r in records};sources={}
 for name in ['wolfssl','json-c','libubox','ustream-ssl','uhttpd','libnl-tiny']:
  r=source_records[name];archive=(a.extra_inputs if name=='json-c' else a.inputs)/(name+'.tar');assert sha(archive)==r['sha256']
  source=a.output/'sources'/name;source.parent.mkdir(exist_ok=True);shutil.copytree(r['source'],source);sources[name]=source
 prefix=a.output/'install';prefix.mkdir();tool=a.output/'toolchain.cmake'
 # GCC's shipped libatomic requires LLOCK/SCOND. Bind only the needed 32-bit
 # helpers to the same UP syscall primitive used by the qualified libc.
 helper=Path(__file__).resolve().parent/'arc750_atomic32.c'
 shutil.copyfile(helper,sources['libubox']/'arc750_atomic32.c')
 f=sources['libubox']/'CMakeLists.txt';s=f.read_text();anchor='ADD_LIBRARY(ubox SHARED ${SOURCES})';assert s.count(anchor)==1
 f.write_text(s.replace(anchor,'LIST(APPEND SOURCES arc750_atomic32.c)\n'+anchor))
 flags='-mcpu=arc700 -mno-lock -mno-atomic -mno-swape -Os -fPIC -fstack-protector-strong -ffunction-sections -fdata-sections -ffile-prefix-map='+str(a.output)+'=/usr/src/modern-web'
 tool.write_text('\n'.join(['set(CMAKE_SYSTEM_NAME Linux)','set(CMAKE_SYSTEM_PROCESSOR arc)',
  'set(CMAKE_C_COMPILER "'+tc+'gcc")','set(CMAKE_AR "'+tc+'ar")','set(CMAKE_RANLIB "'+tc+'ranlib")',
  'set(CMAKE_SYSROOT "'+str(a.sysroot)+'")','set(CMAKE_C_FLAGS_INIT "'+flags+'")',
  'set(CMAKE_EXE_LINKER_FLAGS_INIT "-Wl,--gc-sections,-z,relro,-z,now")',
  'set(CMAKE_SHARED_LINKER_FLAGS_INIT "-Wl,--gc-sections,-z,relro,-z,now")',
  'set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)',
  'set(CMAKE_FIND_ROOT_PATH "'+str(prefix)+'" "'+str(a.sysroot)+'")',
  'set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)','set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)',
  'set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)','set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)'])+'\n')
 env=os.environ|{'SOURCE_DATE_EPOCH':'1792694400','LC_ALL':'C','PKG_CONFIG_LIBDIR':str(prefix/'lib/pkgconfig'),'PKG_CONFIG_PATH':str(prefix/'lib/pkgconfig')}
 # gcc15+ no-hardware-atomic code may reference libatomic. Let the real
 # linker identify requirements; do not silently substitute lock semantics.
 def cmake(name,options):
  build=a.output/('build-'+name)
  cmd=[str(a.cmake),'-S',str(sources[name]),'-B',str(build),'-G','Unix Makefiles','-DCMAKE_TOOLCHAIN_FILE='+str(tool),'-DCMAKE_BUILD_TYPE=MinSizeRel','-DCMAKE_INSTALL_PREFIX='+str(prefix),'-DCMAKE_INSTALL_LIBDIR=lib']+options
  run(cmd,a.output/(name+'-config.log'),env)
  run([str(a.cmake),'--build',str(build),'--parallel','6'],a.output/(name+'-build.log'),env)
  run([str(a.cmake),'--install',str(build)],a.output/(name+'-install.log'),env)
 cmake('wolfssl',['-DBUILD_SHARED_LIBS=ON','-DWOLFSSL_ASM=no','-DWOLFSSL_SINGLE_THREADED=yes',
  '-DWOLFSSL_OPENSSLEXTRA=yes','-DWOLFSSL_OPENSSLALL=no','-DWOLFSSL_TLS13=yes','-DWOLFSSL_TLSV12=yes',
  '-DWOLFSSL_OLD_TLS=no','-DWOLFSSL_TLSV10=no','-DWOLFSSL_EXAMPLES=no','-DWOLFSSL_CRYPT_TESTS=no',
  '-DWOLFSSL_MLKEM=no','-DWOLFSSL_DH=const','-DWOLFSSL_EX_DATA=yes','-DWOLFSSL_TLSX=yes'])
 cmake('json-c',['-DBUILD_SHARED_LIBS=ON','-DBUILD_STATIC_LIBS=ON','-DBUILD_TESTING=OFF','-DENABLE_THREADING=OFF','-DENABLE_RDRAND=OFF','-DDISABLE_WERROR=ON'])
 cmake('libubox',['-DBUILD_LUA=OFF','-DBUILD_EXAMPLES=OFF','-DUNIT_TESTING=OFF'])
 cmake('ustream-ssl',['-DWOLFSSL=ON','-DMBEDTLS=OFF'])
 cmake('uhttpd',['-DTLS_SUPPORT=ON','-DLUA_SUPPORT=OFF','-DUBUS_SUPPORT=OFF','-DUCODE_SUPPORT=OFF'])
 cmake('libnl-tiny',[])
 checked=[]
 for f in sorted(prefix.rglob('*')):
  if not f.is_file() or f.is_symlink() or not f.read_bytes().startswith(b'\x7fELF'):continue
  subprocess.run([tc+'strip','--strip-unneeded',str(f)],check=True)
  asm=subprocess.check_output([tc+'objdump','-d',str(f)],text=True)
  assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm),f
  dyn=subprocess.check_output([tc+'readelf','-d',str(f)],text=True)
  needed=re.findall(r'\(NEEDED\).*\[([^]]+)\]',dyn)
  checked.append({'path':f.relative_to(prefix).as_posix(),'bytes':f.stat().st_size,'sha256':sha(f),'needed':needed,'forbidden_instructions':0})
 assert (prefix/'bin/uhttpd').is_file() and any('libustream' in r['path'] for r in checked)
 report={'schema':'openmitrastar.modern-web-arc750/v1','status':'PASS_ARC_CURRENT_WEB_BUILD','hardware_accessed':False,'physical':'UNRUN',
  'inputs':source_records,'sysroot':str(a.sysroot),'libraries_shared':True,'tls_versions':'1.2/1.3 enabled; physical rejection/handshake unrun',
  'checked':checked,'limits':['Host interoperability and physical ARC loader/TLS/API integration unrun.','uhttpd config must expose only HTTPS; current build also contains HTTP capability but no listener has started.']}
 (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
