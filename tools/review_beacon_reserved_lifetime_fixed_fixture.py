"""Independent32bit host fixture of actual candidate helpers, nohardware."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from prepare_hgw5g_beacon_descriptor_lifetime import function

ROOT=Path(__file__).resolve().parents[1]
PRE=r'''
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <assert.h>
#include <errno.h>
typedef uint32_t dma_addr_t;
#define EXPORT_SYMBOL(x)
#define BEACON_PARAM_SIZE 1000
struct beacon_shared_ie_t {dma_addr_t buf;uint8_t*lhost_buf;uint32_t size;uint32_t next_muc_addr;struct beacon_shared_ie_t*next;};
struct ieee80211_beacon_param_t {struct beacon_shared_ie_t*head,*tail;uint8_t buf[1000];uint32_t curr;uint16_t size;struct beacon_shared_ie_t*om_cca_ie,*om_app_ie;int om_build_error;};
static uint32_t plat_kernel_addr_to_dma(void*x,void*y){(void)x;return(uint32_t)(uintptr_t)y;}
'''
TEST=r'''
int main(void){
 struct ieee80211_beacon_param_t p={0};unsigned char payload[64]={0};
 _Static_assert(sizeof(struct beacon_shared_ie_t)==20,"32bitwire");
 p.curr=(uint32_t)(uintptr_t)p.buf;p.size=1000;
 p.om_cca_ie=ieee80211_beacon_alloc_ie(&p);p.om_app_ie=ieee80211_beacon_alloc_ie(&p);
 struct beacon_shared_ie_t*stat=ieee80211_beacon_alloc_ie(&p);
 ieee80211_beacon_associate_ie(stat,payload,20);p.head=p.tail=stat;
 assert(om_beacon_reserved_update(&p,p.om_app_ie,payload+20,4)==0);
 assert(om_beacon_reserved_update(&p,p.om_cca_ie,payload+20,8)==0);
 assert(om_beacon_reserved_update(&p,p.om_app_ie,payload+28,4)==0);
 unsigned n=0;int order_violation=0;uint8_t*previous=NULL;
 for(struct beacon_shared_ie_t*it=p.head;it;it=it->next){if(previous&&it->lhost_buf<previous)order_violation=1;previous=it->lhost_buf;n++;assert(n<=50);}
 int saved_error=p.om_build_error; int invalid_rc=om_beacon_reserved_update(&p,NULL,payload+20,8);
 int invalid_not_latched=invalid_rc<0&&p.om_build_error==0;
 p.om_build_error=saved_error; unsigned before=p.curr;
 for(unsigned i=0;i<10000;i++){assert(om_beacon_reserved_remove(&p,p.om_cca_ie)==0);assert(om_beacon_reserved_update(&p,p.om_cca_ie,payload+20,8)==0);}
 assert(p.curr==before);
 assert(!order_violation);assert(!invalid_not_latched);
 printf("{\"wire_bytes\":%u,\"list_count\":%u,\"order_violation_reproduced\":%d,\"invalid_error_not_latched\":%d,\"repeat_updates\":10000,\"curr_unchanged\":true}\n",(unsigned)sizeof(struct beacon_shared_ie_t),n,order_violation,invalid_not_latched);
 return 0;
}
'''

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--candidate',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 path=a.candidate/'source/wlan/ieee80211_beacon_desc.c';raw=path.read_bytes();text=raw.decode();names=['static void ieee80211_beacon_associate_ie(','static struct beacon_shared_ie_t *ieee80211_beacon_alloc_ie(','static int om_beacon_descriptor_valid(','static int om_beacon_slot_error(','static int om_beacon_allocation_ready(','int om_beacon_reserved_remove(','int om_beacon_reserved_update(']
 src=a.output/'fixture.c';src.write_text(PRE+'\n'.join(function(text,n)[2] for n in names)+TEST)
 exe=a.output/'fixture.exe';cc=ROOT/'tools/external/llvm-mingw-20260616-ucrt-x86_64/bin/i686-w64-mingw32-clang.exe'
 cmd=[str(cc),'-std=c11','-O1','-g','-Wall','-Wextra',str(src),'-o',str(exe)]
 build=subprocess.run(cmd,capture_output=True);(a.output/'compile.stderr').write_bytes(build.stderr);assert build.returncode==0,build.stderr.decode()
 run=subprocess.run([str(exe)],capture_output=True);(a.output/'run.stdout').write_bytes(run.stdout);assert run.returncode==0,run.stderr.decode()
 assert hashlib.sha256(path.read_bytes()).digest()==hashlib.sha256(raw).digest()
 facts=json.loads(run.stdout);result={'status':'PASS_ACTUAL_HELPER_PREVIOUS_COUNTEREXAMPLES_FIXED','hardware_accessed':False,'candidate_status':'SOURCE_HELPER_FIXES_PASS_FULL_VALIDATION_PENDING','source_sha256':hashlib.sha256(raw).hexdigest(),'facts':facts,
 'limits':'Exactcandidatehelpers compiled32bithost, fakeDMA identity. Previous orderfault and unlatchedinvaliderror no longer reproduce; notphysicalMuC andnotallbeaconintegration.'}
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
