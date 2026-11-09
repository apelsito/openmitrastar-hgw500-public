"""Build BusyBox and Dropbear current releases with shared no-atomic ARC libc."""
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

def run(command,path,env,cwd=None,input=None):
 print('RUN '+path.name,flush=True)
 with path.open('xb') as f:subprocess.run(command,stdout=f,stderr=subprocess.STDOUT,input=input,env=env,cwd=cwd,check=True,timeout=900)

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['inputs','extra-inputs','sysroot','toolchain','output']:p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--component',choices=['busybox','dropbear'],required=True)
 a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 inputs=a.inputs if a.component=='busybox' else a.extra_inputs
 record=next(r for r in json.loads((inputs/'manifest.json').read_text())['inputs'] if r['name']==a.component)
 assert sha(inputs/(a.component+'.tar'))==record['sha256']
 source=a.output/'source';shutil.copytree(record['source'],source)
 tc=str(a.toolchain/'bin/arc-snps-linux-uclibc-')
 assert sha(Path(tc+'gcc'))=='3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263'
 config=(a.sysroot/'usr/include/bits/uClibc_config.h').read_text();assert '#undef __CONFIG_ARC_HAS_ATOMICS__' in config
 flags='--sysroot='+str(a.sysroot)+' -mcpu=arc700 -mno-lock -mno-atomic -mno-swape -Os -fstack-protector-strong -ffunction-sections -fdata-sections -ffile-prefix-map='+str(a.output)+'=/usr/src/'+a.component
 ldflags='--sysroot='+str(a.sysroot)+' -Wl,--gc-sections,-z,relro,-z,now'
 env=os.environ|{'SOURCE_DATE_EPOCH':'1792694400','LC_ALL':'C','CC':tc+'gcc','AR':tc+'ar','RANLIB':tc+'ranlib','STRIP':tc+'strip','CFLAGS':flags,'LDFLAGS':ldflags}
 if a.component=='busybox':
  make=['make','-C',str(source),'CROSS_COMPILE='+tc]
  run(make+['defconfig'],a.output/'config.log',env)
  text=(source/'.config').read_text()
  settings={'STATIC':'n','PIE':'y','CROSS_COMPILER_PREFIX':'"'+tc+'"','SYSROOT':'"'+str(a.sysroot)+'"','EXTRA_CFLAGS':'"'+flags+'"','EXTRA_LDFLAGS':'"'+ldflags+'"',
   'HTTPD':'n','TELNET':'n','TELNETD':'n','TFTP':'n','TFTPD':'n','FTPGET':'n','FTPPUT':'n','FTPD':'n','NC':'n','NETCAT':'n','WGET':'n',
   'RDATE':'n','RLOGIN':'n','RSH':'n','SHA256SUM':'y','INSMOD':'y','FEATURE_CMDLINE_MODULE_OPTIONS':'y','ASH':'y','AWK':'y','SED':'y','IP':'y','FEATURE_IP_ADDRESS':'y','FEATURE_IP_LINK':'y','FEATURE_IP_ROUTE':'y','SWITCH_ROOT':'y','INIT':'y','FEATURE_INIT_SYSLOG':'n'}
  for key,value in settings.items():
   text=re.sub(r'(?m)^(?:CONFIG_'+key+r'=.*|# CONFIG_'+key+r' is not set)\n','',text)
   text+=('# CONFIG_'+key+' is not set\n') if value=='n' else 'CONFIG_'+key+'='+value+'\n'
  (source/'.config').write_text(text)
  # Current libc omits the obsolete mktemp API. Preserve the applet's dry-run
  # result via safe creation, close and unlink, while retaining mkstemp/mkdtemp.
  temp=source/'coreutils/mktemp.c';s=temp.read_text();anchor="\t\tchp = mktemp(chp);\n\t\tif (chp[0] == '\\0')\n\t\t\tgoto error;"
  assert s.count(anchor)==1
  temp.write_text(s.replace(anchor,'\t\tint fd = mkstemp(chp);\n\t\tif (fd < 0)\n\t\t\tgoto error;\n\t\tclose(fd);\n\t\tif (unlink(chp) != 0)\n\t\t\tgoto error;'))
  # Same exported UAPI as the configured Linux kernel; no device writes.
  headers=a.sysroot.parent.parent/'radio2g73-build-v1/source/include/uapi/mtd'
  if not headers.exists():headers=a.sysroot.parents[2]/'radio2g73-build-v1/source/include/uapi/mtd'
  assert headers.is_dir();shutil.copytree(headers,source/'include/mtd')
  run(make+['oldconfig'],a.output/'oldconfig.log',env,input=b'\n'*8192)
  run(make+['-j6'],a.output/'build.log',env)
  binary=source/'busybox';final=source/'.config';programs=['busybox']
 else:
  # Preserve modern SSH with key authentication; disable legacy transport crypto.
  options='''#define DROPBEAR_X11FWD 0
#define DROPBEAR_SVR_AGENTFWD 0
#define DROPBEAR_CLI_AGENTFWD 0
#define DROPBEAR_CLI_PROXYCMD 0
#define DROPBEAR_CLI_NETCAT 0
#define DROPBEAR_DSS 0
#define DROPBEAR_3DES 0
#define DROPBEAR_ENABLE_CBC_MODE 0
#define DROPBEAR_SHA1_HMAC 0
#define DROPBEAR_RSA_SHA1 0
#define DROPBEAR_DH_GROUP1 0
#define DROPBEAR_DH_GROUP14_SHA1 0
#define DROPBEAR_SVR_PASSWORD_AUTH 0
#define DROPBEAR_SVR_PAM_AUTH 0
#define DROPBEAR_SMALL_CODE 1
'''
  (source/'localoptions.h').write_text(options)
  run([str(source/'configure'),'--host=arc-snps-linux-uclibc','--disable-zlib','--enable-bundled-libtom','--disable-syslog','--disable-lastlog','--disable-utmp','--disable-utmpx','--disable-wtmp','--disable-wtmpx'],a.output/'configure.log',env,cwd=source)
  run(['make','-C',str(source),'-j6','PROGRAMS=dropbear dropbearkey','MULTI=1'],a.output/'build.log',env)
  binary=source/'dropbearmulti';final=source/'localoptions.h';programs=['dropbear','dropbearkey']
 artifact=a.output/binary.name;shutil.copyfile(binary,artifact)
 subprocess.run([tc+'strip','--strip-unneeded',str(artifact)],check=True)
 asm=subprocess.check_output([tc+'objdump','-d',str(artifact)],text=True)
 assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm),artifact
 elf=subprocess.check_output([tc+'readelf','-l','-d',str(artifact)],text=True)
 needed=re.findall(r'\(NEEDED\).*\[([^]]+)\]',elf)
 report={'schema':'openmitrastar.current-tools-arc750/v1','status':'PASS_CURRENT_TOOL_BUILD_NO_FORBIDDEN_INSTRUCTIONS','component':a.component,'source':record,
  'hardware_accessed':False,'physical':'UNRUN','artifact':str(artifact),'bytes':artifact.stat().st_size,'sha256':sha(artifact),'needed':needed,
  'programs':programs,'config_sha256':sha(final),'sysroot':str(a.sysroot),'limits':['Physical dynamic loader, commands and SSH negotiation unrun.']}
 (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
