"""Actual APP helpers, bounded-frame and BH exclusion source fixture, offline.

Pointer/length/helpers execute host C with fake lock/allocation/validator. This
does not validate all IE encoders, hardIRQ callers or actual scheduler behavior.
"""
import argparse,hashlib,json,subprocess
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function

PRE=r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <errno.h>
#define IEEE80211_APPIE_MAX 1024
#define M_DEVBUF 1
#define M_WAITOK 1
struct ieee80211_ie{uint8_t v;};struct ieee80211com{int x;};struct ieee80211_app_ie_t{struct ieee80211_ie*ie;unsigned length;};struct ieee80211vap{struct ieee80211com*iv_ic;struct ieee80211_app_ie_t app_ie[6];};struct ieee80211req_getset_appiebuf{unsigned app_buflen;uint8_t app_buf[1024];};
static unsigned locked,bh,allocs,frees,copies,pending,softirq_runs,reentries;
static int fail_alloc;static unsigned injected,inject_phase;
static void try_softirq(unsigned at){if(inject_phase==at&&!injected){injected=1;if(bh)pending=1;else{softirq_runs++;if(locked)reentries++;}}}
static void lock_bh(void){try_softirq(1);bh++;try_softirq(2);assert(!locked);locked=1;try_softirq(3);}
static void unlock_bh(void){try_softirq(4);assert(locked);locked=0;try_softirq(5);assert(bh);bh--;try_softirq(6);if(!bh&&pending){assert(!locked);pending=0;softirq_runs++;}}
#define IEEE80211_LOCK_BH(ic) do{(void)(ic);lock_bh();}while(0)
#define IEEE80211_UNLOCK_BH(ic) do{(void)(ic);unlock_bh();}while(0)
static int is_valid_ie_list(unsigned n,void*p,int x){(void)p;(void)x;return n<=1024;}
static void*allocation(unsigned n){assert(!locked);allocs++;return fail_alloc?NULL:malloc(n?n:1);}
static void release(void*p){assert(!locked);frees++;free(p);}
#define MALLOC(p,type,n,t,f) ((p)=(type)allocation(n))
#define FREE(p,t) release(p)
static void*checked_copy(void*d,const void*s,size_t n){if(locked)assert(bh);copies++;return memcpy(d,s,n);}
#define memcpy(d,s,n) checked_copy(d,s,n)
'''
TEST=r'''
int main(void){struct ieee80211com ic;struct ieee80211vap v={.iv_ic=&ic};struct ieee80211req_getset_appiebuf request={0},answer={0};unsigned char frame[1056];unsigned cases=0;
for(unsigned n=0;n<=1024;n++){
 request.app_buflen=n;memset(request.app_buf,(unsigned char)n,n);assert(add_app_ie(0,&v,&request)==0);
 answer.app_buflen=1024;assert(get_app_ie(0,&v,&answer)==0&&answer.app_buflen==n&&!memcmp(answer.app_buf,request.app_buf,n));
 memset(frame,0x5c,sizeof(frame));assert(om_app_ie_copy(&v,0,frame+16)==n);assert(!memcmp(frame+16,request.app_buf,n));
 for(unsigned i=0;i<16;i++)assert(frame[i]==0x5c&&frame[1040+i]==0x5c);
 if(n){unsigned before=copies;answer.app_buflen=n-1;assert(get_app_ie(0,&v,&answer)==-EINVAL&&answer.app_buflen==n-1&&copies==before);}
 assert(!locked&&!bh);cases++;
}
fail_alloc=1;request.app_buflen=4;unsigned oldlen=v.app_ie[0].length;struct ieee80211_ie*old=v.app_ie[0].ie;assert(add_app_ie(0,&v,&request)==-ENOMEM&&v.app_ie[0].ie==old&&v.app_ie[0].length==oldlen);fail_alloc=0;cases++;
request.app_buflen=1025;unsigned before=allocs;assert(add_app_ie(0,&v,&request)==-EINVAL&&allocs==before&&v.app_ie[0].ie==old);cases++;
for(unsigned phase=1;phase<=6;phase++){inject_phase=phase;injected=pending=softirq_runs=0;assert(om_app_ie_copy(&v,0,frame+16)==1024);assert(injected&&softirq_runs==1&&!pending&&!locked&&!bh&&!reentries);cases++;}
inject_phase=0;assert(remove_app_ie(0,&v)==0&&!v.app_ie[0].ie&&!v.app_ie[0].length);assert(om_app_ie_copy(&v,0,frame+16)==0);cases++;
printf("{\"cases\":%u,\"lengths\":1025,\"BH_injection_phases\":6,\"reentrant_lock_windows\":%u}\n",cases,reentries);return 0;}
'''
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True)
 wireless=a.source/'source/wlan/ieee80211_wireless.c';output=a.source/'source/wlan/ieee80211_output.c';body='\n'.join('static int '+function(wireless.read_text(),n+'(')for n in['add_app_ie','remove_app_ie','get_app_ie'])+'\nstatic unsigned int '+function(output.read_text(),'om_app_ie_copy(')
 fixture=a.output/'actual-app-transaction.c';fixture.write_text(PRE+body+TEST)
 r=subprocess.run([str(a.compiler),'-O1','-std=c11',str(fixture),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode()
 r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert not r.returncode,r.stderr.decode();v=json.loads(r.stdout);assert v['cases']==1034 and not v['reentrant_lock_windows']
 result={'status':'PASS_ACTUAL_APP_HELPER_LENGTH_ALLOCATION_BH_TRANSACTION_FIXTURE','hardware_accessed':False,'firmware_eligible':False,**v,'source_pins':{str(p):sha(p)for p in[wireless,output]},'fixture_sha256':sha(fixture),'executable_sha256':sha(a.output/'fixture.exe'),'compiler_sha256':sha(a.compiler),'limits':['Validator/allocation/lock/copy operate as host fakes. IE syntax validator not included.','APP helpers and1024byteownedframecopy tested; otherfullframeIEencodersnotexecuted.','BH exclusion modeledin6phases; noactualkernelSMP/hardIRQ/reentrancyorVAPobjectlifetimeacceptance.']}
 (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
