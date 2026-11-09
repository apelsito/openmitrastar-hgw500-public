"""Linux7.3 source-only port candidate from recoveredR9, no previousABI objects.

Pins exact current73context. Creates new guarded packet ABI overlay and complete
seven-module Kbuild. No activekernel/device/source mutation or downloads.
"""
import argparse,difflib,hashlib,json,shutil
from pathlib import Path
from witness_hgw5g_typed_vap_abi import split_struct
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--kernel',type=Path,required=True);p.add_argument('--context',type=Path,required=True);p.add_argument('--toolchain',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();cfg=a.context/'.config';sym=a.context/'Module.symvers';assert sha(cfg)=='2990fb628241fa6714dd41af73bd77f4e4df44f9b8eec37feda31c749818ef27';assert sha(sym)=='a9f74b04bf95ffb60954c61f12983d056dade9f8bb6b67d7e45cba5ddcee03a3';assert sha(a.toolchain/'bin/arc-snps-linux-uclibc-gcc')=='3918a0da3c9f2cfde359f6fed1d0df19e737438dfd2cc60edae63f2dcbf14263';conf=cfg.read_text();assert all('CONFIG_'+k+'=y'in conf for k in('ARC_CPU_750D','ARC_MMU_V2','ARC_PAGE_SIZE_8K','PREEMPT_NONE','ARC_PLAT_TOPAZ_BASIC'));assert '# CONFIG_MODULE_FORCE_UNLOAD is not set'in conf;root=Path(__file__).resolve().parents[1];a.output.mkdir(parents=True);shutil.copytree(a.parent/'source',a.output/'source');shutil.copytree(a.parent/'headers',a.output/'headers');overlay=a.output/'kernel-overlay';patch=[];changed={}
 def write(rel,text):
  f=overlay/rel;f.parent.mkdir(parents=True,exist_ok=True);old=(a.kernel/rel).read_text()if(a.kernel/rel).exists()else'';f.write_text(text,newline='\n');changed[rel]=sha(f);patch.extend(difflib.unified_diff(old.splitlines(True),text.splitlines(True),fromfile='a/'+rel,tofile='b/'+rel))
 # Packetfields livein the copied headersstructgroup, preservingclone/copy scope.
 rel='include/linux/skbuff.h';t=(a.kernel/rel).read_text();anchor='\tstruct_group(headers,\n';assert t.count(anchor)==1;fields='''
#ifdef CONFIG_OPENMITRASTAR_QDRV_COMPAT
        /* NativeTopazpacketcontract; includedin __copy_skb_header headersgroup. */
        struct qtn_skb_cb qtn_cb;
        struct net_device *orig_dev;
        struct qtn_skb_recycle_list *recycle_list;
        __u32 src_port,dest_port;
        __u8 is_recyclable:1,cache_is_cleaned:1,hbm_no_free:1,ext_l2_filter:1;
#endif
''';t=t.replace(anchor,anchor+fields,1);anchor='#include <linux/kernel.h>'
 if anchor not in t:anchor='#include <linux/compiler.h>'
 assert anchor in t;t=t.replace(anchor,anchor+'\n#ifdef CONFIG_OPENMITRASTAR_QDRV_COMPAT\n#include <linux/openmitrastar_qtn_skb.h>\n#endif',1);write(rel,t);write('include/linux/openmitrastar_qtn_skb.h',(root/'work/kernel-port/linux-5.10/include/linux/openmitrastar_qtn_skb.h').read_text())
 # Standardcounters prefix is unchanged; nativeunicast/broadcast countersappend.
 rel='include/linux/netdevice.h';t=(a.kernel/rel).read_text();body=split_struct(t,'struct net_device_stats {');old='struct net_device_stats {'+body+'}';assert old in t;new=old[:-1]+'''#ifdef CONFIG_OPENMITRASTAR_QDRV_COMPAT
        NET_DEV_STAT(rx_unicast_packets);NET_DEV_STAT(tx_unicast_packets);
        NET_DEV_STAT(tx_multicast_packets);NET_DEV_STAT(rx_broadcast_packets);
        NET_DEV_STAT(tx_broadcast_packets);
#endif
}''';t=t.replace(old,new,1);anchor='\tchar\t\t\tpriv[]';
 if anchor not in t:anchor='\tu8\t\t\tpriv[]'
 if anchor not in t:
  import re
  match=re.search(r'^[^\n]*\bpriv\[\][^\n]*',t,re.M);assert match;anchor=match.group()
 assert t.count(anchor)==1;t=t.replace(anchor,'#ifdef CONFIG_OPENMITRASTAR_QDRV_COMPAT\n        u32 qtn_flags;\n#endif\n'+anchor,1);write(rel,t)
 rel='net/core/dev.c';t=(a.kernel/rel).read_text();anchor='\tBUILD_BUG_ON(n > sizeof(*stats64) / sizeof(u64));';assert t.count(anchor)==1;t=t.replace(anchor,'#ifdef CONFIG_OPENMITRASTAR_QDRV_COMPAT\n\tn=min_t(size_t,n,sizeof(*stats64)/sizeof(u64));\n#else\n'+anchor+'\n#endif',1);write(rel,t)
 write('include/linux/openmitrastar_bridge.h',(root/'work/kernel-port/linux-5.10/include/linux/openmitrastar_bridge.h').read_text())
 write('net/wireless/Kconfig',(a.kernel/'net/wireless/Kconfig').read_text()+'''\nconfig OPENMITRASTAR_QDRV_COMPAT
    bool "OwnerHGW500Quantenna packetABI andlegacyWEXT"
    depends on ARC_PLAT_TOPAZ_BASIC
    select WIRELESS_EXT
    select WEXT_PRIV
    help
      Offlineowner portcandidate. Requires fullkernel/module pairedrebuild.
''')
 # Kbuildusesactual7.3 flags/toolchain config; no retained5.10 command reuse.
 gpl=root/'work/sources/Quantenna-GPL';mk='''# Linux7.3ownerQuantenna candidate; offlineonly.
QTN_GPL := '''+str(gpl)+'''
ccflags-y += -I$(src)/headers -I$(src)/source/wlan -I$(src)/source/qdrv
ccflags-y += -I$(src)/source/qdrv/compat/include -include $(src)/source/qdrv/compat/include/openmitrastar_qdrv_compat.h
ccflags-y += -I$(QTN_GPL) -I$(QTN_GPL)/drivers -I$(QTN_GPL)/drivers/ruby
ccflags-y += -I$(QTN_GPL)/include -I$(QTN_GPL)/drivers/include/shared -I$(QTN_GPL)/drivers/include/kernel -I$(QTN_GPL)/common
ccflags-y += -DQDRV -DQSCS_ENABLED -DQTN_BG_SCAN -DQBMPS_ENABLE -DCONFIG_ARCH_ARC=1 -DCONFIG_RUBY=1
ccflags-y += -DCONFIG_QTN_80211K_SUPPORT -DQTN_DYN_CCA=1 -DQTN_ENABLE_TRACE_BUFFER=0 -DQTN_DEBUG -mlong-calls -mno-millicode
ccflags-y += -DOPENMITRASTAR_QDRV_V89_PAIR=1 -DOPENMITRASTAR_QDRV_NO_IPV6_OFFLOAD -DOPENMITRASTAR_NO_LEGACY_PROC
ccflags-y += -Wall -Wno-error -Wno-unused-function -Wno-unused-variable -Wno-error=implicit-function-declaration
''';qnames=(a.parent/'source/qdrv/Makefile').read_text().split('qdrv-objs :=',1)[1].split('obj-m',1)[0].replace('\\',' ').split();wnames=['wlan_fwt_compat','if_media','ieee80211_beacon','ieee80211_beacon_desc','ieee80211_crypto','ieee80211_crypto_none','ieee80211_proto','ieee80211_output','ieee80211_power','ieee80211_scan','ieee80211_wireless','ieee80211_linux','ieee80211_rate','ieee80211_input','ieee80211_node','ieee80211_tdls','ieee80211_tpc','ieee80211_mlme_statistics','ieee80211'];mk+='qdrv-y := '+' '.join('source/qdrv/'+n for n in qnames)+'\n';mk+='wlan-y := '+' '.join('source/wlan/'+n+'.o'for n in wnames)+'\n';providers={'wlan_scan_ap':'ieee80211_scan_ap','wlan_scan_sta':'ieee80211_scan_sta','wlan_ccmp':'ieee80211_crypto_ccmp','wlan_tkip':'ieee80211_crypto_tkip','wlan_xauth':'ieee80211_xauth'}
 for c,n in providers.items():mk+=c+'-y := source/wlan/'+n+'.o\n'
 mk+='obj-m += qdrv.o wlan.o '+' '.join(c+'.o'for c in providers)+'\n';(a.output/'Kbuild').write_text(mk,newline='\n');(a.output/'kernel73-overlay.patch').write_text(''.join(patch),newline='\n');pins={str(x):sha(x)for x in [Path(__file__),cfg,sym,a.context/'include/generated/utsrelease.h',a.kernel/'Makefile',a.toolchain/'bin/arc-snps-linux-uclibc-gcc']};files={str(x.relative_to(a.output)):sha(x)for t in('source','headers','kernel-overlay')for x in(a.output/t).rglob('*')if x.is_file()};result=dict(status='SOURCE_ONLY_LINUX73_QDRV_R9_API_PORT_CANDIDATE_PENDING_KERNEL_MODULE_BUILD',hardware_accessed=False,firmware_eligible=False,parent=str(a.parent),kernel_source=str(a.kernel),context=str(a.context),toolchain=str(a.toolchain),pins=pins,files=files,kernel_overlay=changed,kbuild_sha256=sha(a.output/'Kbuild'),new_kernel_config_required=['OPENMITRASTAR_QDRV_COMPAT=y','WIRELESS_EXT=y','WEXT_CORE=y','WEXT_PRIV=y'],old_5_10_objects_used=False,limits=['No7.3compile/ABI/allmoduleclosure yet; packetABIrequiresentirekernel+19existingmodules rebuild.','Signedregdb/CPU750D/MMUv2/8K/noSMP/noForceUnload preservedrequired.','No5.10objectsorheaders reusedas7.3buildproof; sourceported only.','PMQoS/board/DMA/bridge/API residualintegration remainsunverified.','No hardware/RF/client/firmwareoperation.']);(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items()if k!='files'},indent=2))
if __name__=='__main__':main()
