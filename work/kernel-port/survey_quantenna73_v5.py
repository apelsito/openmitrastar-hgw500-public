"""Build real7.3 packet/WEXT context and port remaining5GHz API uses offline."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import hashlib,json,os,re,shlex,shutil,subprocess
BASE=Path('/home/rea/openmitrastar-linux73-20261022T135100Z')
OLD=BASE/'quantenna73-api-survey-v3';OUT=BASE/'quantenna73-api-survey-v5'
PARENT=BASE/'radioeth73-events-ram-v2'
TC=str(BASE/'toolchain-arc700/bin/arc-snps-linux-uclibc-')

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def run(args,name,env=None):
 print('RUN '+name,flush=True)
 with (OUT/name).open('xb') as log:subprocess.run(args,stdout=log,stderr=subprocess.STDOUT,env=env,check=True,timeout=1800)
def main():
 if OUT.exists():raise RuntimeError('Immutable survey exists')
 OUT.mkdir(mode=0o700)
 for folder in ['source','headers','compat','legacy','port-context']:shutil.copytree(OLD/folder,OUT/folder)
 kernel=OUT/'kernel';context=OUT/'kernel-context'
 run(['cp','-a','--reflink=auto',str(PARENT/'source'),str(kernel)],'copy-kernel.log')
 run(['cp','-a','--reflink=auto',str(PARENT/'a'),str(context)],'copy-context.log')
 shutil.copyfile(OLD/'kernel-overrides/linux/skbuff.h',kernel/'include/linux/skbuff.h')
 for name in ['openmitrastar_qtn_skb.h','openmitrastar_bridge.h']:
  shutil.copyfile(OUT/'compat/linux'/name,kernel/'include/linux'/name)
 netdevice=kernel/'include/linux/netdevice.h'
 text=netdevice.read_text();needle='\tNET_DEV_STAT(tx_compressed);\n'
 assert text.count(needle)==1
 text=text.replace(needle,needle+''.join('\tNET_DEV_STAT('+name+');\n' for name in ['rx_unicast_packets','tx_unicast_packets','tx_multicast_packets','rx_broadcast_packets','tx_broadcast_packets']),1)
 needle='\tu8\t\t\tpriv[] ____cacheline_aligned'
 assert text.count(needle)==1
 text=text.replace(needle,'\t/* Native Quantenna per-interface policy bits. */\n\tu32 qtn_flags;\n\n'+needle,1)
 netdevice.write_text(text)
 # Public rtnetlink conversion copies only the upstream prefix. Quantenna's
 # appended counters stay private; never overwrite newer standard counters.
 core=kernel/'net/core/dev.c'
 t=core.read_text()
 old='size_t i, n = sizeof(*netdev_stats) / sizeof(atomic_long_t);'
 assert t.count(old)==1
 t=t.replace(old,'size_t i, n = offsetof(struct net_device_stats, rx_unicast_packets) / sizeof(atomic_long_t);',1)
 core.write_text(t)
 # Hidden WEXT/I2C options are selected by the actual Topaz radio integration,
 # without weakening signed regdb, channel or CPU restrictions.
 kconfig=kernel/'arch/arc/plat-topaz-basic/Kconfig'
 text=kconfig.read_text();needle='    select HAVE_PCI\n';assert text.count(needle)==1
 text=text.replace(needle,needle+'    select WIRELESS_EXT\n    select WEXT_PRIV\n    select I2C\n',1);kconfig.write_text(text)
 cfg=(context/'.config').read_text()
 cfg+='\nCONFIG_GPIOLIB=y\nCONFIG_GPIO_SYSFS=y\n'
 (context/'.config').write_text(cfg)
 env=os.environ|{'SOURCE_DATE_EPOCH':'1792365298','KBUILD_BUILD_TIMESTAMP':'@1792365298','KBUILD_BUILD_USER':'openmitrastar','KBUILD_BUILD_HOST':'radio73','KBUILD_BUILD_VERSION':'1'}
 make=['make','-C',str(kernel),'O='+str(context),'ARCH=arc','CROSS_COMPILE='+TC]
 run(make+['olddefconfig'],'olddefconfig.log',env)
 config=(context/'.config').read_text()
 for flag in ['CONFIG_WIRELESS_EXT=y','CONFIG_WEXT_PRIV=y','CONFIG_I2C=y','CONFIG_EPOLL=y']:assert flag in config,flag
 run(make+['KCFLAGS=-ffile-prefix-map='+str(context)+'=/quantenna73-context','-j6','vmlinux','dtbs'],'kernel-build.log',env)
 # Kernel-file helper already uses kernel_read/kernel_write. Remove obsolete
 # address-limit switches only; no replacement stub or access widening.
 for name in ['qdrv_control.c','qdrv_comm.c']:
  f=OUT/'source/qdrv'/name;t=f.read_text()
  t=re.sub(r'^\s*mm_segment_t (?:OldFs|old_fs);\n','\n',t,flags=re.M)
  t=re.sub(r'^\s*(?:OldFs|old_fs) = get_fs\(\);\n','\n',t,flags=re.M)
  t=re.sub(r'^\s*set_fs\((?:KERNEL_DS|OldFs|old_fs)\);\n','\n',t,flags=re.M)
  f.write_text(t)
 # Current tracepoint API appends _tp; preserve registration/provider spelling.
 for folder in ['source/qdrv','source/wlan']:
  for f in (OUT/folder).glob('*.c'):
   t=f.read_text()
   for name in ['ippkt_dropped','ippkt_check']:t=re.sub(r'\btrace_'+name+r'\(', 'trace_'+name+'_tp(',t)
   t=t.replace('netif_napi_add(', 'netif_napi_add_weight(')
   t=re.sub(r'\bdev_deactivate\(([^,()]+)\)',r'dev_deactivate(\1, true)',t)
   t=t.replace('qd->bstats.packets','u64_stats_read(&qd->bstats.packets)')
   f.write_text(t)
 # Keep const sysctl descriptions immutable. Each handler gets a local table
 # for its temporary stack data; this also removes a shared-data-pointer race.
 f=OUT/'source/wlan/ieee80211_linux.c';t=f.read_text()
 pattern=r'(IEEE80211_SYSCTL_DECL\([^)]*\)\n\{)'
 t,n=re.subn(pattern,r'\1\n\tstruct ctl_table ctl_local = *ctl;\n\tctl = &ctl_local;',t);assert n==6,n
 start=t.index('\t/*\n\t * Setup the table hierarchy.') if '\t/*\n\t * Setup the table hierarchy.' in t else t.index('#if LINUX_VERSION_CODE < KERNEL_VERSION(2,6,35)\n\tvap->iv_sysctls[0]')
 end=t.index('\tvap->iv_disconn_cnt = 0;',start)
 prefix=t[:start]
 # Retain allocated table/devname owners in the original cleanup path, but
 # replace removed child nodes with explicit net/<ifname> registration.
 registration='''
\tmemcpy(vap->iv_sysctls, ieee80211_sysctl_template,
\t\tsizeof(ieee80211_sysctl_template));
\tfor (i = 0; vap->iv_sysctls[i].procname; i++)
\t\tif (vap->iv_sysctls[i].extra1 == NULL)
\t\t\tvap->iv_sysctls[i].extra1 = vap;
\tvap->iv_sysctls[i-1].data = "";
\t{
\t\tchar path[IFNAMSIZ + 5];
\t\tsnprintf(path, sizeof(path), "net/%s", devname);
\t\tvap->iv_sysctl_header = register_sysctl_sz(path,
\t\t\tvap->iv_sysctls, ARRAY_SIZE(ieee80211_sysctl_template) - 1);
\t}
\tif (!vap->iv_sysctl_header) {
\t\tprintk("%s: failed to register sysctls!\\n", vap->iv_dev->name);
\t\tkfree(vap->iv_sysctls);
\t\tvap->iv_sysctls = NULL;
\t}
'''
 t=prefix+registration+t[end:]
 # The legacy detach frees its devname through table[2].procname; preserve
 # that owner explicitly until typed VAP owner integration is qualified.
 t=t.replace('kfree(vap->iv_sysctls[2].procname);','/* Path owner released after registration. */').replace('kfree((void *)vap->iv_sysctls[2].procname);','/* Path owner released after registration. */')
 # The existing devname allocation must be released after registration, as
 # the new API copies its path synchronously.
 t=t.replace('\tvap->iv_disconn_cnt = 0;','\tkfree(devname);\n\tvap->iv_disconn_cnt = 0;',1)
 f.write_text(t)
 # Const signatures in the shared compatibility header, with mutable handler
 # working table local to each call above.
 for folder in ['port-context','legacy']:
  f=OUT/folder/'drivers/include/kernel/net80211/ieee80211_linux.h';t=f.read_text()
  t=t.replace('f(struct ctl_table *ctl, int write,','f(const struct ctl_table *ctl, int write,')
  t=t.replace('struct bin_attribute * bin_attr,','const struct bin_attribute * bin_attr,')
  f.write_text(t)
 # Const pointer reassignment to local mutable table is valid, member writes
 # must address the local object while proc_dointvec accepts const input.
 f=OUT/'source/wlan/ieee80211_linux.c';t=f.read_text().replace('ctl->data =','ctl_local.data =').replace('ctl->maxlen =','ctl_local.maxlen =');f.write_text(t)
 for module,name,header in [('qdrv','qdrv_tx.c','net/gso.h'),('wlan','ieee80211_wireless.c','linux/of.h'),('qdrv','qdrv_wlan.c','linux/gpio/consumer.h')]:
  f=OUT/'source'/module/name;t=f.read_text();f.write_text('#include <'+header+'>\n'+t)
 # Numeric GPIO sysfs export stays an explicit configured kernel API.
 f=OUT/'source/qdrv/qdrv_wlan.c';t=f.read_text().replace('gpio_export(', 'gpiod_export(gpio_to_desc(')
 # Correct the two-argument call shape by preserving the exact numeric pin.
 t=re.sub(r'gpiod_export\(gpio_to_desc\(([^,\n]+),\s*([^)]*)\)',r'gpiod_export(gpio_to_desc(\1), \2)',t)
 f.write_text(t)
 base=shlex.split((context/'arch/arc/kernel/.reset.o.cmd').read_text().splitlines()[0].split(' := ',1)[1]);base=[x for x in base[:base.index('-c')] if not x.startswith('-Wp,-MMD,')]
 prior=json.loads((OLD/'compile-base.json').read_text());extras=prior[prior.index('-DMODULE'):]
 extras=[x.replace(str(OLD),str(OUT)) for x in extras]
 base+=extras
 (OUT/'compile-base.json').write_text(json.dumps(base,indent=2)+'\n')
 old=json.loads((OLD/'result.json').read_text());jobs=old['rows']
 def compile(record):
  module=record['module'];name=record['unit'];folder=OUT/'objects'/module;folder.mkdir(parents=True,exist_ok=True)
  oldcmd=json.loads((OLD/'objects'/module/(name+'.command.json')).read_text());src=Path(oldcmd[-1].replace(str(OLD),str(OUT)))
  cmd=base+(['-DQTN_DYN_CCA=1'] if module=='wlan' else [])+['-DKBUILD_BASENAME="'+name+'"','-DKBUILD_MODNAME="'+module+'"','-c','-o',str(folder/(name+'.o')),str(src)]
  (folder/(name+'.command.json')).write_text(json.dumps(cmd,indent=2)+'\n');r=subprocess.run(cmd,cwd=context,capture_output=True,text=True,timeout=120);(folder/(name+'.stderr')).write_text(r.stderr)
  errors=[l for l in r.stderr.splitlines() if re.search(r'error:|fatal error:',l)]
  row={'module':module,'unit':name,'exit':r.returncode,'errors':errors[:24]}
  if not r.returncode:row.update(bytes=(folder/(name+'.o')).stat().st_size,sha256=sha(folder/(name+'.o')))
  print(json.dumps({'module':module,'unit':name,'compiled':r.returncode==0,'first_error':errors[:1]}),flush=True);return row
 with ThreadPoolExecutor(max_workers=4) as pool:rows=list(pool.map(compile,jobs))
 result={'status':'QUANTENNA73_REAL_CONTEXT_COMPILE_SURVEY','compiled':sum(r['exit']==0 for r in rows),'failed':sum(r['exit']!=0 for r in rows),'units':len(rows),'rows':rows,'kernel_vmlinux_sha256':sha(context/'vmlinux'),'kernel_config_sha256':sha(context/'.config'),'hardware_accessed':False,'firmware_eligible':False,'whole_kernel_rebuilt':True,'module_link':'UNRUN','limits':['Real7.3 header/layout build; shipped19radio modules require rebuild against this kernel before any image use.','Sysctl lifetime/packet copy and API semantic fixtures pending; compile count is not5GHz radio proof.']}
 (OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['status','compiled','failed','units']}))
if __name__=='__main__':main()
