"""Offline exact-binary disassembly and native CLI bodies with fake syscalls."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shlex,shutil,subprocess
ROOT=Path(__file__).resolve().parents[1]
LOADER_SHA='8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6'
BUSYBOX_SHA='537b409a13db65380cebff31a24b2cfe8d9ebe38678b35fe6c205db080c5773d'
WSL='podman-mem9-tidb'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def read_wsl(path):return subprocess.run(['wsl.exe','-d',WSL,'-u','root','-e','cat',path],capture_output=True,check=True).stdout
def function(text,name):
 m=re.search(r'(?:void|int|char\*) (?:FAST_FUNC )?'+name+r'\([^;]*?\)\s*\{',text);assert m,name
 start=m.start();i=m.end();depth=1
 while depth:
  if text[i]=='{':depth+=1
  elif text[i]=='}':depth-=1
  i+=1
 return text[start:i]
def run(out):
 assert shutil.disk_usage('C:/').free>500*1024*1024
 out=Path(out);out.mkdir(parents=True,exist_ok=False)
 loader=out/'ram-insmod-qtn';loader.write_bytes(read_wsl('/home/user/openmitrastar-build/f168-verify-cand/usr/sbin/ram-insmod-qtn'))
 busy=out/'busybox-f340';busy.write_bytes(read_wsl('/home/user/openmitrastar-build/f168-verify-cand/bin/busybox'))
 assert sha(loader)==LOADER_SHA and loader.stat().st_size==816 and sha(busy)==BUSYBOX_SHA
 assert busy.read_bytes()[0x3ee30]==0
 tc=linux(ROOT/'work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-objdump')
 for path,start,end,name in [(loader,'0x100a8','0x10138','loader.disasm'),(busy,'0x12490','0x124d8','busybox-insmod.disasm')]:
  r=subprocess.run(['wsl.exe','-d',WSL,'-u','root','-e',tc,'-d','--start-address='+start,'--stop-address='+end,linux(path)],capture_output=True,check=True);(out/name).write_bytes(r.stdout)
 dis=(out/'loader.disasm').read_text();bd=(out/'busybox-insmod.disasm').read_text()
 assert re.search(r'100d6:.*ld_s\s+r12,\[r1,0xc\]',dis) and re.search(r'10104:.*mov_s\s+r1,r12',dis)
 assert len(re.findall(r'mov\s+r8,273',dis))==1 and 'init_module' not in dis
 assert re.search(r'124a6:.*mov\s+r1,0x4ee30',bd) and re.search(r'124b0:.*bl.*0x1256c',bd)
 source=(ROOT/'tools/ram_insmod_nolibc.c').read_text();(out/'ram_insmod_nolibc.c').write_bytes(source.encode())
 native=r'''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef unsigned long om_word;
#define OM_NR_OPENAT 56
#define OM_NR_CLOSE 57
#define OM_NR_FINIT_MODULE 273
#define OM_AT_FDCWD (-100)
#define OM_O_RDONLY 0
#define OM_O_CLOEXEC 02000000
static unsigned opens,loads,closes;static const char *params="";
static long om_syscall4(long n,long a,long b,long c,long d){if(n!=56||a!=-100||!b||c!=OM_O_CLOEXEC||d)exit(90);opens++;return getenv("OPEN_FAIL")?-2:7;}
static long om_syscall3(long n,long a,long b,long c){if(n!=273||a!=7||!b||c)exit(91);loads++;params=(const char*)b;return getenv("LOAD_FAIL")||!params[0]?-13:0;}
static long om_syscall1(long n,long a){if(n!=57||a!=7)exit(92);closes++;return 0;}
static void om_puts(const char*s){fputs(s,stdout);}
__attribute__((noreturn)) static void om_exit(long status){printf("FAKE_RESULT opens=%u loads=%u closes=%u params=%s\n",opens,loads,closes,params);exit((int)status);}
'''+function(source,'ram_insmod_main')+r'''
int main(int argc,char**argv){om_word stack[16];int i;if(argc>12)return 3;stack[0]=(om_word)argc;for(i=0;i<argc;i++)stack[i+1]=(om_word)argv[i];ram_insmod_main(stack);}
'''
 (out/'loader-native.c').write_bytes(native.encode())
 base='/home/user/openmitrastar-build/busybox-product-rootfs-src/modutils/'
 ins=read_wsl(base+'insmod.c').decode();mod=read_wsl(base+'modutils.c').decode();header=read_wsl(base+'modutils.h')
 (out/'insmod.c').write_bytes(ins.encode());(out/'modutils.c').write_bytes(mod.encode());(out/'modutils.h').write_bytes(header)
 busy_native=r'''#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define UNUSED_PARAM __attribute__((unused))
#define IF_FEATURE_2_4_MODULES(...)
#define FAST_FUNC
static void bb_show_usage(void){exit(2);}
static void bb_error_msg(const char*f,...){(void)f;}
static const char *moderror(int r){(void)r;return "fake";}
static int bb_init_module(const char*f,const char*p){(void)f;printf("PARAMS=%s\n",p);return *p?0:13;}
#if MODULE_OPTIONS
static void *xzalloc(size_t n){return calloc(1,n);}
static void *xrealloc(void*p,size_t n){return realloc(p,n);}
'''+function(mod,'parse_cmdline_module_options')+r'''
#else
#define parse_cmdline_module_options(a,b) ""
#endif
'''+function(ins,'insmod_main')+r'''
int main(int argc,char**argv){return insmod_main(argc,argv);}
'''
 (out/'busybox-native.c').write_bytes(busy_native.encode())
 q=shlex.quote;script=f'''set -eu
out={q(linux(out))}
cc -std=c11 -O2 -Wall -Wextra -Werror "$out/loader-native.c" -o "$out/loader-native"
cc -std=c11 -O2 -Wall -Wextra -Werror -DMODULE_OPTIONS=0 "$out/busybox-native.c" -o "$out/busybox-disabled"
cc -std=c11 -O2 -Wall -Wextra -Werror -DMODULE_OPTIONS=1 "$out/busybox-native.c" -o "$out/busybox-enabled"
'''
 (out/'build.sh').write_bytes(script.encode());r=subprocess.run(['wsl.exe','-d',WSL,'-u','root','-e','sh',linux(out/'build.sh')],capture_output=True)
 (out/'build.stdout').write_bytes(r.stdout);(out/'build.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode(errors='replace')
 cases=[]
 def case(name,binary,args,rc,fragment,env=None):
  argv=['wsl.exe','-d',WSL,'-u','root','-e']
  if env:argv+=['env',env]
  r=subprocess.run(argv+[linux(out/binary),*args],capture_output=True)
  ok=r.returncode==rc and fragment in r.stdout and not r.stderr
  cases.append({'name':name,'passed':ok,'exit_code':r.returncode,'stdout':r.stdout.decode('ascii')});assert ok,cases[-1]
 case('busybox-current-discards-param','busybox-disabled',['probe.ko','execute_read=1'],13,b'PARAMS=\n')
 case('busybox-enabled-source-keeps-param','busybox-enabled',['probe.ko','execute_read=1'],0,b'PARAMS=execute_read=1 \n')
 case('loader-single-positive','loader-native',['probe.ko','execute_read=1'],0,b'loads=1 closes=1 params=execute_read=1\n')
 case('loader-negative-default','loader-native',['probe.ko'],1,b'loads=1 closes=1 params=\n')
 case('loader-negative-no-fallback','loader-native',['probe.ko','execute_read=1'],1,b'loads=1 closes=1 params=execute_read=1\n','LOAD_FAIL=1')
 case('loader-open-fail-no-load','loader-native',['probe.ko','execute_read=1'],1,b'loads=0 closes=0 params=\n','OPEN_FAIL=1')
 case('loader-whole-string','loader-native',['probe.ko','first=1 second=2'],0,b'params=first=1 second=2\n')
 case('loader-extra-argv-rejected','loader-native',['probe.ko','first=1','second=2'],2,b'opens=0 loads=0 closes=0')
 report={'schema':'openmitrastar.f354-loader-proof/v1','status':'PASS_OFFLINE_EXACT_LOADER_ARGUMENTS','hardware_actions':False,'cases':cases,
  'loader':{'path':str(loader),'sha256':sha(loader),'bytes':loader.stat().st_size,'runtime_path':'/usr/sbin/ram-insmod-qtn'},
  'busybox':{'path':str(busy),'sha256':sha(busy),'bytes':busy.stat().st_size,'options_pointer':'0x4ee30','options_first_byte':0,'ignores_argv_after_filename':True},
  'source_template_note':'Current BusyBox source supports both feature branches; historical .config was not recovered. Exact installed disassembly proves disabled branch.',
  'production_loader_modified':False,'production_loader_finit_module_calls':1,'production_loader_init_module_fallback':False,
  'inputs':{str(ROOT/'tools/ram_insmod_nolibc.c'):sha(ROOT/'tools/ram_insmod_nolibc.c'),str(Path(__file__).resolve()):sha(__file__)}}
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='ascii');return report
def main():
 out=ROOT/'outputs/preflight'/('f354-loader-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));r=run(out);print(json.dumps({'status':r['status'],'result':str(out/'result.json'),'tests':len(r['cases'])}))
if __name__=='__main__':main()
