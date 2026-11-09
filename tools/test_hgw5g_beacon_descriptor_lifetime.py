"""Exercise real 32-bit descriptor helpers and extracted dynamic update paths.

Fake skb/DMA/IE writers only. This proves source ownership/budget cases, not an
ARC build, every IE encoder, MuC timing or physical beacon delivery.
"""
import argparse, hashlib, json, subprocess
from pathlib import Path
from prepare_hgw5g_beacon_descriptor_lifetime import ROOT, function

PRE = r'''
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#include <assert.h>
#include <errno.h>
typedef uint32_t u32;typedef uint8_t u8;typedef uint32_t dma_addr_t;
#define EXPORT_SYMBOL(x)
#define BEACON_PARAM_SIZE 1000
#define IEEE80211_F_CCA 1U
#define IEEE80211_ELEMID_MEASREQ 38
#define IEEE80211_ELEMID_VENDOR_APP 0xff09
#define IEEE80211_APPIE_FRAME_BEACON 0
#define IEEE80211_FEXT_APPIE_UPDATE 1U
struct beacon_shared_ie_t {dma_addr_t buf;uint8_t*lhost_buf;uint32_t size;uint32_t next_muc_addr;struct beacon_shared_ie_t*next;};
struct ieee80211_beacon_param_t {struct beacon_shared_ie_t*head,*tail;uint8_t buf[1000];uint32_t curr;uint16_t size;struct beacon_shared_ie_t*om_cca_ie,*om_app_ie;int om_build_error;};
struct ieee80211_ie_measreq {u8 data[18];};
struct ieee80211_ie_measure_comm {u8 data[5];};
struct sk_buff {u8 *data;unsigned len,capacity;};
struct app_ie {u8*ie;unsigned length;};
struct ieee80211vap {struct ieee80211_beacon_param_t*param;struct app_ie app_ie[1];u32 iv_flags_ext;};
struct ieee80211com {u32 ic_flags;};
struct ieee80211_node {struct ieee80211vap*ni_vap;};
struct ieee80211_beacon_offsets {u8 *bo_cca,*bo_appie_buf,*bo_xr;unsigned bo_appie_buf_len,bo_tim_trailerlen;};
static unsigned checks,cases;
#define CHECK(x) do{checks++;assert(x);}while(0)
static uint32_t plat_kernel_addr_to_dma(void*x,void*y){(void)x;return(uint32_t)(uintptr_t)y;}
static int skb_tailroom(struct sk_buff*s){CHECK(s->len<=s->capacity);return s->capacity-s->len;}
static u8*skb_put(struct sk_buff*s,unsigned n){CHECK(n<=s->capacity-s->len);u8*p=s->data+s->len;s->len+=n;return p;}
static void skb_trim(struct sk_buff*s,unsigned n){CHECK(n<=s->len);s->len=n;}
'''

WRITER = r'''
static u8*ieee80211_add_beacon_desc_ie(struct ieee80211_node*ni,unsigned id,u8*frm){
 struct ieee80211_beacon_param_t*p=ni->ni_vap->param;unsigned n;
 if(id==IEEE80211_ELEMID_MEASREQ){
#ifdef CONFIG_QTN_80211K_SUPPORT
 n=sizeof(struct ieee80211_ie_measreq)+sizeof(struct ieee80211_ie_measure_comm);
#else
 n=sizeof(struct ieee80211_ie_measreq);
#endif
 memset(frm,0x38,n);CHECK(om_beacon_reserved_update(p,p->om_cca_ie,frm,n)==0);
 }else{n=ni->ni_vap->app_ie[0].length;CHECK(ni->ni_vap->app_ie[0].ie!=NULL);memcpy(frm,ni->ni_vap->app_ie[0].ie,n);CHECK(om_beacon_reserved_update(p,p->om_app_ie,frm,n)==0);}
 return frm+n;
}
'''

