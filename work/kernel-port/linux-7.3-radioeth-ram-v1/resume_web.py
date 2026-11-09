"""Resume existing web build after qualified ARC atomic integration; fresh logs."""
import argparse,hashlib,json,os,re,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(command,log,env):
 print('RUN '+log.name,flush=True)
 with log.open('xb') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,env=env,check=True,timeout=1200)

def main():
 p=argparse.ArgumentParser()
 for name in ['build','sysroot','cmake','toolchain','output']:p.add_argument('--'+name,type=Path,required=True)
 a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 prefix=a.build/'install';tc=str(a.toolchain/'bin/arc-snps-linux-uclibc-')
 sources={name:a.build/'sources'/name for name in ['libubox','ustream-ssl','uhttpd','libnl-tiny']}
 helper=sources['libubox']/'arc750_atomic32.c';assert not helper.exists();shutil.copyfile(HERE/'arc750_atomic32.c',helper)
 file=sources['libubox']/'CMakeLists.txt';text=file.read_text();anchor='ADD_LIBRARY(ubox SHARED ${SOURCES})';assert text.count(anchor)==1;file.write_text(text.replace(anchor,'LIST(APPEND SOURCES arc750_atomic32.c)\n'+anchor))
 env=os.environ|{'SOURCE_DATE_EPOCH':'1792694400','LC_ALL':'C','PKG_CONFIG_LIBDIR':str(prefix/'lib/pkgconfig'),'PKG_CONFIG_PATH':str(prefix/'lib/pkgconfig')}
 for name,options in [('libubox',['-DBUILD_LUA=OFF','-DBUILD_EXAMPLES=OFF','-DUNIT_TESTING=OFF']),('ustream-ssl',['-DWOLFSSL=ON','-DMBEDTLS=OFF']),('uhttpd',['-DTLS_SUPPORT=ON','-DLUA_SUPPORT=OFF','-DUBUS_SUPPORT=OFF','-DUCODE_SUPPORT=OFF']),('libnl-tiny',[])]:
  build=a.build/('build-'+name)
  run([str(a.cmake),'-S',str(sources[name]),'-B',str(build),'-G','Unix Makefiles','-DCMAKE_TOOLCHAIN_FILE='+str(a.build/'toolchain.cmake'),'-DCMAKE_BUILD_TYPE=MinSizeRel','-DCMAKE_INSTALL_PREFIX='+str(prefix),'-DCMAKE_INSTALL_LIBDIR=lib']+options,a.output/(name+'-config.log'),env)
  run([str(a.cmake),'--build',str(build),'--parallel','6'],a.output/(name+'-build.log'),env)
  run([str(a.cmake),'--install',str(build)],a.output/(name+'-install.log'),env)
 checked=[]
 for f in sorted(prefix.rglob('*')):
  if not f.is_file() or f.is_symlink() or not f.read_bytes().startswith(b'\x7fELF'):continue
  subprocess.run([tc+'strip','--strip-unneeded',str(f)],check=True)
  asm=subprocess.check_output([tc+'objdump','-d',str(f)],text=True);assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm),f
  dyn=subprocess.check_output([tc+'readelf','-d',str(f)],text=True)
  checked.append({'path':f.relative_to(prefix).as_posix(),'bytes':f.stat().st_size,'sha256':sha(f),'needed':re.findall(r'\(NEEDED\).*\[([^]]+)\]',dyn),'forbidden_instructions':0})
 assert (prefix/'bin/uhttpd').is_file()
 result={'schema':'openmitrastar.modern-web-arc750/v2','status':'PASS_CURRENT_ARC_WEB_BUILD','hardware_accessed':False,'physical':'UNRUN','install':str(prefix),'checked':checked,'atomic_helper_sha256':sha(helper),'limits':['Physical TLS, dynamic loader, authenticated API and traffic unrun.']}
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
