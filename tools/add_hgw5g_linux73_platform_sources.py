"""Carry original/versioned nativeprovider sources into7.3jointKbuild, noobjects."""
import argparse,hashlib,json,shutil
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--parent',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();root=Path(__file__).resolve().parents[1];shutil.copytree(a.parent,a.output);records=[]
 topaz=root/'work/linux510-radio-port/quantenna-f344-peers/platform/topaz';ruby=root/'work/linux510-radio-port/quantenna/platform/ruby';bounded=root/'outputs/rea/driver5g-ops-20261022-tqe-r4-typed-queue-source-r8';qtsens=root/'work/linux510-radio-port/quantenna/platform/qtsens';mapping={}
 for n in('hbm.c','temp_sens.c','switch_vlan.c','fwt_if.c'):mapping['source/platform/topaz/'+n]=topaz/n
 for n in('switch_tqe.c','topaz_congest_queue.c','openmitrastar_tqe_bounded_ownership.h'):mapping['source/platform/topaz/'+n]=bounded/n
 for n in('gpio.c','gpio.h','iputil.c','dmautil.c','dma_cache_ops.h','emac_lib.h','arasan_emac_ahb.h','ar823x.h','mv88e6071.h','spi_api.h'):mapping['source/platform/ruby/'+n]=ruby/n
 mapping['source/platform/qtsens/temp_sensor.c']=qtsens/'temp_sensor.c'
 for rel,src in mapping.items():dst=a.output/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst);records.append({'path':rel,'source':str(src),'sha256':sha(dst)})
 # C99 inline alone doesnotemitcalledlocalfunction inmodernkernelgnu11.
 rel='source/wlan/ieee80211_output.c';f=a.output/rel;t=f.read_text();needle='__inline void ieee80211_ppqueue_release_entry(';assert t.count(needle)==1;t=t.replace(needle,'static inline void ieee80211_ppqueue_release_entry(',1);f.write_text(t,newline='\n');k=a.output/'Kbuild';t=k.read_text();t+='\nccflags-y += -DCONFIG_TOPAZ=1 -I$(src)/source/platform/ruby\n';mods={'hbm':'topaz/hbm','temp_sens':'topaz/temp_sens','switch_vlan':'topaz/switch_vlan','fwt_if':'topaz/fwt_if','switch_tqe':'topaz/switch_tqe','topaz_congest_queue':'topaz/topaz_congest_queue','gpio':'ruby/gpio','iputil':'ruby/iputil','dmautil':'ruby/dmautil','qtn_tsens':'qtsens/temp_sensor'}
 for name,path in mods.items():t+=name+'-y := source/platform/'+path+'.o\n'
 t+='obj-m += '+' '.join(n+'.o'for n in mods)+'\n';k.write_text(t,newline='\n');proof=json.loads((a.parent/'result.json').read_text());proof.update(status='SOURCE_ONLY_LINUX73_FULL44_NATIVE_PROVIDER_SOURCE_CLOSURE_PENDING_BUILD',parent=str(a.parent),native_provider_sources=records,changed_sources={rel:sha(f),'Kbuild':sha(k)},kbuild_sha256=sha(k));proof['files']={str(x.relative_to(a.output)):sha(x)for group in('source','headers','kernel-overlay','providers')for x in(a.output/group).rglob('*')if x.is_file()};(a.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({'status':proof['status'],'new_native_providers':list(mods),'sources':len(records),'kbuild_sha256':sha(k)},indent=2))
if __name__=='__main__':main()