TEST = r'''
static unsigned list_count(struct ieee80211_beacon_param_t*p,struct sk_buff*s){
 unsigned n=0;u8*position=s->data;struct beacon_shared_ie_t*last=NULL;
 for(struct beacon_shared_ie_t*i=p->head;i;i=i->next){CHECK(++n<=50);CHECK(om_beacon_descriptor_valid(p,i));CHECK(i->lhost_buf==position);CHECK(i->buf==(u32)(uintptr_t)i->lhost_buf);CHECK(i->next_muc_addr==(u32)(uintptr_t)i->next);position+=i->size;last=i;}
 CHECK(last==p->tail);CHECK(position==s->data+s->len);return n;
}
static void init(struct ieee80211_beacon_param_t*p,u8*bytes,unsigned base){
 memset(p,0,sizeof(*p));p->size=1000;p->curr=(u32)(uintptr_t)p->buf;
 p->om_cca_ie=ieee80211_beacon_alloc_ie(p);p->om_app_ie=ieee80211_beacon_alloc_ie(p);
 struct beacon_shared_ie_t*i=ieee80211_beacon_alloc_ie(p);ieee80211_beacon_associate_ie(i,bytes,base);p->head=p->tail=i;
 CHECK(om_ieee80211_beacon_build_status(p)==0);
}
int main(void){
 _Static_assert(sizeof(void*)==4,"32bit host required");_Static_assert(sizeof(struct beacon_shared_ie_t)==20,"wire descriptor");
 struct ieee80211_beacon_param_t p;u8 buffer[512]={0},app[280];memset(app,0x65,sizeof(app));
 struct sk_buff s={buffer,20,sizeof(buffer)};struct ieee80211vap v={0};struct ieee80211com ic={0};struct ieee80211_node ni={&v};struct ieee80211_beacon_offsets bo={buffer+20,buffer+20,buffer+20,0,20};v.param=&p;
 init(&p,buffer,20);unsigned curr=p.curr;
 /* APP is attached first. Every CCA toggle must preserve serialized frame order. */
 v.app_ie[0].ie=app;v.app_ie[0].length=17;actual_dynamic(&ni,&v,&ic,&bo,&s);CHECK(list_count(&p,&s)==2);cases++;
 for(unsigned n=0;n<10000;n++){ic.ic_flags=n&1;v.app_ie[0].length=(n%3)?17:270;v.app_ie[0].ie=(n%5)?app:NULL;actual_dynamic(&ni,&v,&ic,&bo,&s);CHECK(!p.om_build_error);CHECK(p.curr==curr);list_count(&p,&s);if(v.app_ie[0].ie)CHECK(memcmp(bo.bo_appie_buf,app,bo.bo_appie_buf_len)==0);cases++;}
 ic.ic_flags=0;v.app_ie[0].ie=NULL;actual_dynamic(&ni,&v,&ic,&bo,&s);CHECK(list_count(&p,&s)==1);CHECK(s.len==20);cases++;
 /* Once reserved, dynamic updates never consume the remaining 47 static slots. */
 while(om_beacon_allocation_ready(&p)){CHECK(ieee80211_beacon_alloc_ie(&p)!=NULL);}CHECK(p.curr==(u32)(uintptr_t)p.buf+1000);CHECK(p.om_build_error==-ENOSPC);unsigned before=p.curr;CHECK(ieee80211_beacon_alloc_ie(&p)==NULL);CHECK(p.curr==before);cases++;
 /* Invalid, misaligned, foreign, one-past and corrupt chain pointers are refused. */
 for(unsigned k=0;k<6;k++){init(&p,buffer,20);struct beacon_shared_ie_t*bad=k==0?NULL:k==1?(void*)(p.buf+1):k==2?(void*)(p.buf+1000):k==3?(void*)buffer:k==4?(void*)(p.buf-20):(void*)(p.buf+60);CHECK(om_beacon_reserved_update(&p,bad,buffer+20,8)==-EINVAL);CHECK(p.om_build_error==-EINVAL);cases++;}
 init(&p,buffer,20);p.head->next=(void*)(p.buf+1000);CHECK(om_beacon_reserved_update(&p,p.om_app_ie,buffer+20,4)==-EINVAL);CHECK(p.om_build_error==-EINVAL);cases++;
 init(&p,buffer,20);p.head->next=p.head;CHECK(om_beacon_reserved_update(&p,p.om_app_ie,buffer+20,4)==-EINVAL);CHECK(p.om_build_error==-EINVAL);cases++;
 init(&p,buffer,20);p.om_cca_ie=(void*)(p.buf+1);CHECK(om_ieee80211_beacon_build_status(&p)==-EINVAL);CHECK(p.om_build_error==-EINVAL);cases++;
 /* Validate every suffix and tail before reaching any insertion point. */
 init(&p,buffer,20);p.tail=(void*)(p.buf+1000);CHECK(om_ieee80211_beacon_build_status(&p)==-EINVAL);CHECK(p.om_build_error==-EINVAL);cases++;
 init(&p,buffer,20);p.head->lhost_buf=buffer+40;p.head->buf=(u32)(uintptr_t)(buffer+40);p.head->next=(void*)(p.buf+1000);p.head->next_muc_addr=(u32)(uintptr_t)p.head->next;CHECK(om_beacon_reserved_update(&p,p.om_cca_ie,buffer+20,8)==-EINVAL);CHECK(p.om_cca_ie->size==0);CHECK(p.head->lhost_buf==buffer+40);cases++;
 init(&p,buffer,20);p.head->buf^=1;CHECK(om_ieee80211_beacon_build_status(&p)==-EINVAL);cases++;
 init(&p,buffer,20);p.head->next_muc_addr=1;CHECK(om_ieee80211_beacon_build_status(&p)==-EINVAL);cases++;
 init(&p,buffer,20);p.om_app_ie->size=8;CHECK(om_ieee80211_beacon_build_status(&p)==-EINVAL);cases++;
 init(&p,buffer,20);p.head->size=19;s.len=20;s.capacity=512;CHECK(om_ieee80211_beacon_frame_status(&p,&s)==-EINVAL);cases++;
 init(&p,buffer,20);s.len=20;s.capacity=512;bo=(struct ieee80211_beacon_offsets){buffer+20,buffer+20,buffer+20,0,20};p.tail=(void*)(p.buf+1000);u8 bad_snapshot[512];memcpy(bad_snapshot,buffer,512);actual_dynamic(&ni,&v,&ic,&bo,&s);CHECK(p.om_build_error==-EINVAL);CHECK(memcmp(bad_snapshot,buffer,512)==0);CHECK(s.len==20);cases++;
 init(&p,buffer,20);s.len=20;s.capacity=512;bo=(struct ieee80211_beacon_offsets){buffer+20,buffer+19,buffer+20,0,20};actual_dynamic(&ni,&v,&ic,&bo,&s);CHECK(p.om_build_error==-EINVAL);CHECK(s.len==20);cases++;
 /* Tailroom refusal occurs before changing payload, offsets or descriptor links. */
 init(&p,buffer,20);s.len=20;s.capacity=20;bo=(struct ieee80211_beacon_offsets){buffer+20,buffer+20,buffer+20,0,20};ic.ic_flags=1;u8 snapshot[512];memcpy(snapshot,buffer,512);actual_dynamic(&ni,&v,&ic,&bo,&s);CHECK(p.om_build_error==-ENOSPC);CHECK(memcmp(snapshot,buffer,512)==0);CHECK(s.len==20);CHECK(bo.bo_appie_buf==buffer+20);cases++;
 printf("{\"cases\":%u,\"checks\":%u,\"wire_bytes\":20,\"dynamic_updates\":10000}\n",cases,checks);return 0;
}
'''

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--candidate',required=True,type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
 assert not a.output.exists();a.output.mkdir(parents=True)
 desc_path=a.candidate/'source/wlan/ieee80211_beacon_desc.c';beacon_path=a.candidate/'source/wlan/ieee80211_beacon.c';desc=desc_path.read_text();beacon=beacon_path.read_text()
 names=['static void ieee80211_beacon_associate_ie(','static struct beacon_shared_ie_t *ieee80211_beacon_alloc_ie(',
        'static int om_beacon_descriptor_valid(','static int om_beacon_slot_error(', 'static int om_beacon_chain_valid(', 'static int om_beacon_allocation_ready(',
        'int om_beacon_reserved_remove(','int om_beacon_reserved_update(','int om_ieee80211_beacon_build_status(',
        'int om_ieee80211_beacon_frame_status(']
 bodies=[]
 for name in names:
  # Skip a forward declaration: implementations all have a brace before ';'.
  start=desc.index(name)
  while desc.find(';',start)<desc.find('{',start):start=desc.index(name,start+1)
  bodies.append(function(desc[start:],name)[2])
 cca=beacon[beacon.index('        /* Change the CCA payload'):beacon.index('\n#if 0 /* Preserve original repeated-allocation algorithm.')]
 app=beacon[beacon.index('    /* APP payload replacement'):beacon.index('\n#if 0 /* Preserve original APP allocation algorithm.')]
 validation_start=beacon.index('\tIEEE80211_LOCK(ic);',beacon.index('void\nieee80211_beacon_update('))
 validation_end=beacon.index('\n\t/* XXX faster',validation_start)
 validation=beacon[validation_start:validation_end]
 dynamic='static void actual_dynamic(struct ieee80211_node*ni,struct ieee80211vap*vap,struct ieee80211com*ic,struct ieee80211_beacon_offsets*bo,struct sk_buff*skb){\n'+validation+cca+app+'\nom_beacon_update_end:IEEE80211_UNLOCK(ic);return;\n}\n'
 fixture_locks='\n#define IEEE80211_LOCK(ic) ((void)(ic))\n#define IEEE80211_UNLOCK(ic) ((void)(ic))\n'
 fixture=PRE+fixture_locks+'\n'.join(bodies)+WRITER+dynamic+TEST
 f=a.output/'actual-descriptors.c';f.write_text(fixture,encoding='utf-8')
 compiler=ROOT/'tools/external/llvm-mingw-20260616-ucrt-x86_64/bin/i686-w64-mingw32-clang.exe';results={}
 for lane in ('plain','80211k'):
  exe=a.output/(lane+'.exe');cmd=[str(compiler),'-std=c11','-O1','-g','-Wall','-Wextra','-Wno-unused-function',str(f),'-o',str(exe)]
  if lane=='80211k':cmd.insert(1,'-DCONFIG_QTN_80211K_SUPPORT=1')
  b=subprocess.run(cmd,capture_output=True);(a.output/(lane+'.compile.stderr')).write_bytes(b.stderr);assert b.returncode==0,b.stderr.decode()
  r=subprocess.run([str(exe)],capture_output=True);(a.output/(lane+'.stdout')).write_bytes(r.stdout);(a.output/(lane+'.stderr')).write_bytes(r.stderr);assert r.returncode==0,r.stderr.decode()
  results[lane]=json.loads(r.stdout)
 result={'status':'PASS_ACTUAL_32BIT_DESCRIPTOR_AND_DYNAMIC_PATH_FIXTURE','hardware_accessed':False,'firmware_eligible':False,
         'lanes':results,'descriptor_source_sha256':hashlib.sha256(desc_path.read_bytes()).hexdigest(),'beacon_source_sha256':hashlib.sha256(beacon_path.read_bytes()).hexdigest(),
         'fixture_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'limits':['Fake skb/DMA and IE encoders; real descriptor/list/dynamic update C blocks.',
         'No ARC/module/full IE encoder or physical MuC proof. Full header dependency rebuild remains required.']}
 result['actual_update_validation_prefix_included']=True
 result['complete_chain_negative_cases_included']=True
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
