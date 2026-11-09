"""Run the actual diagnostic body with RTNL/reset/descriptor safety fixtures."""
from pathlib import Path
import argparse
import importlib.util
import hashlib
import json
import re
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 spec=importlib.util.spec_from_file_location('base',ROOT/'work/kernel-port/linux-7.3-ethernet-v1/test_lifecycle.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
 source=a.candidate/'driver/qtn-topaz-emac-eth73.c';body=base.extract(source.read_text(),'qtn_emac_txdiag')
 assert 'qtn_emac_write' not in body and 'writel' not in body
 header=(a.candidate/'driver/topaz-ethernet.h').read_text()
 names=set(re.findall(r'\bQTN_[A-Z0-9_]+',body))
 definitions='\n'.join(line for line in header.splitlines() if any(re.match(r'#define\s+'+re.escape(name)+r'\s',line) for name in names))
 definitions+='\n#define QTN_TOPAZ_EMAC_TX_RING_COUNT 64\n'
 fixture=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdbool.h>
#include <stdarg.h>
#include <sys/types.h>
#include <stdlib.h>
#include <errno.h>
typedef uint32_t u32; typedef uint16_t u16;
#define BIT(n) (1U<<(n))
#define GENMASK(h,l) ((~0U<<(l))&(~0U>>(31-(h))))
#define READ_ONCE(v) (v)
struct qtn_topaz_emac_desc {u32 status,control,bufaddr1,bufaddr2;};
struct qtn_topaz_emac {unsigned mac_id,phy_addr,active_speed,active_full_duplex;u16 tx_head,tx_tail;struct qtn_topaz_emac_desc *tx_descs;};
struct net_device {struct qtn_topaz_emac *priv;};
static unsigned checks,reads,desc_reads,unlocks;static bool lock_available=true,locked;static u32 registers[256];
#define CHECK(v) do{checks++;if(!(v)){fprintf(stderr,"FAIL %u\n",__LINE__);exit(1);}}while(0)
static bool rtnl_trylock(void){CHECK(!locked);if(!lock_available)return false;locked=true;return true;}
static void rtnl_unlock(void){CHECK(locked);locked=false;unlocks++;}
static void *netdev_priv(struct net_device *n){return n->priv;}
static u32 qtn_emac_read(struct qtn_topaz_emac *e,u32 r){(void)e;CHECK(locked&&r<0x400&&(r&3)==0);reads++;return registers[r/4];}
static u32 qtn_desc_read(const u32 *p){CHECK(locked);desc_reads++;return *p;}
static ssize_t sysfs_emit(char *p,const char *format,...){va_list a;va_start(a,format);int n=vsnprintf(p,4096,format,a);va_end(a);return n;}
'''
 fixture+=definitions+'\n'+body+'\n'
 fixture+=r'''
int main(void){
 char buffer[4096];struct qtn_topaz_emac_desc descriptors[64];struct qtn_topaz_emac e={.tx_descs=descriptors,.active_speed=1000};struct net_device n={.priv=&e};
 for(unsigned t=0;t<256;t++){
  for(unsigned i=0;i<256;i++)registers[i]=0x30000000U+i*2+t*4;
  registers[QTN_EMAC_DMA_CONFIG/4]=0x48020;
  for(unsigned i=0;i<64;i++){descriptors[i].status=0x80000000U+i;descriptors[i].control=i*10;}
  e.tx_head=t%64;e.tx_tail=(t*3)%64;e.mac_id=t%2;e.phy_addr=e.mac_id?3:1;
  u32 prior[256];for(unsigned i=0;i<256;i++)prior[i]=registers[i];
  reads=desc_reads=unlocks=0;ssize_t size=qtn_emac_txdiag(&n,buffer);
  CHECK(size>0&&size<4096&&!locked&&unlocks==1&&desc_reads==4);
  for(unsigned i=0;i<256;i++)CHECK(registers[i]==prior[i]);
 }
 reads=desc_reads=unlocks=0;lock_available=false;CHECK(qtn_emac_txdiag(&n,buffer)==-EBUSY);CHECK(!reads&&!desc_reads&&!unlocks);
 lock_available=true;registers[QTN_EMAC_DMA_CONFIG/4]=1;CHECK(qtn_emac_txdiag(&n,buffer)==-EBUSY);CHECK(reads==1&&!desc_reads&&unlocks==1&&!locked);
 registers[QTN_EMAC_DMA_CONFIG/4]=0;reads=desc_reads=unlocks=0;e.tx_descs=NULL;CHECK(qtn_emac_txdiag(&n,buffer)==-ENODEV);CHECK(!desc_reads&&unlocks==1&&!locked);
 e.tx_descs=descriptors;e.tx_tail=64;CHECK(qtn_emac_txdiag(&n,buffer)==-ENODEV);CHECK(!desc_reads&&!locked);
 e.tx_tail=0;e.tx_head=64;CHECK(qtn_emac_txdiag(&n,buffer)==-ENODEV);CHECK(!desc_reads&&!locked);
 CHECK(qtn_emac_txdiag(NULL,buffer)==-ENODEV);
 printf("TXDIAG_PASS cases=262 checks=%u\n",checks);return 0;
}
'''
 (a.output/'fixture.c').write_text(fixture,newline='\n')
 c=subprocess.run(['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined',str(a.output/'fixture.c'),'-o',str(a.output/'fixture')],capture_output=True);assert not c.returncode,c.stderr.decode()
 r=subprocess.run([str(a.output/'fixture')],capture_output=True);assert not r.returncode,r.stderr.decode()
 result={'schema':'openmitrastar.radioeth73-txdiag-fixture/v1','status':'PASS_ACTUAL_READONLY_DIAGNOSTIC','hardware_accessed':False,'physical':'UNRUN','stdout':r.stdout.decode(),'driver_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'limits':['Fake register/RTNL fixture; physical silicon and sysfs concurrency unrun.']}
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
