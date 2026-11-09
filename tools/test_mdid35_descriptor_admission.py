"""Actual IE54 admission/case/link path, real descriptor C helpers on 32-bit host."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);src=a.candidate/'source/wlan';dp=src/'ieee80211_beacon_desc.c';text=dp.read_text();bodies=[]
 names=['static void ieee80211_beacon_associate_ie(','static struct beacon_shared_ie_t *ieee80211_beacon_alloc_ie(','static int om_beacon_descriptor_valid(','static int om_beacon_slot_error(','static int om_beacon_chain_valid(','static int om_beacon_allocation_ready(','static void ieee80211_add_beacon_ie_desc(','int om_ieee80211_beacon_build_status(']
 for sig in names:
  start=text.index(sig)
  while text.find(';',start)<text.find('{',start):start=text.index(sig,start+1)
  bodies.append(function(text[start:],sig))
 h=(src/'openmitrastar_mdie.h').read_text();md=h[h.index('static inline'):h.rindex('#endif')];whole=function(text,'uint8_t *ieee80211_add_beacon_desc_ie(');s=whole.index('\tif (param == NULL)');e=whole.index('\tswitch (ext_ie_id)',s);admit=whole[s:e];s=whole.index('\tcase 54:');e=whole.index('\tcase 70:',s);case=whole[s:e];s=whole.index('\tpost_frm = frm;',e);tail=whole[s:whole.rindex('}')]
 pre=r'''#include <stdint.h>
#include <stddef.h>
#include <assert.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;
#define EXPORT_SYMBOL(x)
#define READ_ONCE(x) (x)
#define BEACON_PARAM_SIZE 1000
#define IEEE80211_ELEMID_MEASREQ 38
#define IEEE80211_ELEMID_VENDOR_APP 0xff09
struct beacon_shared_ie_t{u32 buf;u8*lhost_buf;u32 size,next_muc_addr;struct beacon_shared_ie_t*next;};
struct ieee80211_beacon_param_t{struct beacon_shared_ie_t*head,*tail;u8 buf[1000];u32 curr;u16 size;struct beacon_shared_ie_t*om_cca_ie,*om_app_ie;int om_build_error;};
struct ieee80211vap{struct ieee80211_beacon_param_t*param;u16 om_mdid;u8 om_ft_over_ds;};struct ieee80211_node{struct ieee80211vap*ni_vap;};
static u32 plat_kernel_addr_to_dma(void*a,void*b){(void)a;return(u32)(uintptr_t)b;}
static int om_beacon_chain_valid(struct ieee80211_beacon_param_t*);
static int om_beacon_reserved_update(struct ieee80211_beacon_param_t*p,struct beacon_shared_ie_t*i,u8*f,u16 n){(void)p;(void)i;(void)f;(void)n;assert(0);return-22;}
'''
 actual='\n'.join(bodies)+md+'\nstatic u8*descriptor(struct ieee80211_node*ni,u16 ext_ie_id,u8*frm){u8*pre_frm=frm,*post_frm=frm;struct ieee80211vap*vap=ni->ni_vap;struct ieee80211_beacon_param_t*param=vap->param;'+admit+'switch(ext_ie_id){'+case+'default:assert(0);}'+tail+'}\n'
 test=r'''static void init(struct ieee80211_beacon_param_t*p,u8*bytes,unsigned slots){memset(p,0,sizeof(*p));p->size=1000;p->curr=(u32)(uintptr_t)p->buf;p->om_cca_ie=ieee80211_beacon_alloc_ie(p);p->om_app_ie=ieee80211_beacon_alloc_ie(p);for(unsigned k=2;k<slots;k++)ieee80211_add_beacon_ie_desc(p,bytes+(k-2),1);assert(!p->om_build_error);}
int main(void){_Static_assert(sizeof(void*)==4&&sizeof(struct beacon_shared_ie_t)==20,"wire");struct ieee80211_beacon_param_t p;struct ieee80211vap vap={&p,0,0};struct ieee80211_node ni={&vap};u8 bytes[128],expected[128];unsigned cases=0;
for(unsigned md=0;md<65536;md++){init(&p,bytes,2);vap.om_mdid=md;vap.om_ft_over_ds=md&255;memset(bytes,0xa5,sizeof(bytes));memset(expected,0xa5,sizeof(expected));expected[1]=54;expected[2]=3;expected[3]=(u8)md;expected[4]=(u8)(md>>8);expected[5]=(md&255)?1:0;assert(descriptor(&ni,54,bytes+1)==bytes+6&&!memcmp(bytes,expected,sizeof(bytes)));assert(p.curr==(u32)(uintptr_t)p.buf+60&&p.head==p.tail&&p.head->size==5&&p.head->lhost_buf==bytes+1);assert(!om_ieee80211_beacon_build_status(&p));cases++;}
for(unsigned slots=2;slots<=50;slots++){init(&p,bytes,slots);vap.om_mdid=0x1234;memset(bytes,0xa5,sizeof(bytes));memcpy(expected,bytes,sizeof(bytes));u32 before=p.curr;u8*frm=bytes+(slots-2);u8*end=descriptor(&ni,54,frm);if(slots==50){assert(end==frm&&p.curr==before&&p.om_build_error==-ENOSPC&&!memcmp(bytes,expected,sizeof(bytes)));}else{assert(end==frm+5&&p.curr==before+20&&!p.om_build_error&&p.tail->size==5);}cases++;}
for(unsigned bad=0;bad<7;bad++){init(&p,bytes,3);if(bad==0)p.curr=(u32)(uintptr_t)p.buf+1;if(bad==1)p.size=999;if(bad==2)p.head->next=p.head;if(bad==3)p.tail=(void*)(p.buf+1000);if(bad==4)p.om_build_error=-EINVAL;if(bad==5)p.head->buf^=1;if(bad==6)p.curr=(u32)(uintptr_t)p.buf+1020;memset(bytes,0xa5,sizeof(bytes));memcpy(expected,bytes,sizeof(bytes));assert(descriptor(&ni,54,bytes+1)==bytes+1&&!memcmp(bytes,expected,sizeof(bytes)));cases++;}
vap.param=NULL;assert(descriptor(&ni,54,bytes+1)==NULL);cases++;printf("{\"actual_IE54_admission_cases\":%u}\n",cases);return 0;}
'''
 f=a.output/'actual-ie54-admission.c';f.write_text(pre+actual+test);compiler=ROOT/'tools/external/llvm-mingw-20260616-ucrt-x86_64/bin/i686-w64-mingw32-clang.exe';r=subprocess.run([str(compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert not r.returncode,r.stderr.decode();proof=json.loads(r.stdout);pins={str(x):sha(x)for x in[Path(__file__),dp,src/'openmitrastar_mdie.h',compiler,f,a.output/'fixture.exe']};r={'status':'PASS_ACTUAL_MDIE54_FULL_ADMISSION_PAYLOAD_AND_DESCRIPTOR_LINK_PATH','hardware_accessed':False,'firmware_eligible':False,**proof,'pins':pins,'limits':'Realadmission/allocator/chain/descriptorlink/IE54; fakeDMAconversiononly, reservedupdatesunreachable. NophysicalMuCTx/RFexecution.'};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
