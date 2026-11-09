"""Build current hostapd2.12 against the current ARC no-atomic libc/nl."""
import argparse,hashlib,json,os,re,shutil,subprocess
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser()
 for name in ['inputs','sysroot','nl-prefix','toolchain','output']:p.add_argument('--'+name,type=Path,required=True)
 p.add_argument('--wolf-prefix',type=Path,required=True)
 a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 record=next(r for r in json.loads((a.inputs/'manifest.json').read_text())['inputs'] if r['name']=='hostapd');assert sha(a.inputs/'hostapd.tar')==record['sha256']
 source=a.output/'source';shutil.copytree(record['source'],source)
 tc=str(a.toolchain/'bin/arc-snps-linux-uclibc-');assert sha(Path(tc+'gcc'))=='3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263'
 config='''CONFIG_DRIVER_NL80211=y
CONFIG_LIBNL_TINY=y
CONFIG_RSN_PREAUTH=y
CONFIG_IEEE80211N=y
CONFIG_NO_RADIUS=y
CONFIG_NO_ACCOUNTING=y
CONFIG_NO_VLAN=y
CONFIG_NO_AES_EXTRAS=y
CONFIG_NO_TKIP=y
CONFIG_TLS=wolfssl
CONFIG_DEBUG_FILE=y
CONFIG_WPS=y
CONFIG_SAE=y
CONFIG_OWE=y
CFLAGS += -DCONFIG_NO_HOSTAPD_LOGGER
'''
 config+='CFLAGS += --sysroot='+str(a.sysroot)+' -mcpu=arc700 -mno-lock -mno-atomic -mno-swape -Os -g0 -fstack-protector-strong -ffunction-sections -fdata-sections -I'+str(a.nl_prefix/'include/libnl-tiny')+' -D_GNU_SOURCE -ffile-prefix-map='+str(a.output)+'=/usr/src/hostapd-2.12\n'
 config+='CFLAGS += -I'+str(a.wolf_prefix/'include')+'\n'
 config+='LDFLAGS += --sysroot='+str(a.sysroot)+' -Wl,--gc-sections,-z,relro,-z,now -L'+str(a.wolf_prefix/'lib')+' -L'+str(a.nl_prefix/'lib')+'\nLIBS += -L'+str(a.wolf_prefix/'lib')+' -L'+str(a.nl_prefix/'lib')+'\n'
 (source/'hostapd/.config').write_text(config)
 env=os.environ|{'SOURCE_DATE_EPOCH':'1792694400','LC_ALL':'C','PKG_CONFIG_LIBDIR':str(a.nl_prefix/'lib/pkgconfig')}
 print('RUN current-hostapd2.12',flush=True)
 with (a.output/'build.log').open('xb') as f:r=subprocess.run(['make','-C',str(source/'hostapd'),'-j6','hostapd','hostapd_cli','CC='+tc+'gcc','AR='+tc+'ar','PKG_CONFIG=/bin/false'],stdout=f,stderr=subprocess.STDOUT,env=env,timeout=600)
 assert not r.returncode,(a.output/'build.log').read_text(errors='replace')[-6000:]
 rows=[]
 for name in ['hostapd','hostapd_cli']:
  output=a.output/name;shutil.copyfile(source/'hostapd'/name,output);subprocess.run([tc+'strip','--strip-unneeded',str(output)],check=True)
  asm=subprocess.check_output([tc+'objdump','-d',str(output)],text=True);assert not re.search(r'\t(?:swape|llock|scond)(?:\t| )',asm)
  dyn=subprocess.check_output([tc+'readelf','-d',str(output)],text=True)
  rows.append({'path':str(output),'bytes':output.stat().st_size,'sha256':sha(output),'needed':re.findall(r'\(NEEDED\).*\[([^]]+)\]',dyn),'forbidden_instructions':0})
 report={'schema':'openmitrastar.hostapd2026-build/v1','status':'PASS_CURRENT_HOSTAPD_BUILD','hardware_accessed':False,'physical':'UNRUN','source':record,'config_sha256':sha(source/'hostapd/.config'),'artifacts':rows,'limits':['Physical nl80211/AP/WPA2/WPA3/client traffic unrun.']}
 (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
