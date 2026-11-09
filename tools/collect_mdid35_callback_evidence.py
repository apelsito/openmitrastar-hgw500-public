"""Exact OEM IC+0x5444 beacon callback mapping and current inherited lifetime paths."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
from qualify_f370_qdrv_module import Elf
from prepare_tqe_bounded_admission_prototype import function
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 original=ROOT/'work/hgw500-rootfs-live/squashfs-root/lib/modules/2.6.35.12/extra/qdrv/qdrv.ko';e=Elf(original);tc='/workspace/user-home/Desktop/MitraStar/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-snps-linux-uclibc-objdump';target='/workspace/user-home/Desktop/MitraStar/work/hgw500-rootfs-live/squashfs-root/lib/modules/2.6.35.12/extra/qdrv/qdrv.ko';r=subprocess.run(['wsl','-d','REA-Linux','--',tc,'-dr','--disassemble=qdrv_wlan_init',target],capture_output=True,text=True);assert not r.returncode;out=a.output/'oem-qdrv-wlan-init.objdump.txt';out.write_text(r.stdout)
 lines=r.stdout.splitlines();add=next(i for i,line in enumerate(lines)if '354ac:'in line);store=next(i for i,line in enumerate(lines)if '35544:'in line);assert 'add\tr14,r24,0x5444'in lines[add]and 'st\t0,[r14,0]'in lines[store]and '.text+0x288ec'in lines[store+1];excerpt='\n'.join(lines[add:store+2]);(a.output/'callback-mapping-excerpt.txt').write_text(excerpt+'\n')
 rr=next(x for x in e.relas if x['section']=='.text'and x['offset']==0x35548);sym=e.syms[rr['symbol']];assert e.symsection(sym)=='.text'and sym['value']+rr['addend']==0x288ec
 r=subprocess.run(['wsl','-d','REA-Linux','--',tc,'-dr','--start-address=0x288ec','--stop-address=0x28e5c',target],capture_output=True,text=True);assert not r.returncode;cb=a.output/'oem-anonymous-beacon-callback-288ec.objdump.txt';cb.write_text(r.stdout);assert all(x in r.stdout for x in ['ieee80211_beacon_create_param','ieee80211_beacon_alloc','ieee80211_beacon_flush_param','vnet_send_ioctl'])
 q=a.candidate/'source/qdrv/qdrv_wlan.c';v=a.candidate/'source/qdrv/qdrv_vap.c';t=q.read_text();bodies={}
 for signature in['static void qdrv_wlan_80211_beacon_update(struct ieee80211vap *vap)','void qdrv_wlan_beacon_vap_detach(struct qdrv_vap *qv)']:
  body=function(t,signature+'\n{');name=signature.split('(')[0].split()[-1];(a.output/(name+'.c')).write_text(body+'\n');bodies[name]=hashlib.sha256(body.encode()).hexdigest()
 assert 'ic->ic_beacon_update = qdrv_wlan_80211_beacon_update;' in t
 vt=v.read_text();assert 'alloc_netdev(sizeof(struct qdrv_vap)'in vt and 'memset(qv, 0, sizeof(struct qdrv_vap));'in vt;assert vt.index('qdrv_wlan_beacon_vap_detach(qv);')<vt.index('ieee80211_vap_detach(&qv->iv);',vt.index('qdrv_wlan_beacon_vap_detach(qv);'))
 pins={str(x):sha(x)for x in[Path(__file__),original,q,v,out,cb,a.output/'callback-mapping-excerpt.txt']};r={'status':'PASS_OEM_5444_ANONYMOUS_BEACON_CALLBACK_MAPPING_AND_INHERITED_SOURCE_LIFETIME_PATHS','hardware_accessed':False,'firmware_eligible':False,'OEM_qdrv_sha256':sha(original),'OEM_callback_entry':0x288ec,'OEM_callback_exact_name':None,'function_bodies':bodies,'pins':pins,'limits':['OriginalICoffset5444relocationmapsanonymousentry288ec; itscreate/alloc/flush/sendconsumerpathconfirmsbeaconupdatepurpose; exactsymbolnameabsent. Currenticcallbackassignsqdrv_wlan_80211_beacon_update.','Existingtxnqueue/dirty/quarantine/detachcancelpathsandVAPsizeofzeroingpreserved; noscheduling/DMA/RFexecutionbythisaudit.','494callbackHOSTAPlow16;495low8nocallback; invocationlifetimeisexistingcurrentdrivercontract.']};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
