"""Actual AES-CCMP key controller and exact string adapter host fixtures."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--overlay',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);cc=a.overlay/'source/wlan/ieee80211_crypto_ccmp.c';comp=a.overlay/'source/qdrv/compat/include/openmitrastar_qdrv_compat.h';controller=function(cc.read_text(),'static int\nccmp_setkey(');s=function(comp.read_text(),'static inline size_t om_linux73_strlcpy(')
 pre=r'''#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <assert.h>
typedef uint8_t u8;typedef uint16_t u16;
#define NBBY 8
#define IEEE80211_KEY_SWCRYPT 1
#define IEEE80211_MSG_CRYPTO 1
#define IEEE80211_DPRINTF(...) ((void)0)
#define GFP_ATOMIC 0
struct aes_enckey{unsigned char keys[256];};struct ccmp_ctx{struct aes_enckey*cc_tfm;void*cc_vap;};struct ieee80211_key{void*wk_private;unsigned wk_keylen,wk_flags;unsigned char wk_key[32];};
static int failalloc,failprepare,allocs,frees,prepares;
static void*kzalloc(size_t n,int ignored){(void)ignored;allocs++;return failalloc?NULL:calloc(1,n);}
static void kfree_sensitive(void*p){if(p){memset(p,0,sizeof(struct aes_enckey));free(p);frees++;}}
static int aes_prepareenckey(struct aes_enckey*k,const unsigned char*key,size_t len){prepares++;assert(len==16&&k&&key);memcpy(k->keys,key,len);return failprepare?-22:0;}
'''
 test=r'''int main(void){unsigned cases=0;struct ccmp_ctx ctx={0};struct ieee80211_key key={&ctx,16,1,{0}};for(unsigned len=0;len<=32;len++)for(unsigned sw=0;sw<2;sw++)for(unsigned allocfail=0;allocfail<2;allocfail++)for(unsigned preparefail=0;preparefail<2;preparefail++){ctx.cc_tfm=NULL;key.wk_keylen=len;key.wk_flags=sw;failalloc=allocfail;failprepare=preparefail;allocs=frees=prepares=0;int rc=ccmp_setkey(&key);if(len!=16){assert(!rc&&!allocs&&!prepares&&!ctx.cc_tfm);}else if(!sw){assert(rc&&!allocs&&!prepares);}else if(allocfail){assert(!rc&&allocs==1&&!prepares&&!ctx.cc_tfm);}else if(preparefail){assert(!rc&&allocs==1&&prepares==1&&frees==1&&!ctx.cc_tfm);}else{assert(rc&&allocs==1&&prepares==1&&ctx.cc_tfm);kfree_sensitive(ctx.cc_tfm);}cases++;}
for(unsigned len=0;len<1024;len++)for(unsigned size=0;size<65;size++){char src[1025],dst[66],exp[66];memset(src,'a',len);src[len]=0;memset(dst,0xa5,sizeof(dst));memset(exp,0xa5,sizeof(exp));if(size){unsigned n=len<size-1?len:size-1;memcpy(exp,src,n);exp[n]=0;}assert(om_linux73_strlcpy(dst,src,size)==len&&!memcmp(dst,exp,sizeof(dst)));cases++;}printf("{\"actual_controller_and_string_cases\":%u}\n",cases);return 0;}
''';f=a.output/'actual-controllers.c';f.write_text(pre+controller+s+test);compiler=ROOT/'tools/external/llvm-mingw-20260616-ucrt-x86_64/bin/clang.exe';r=subprocess.run([str(compiler),'-O1','-std=c11',str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert not r.returncode,r.stderr.decode();proof=json.loads(r.stdout);pins={str(x):sha(x)for x in[Path(__file__),cc,comp,compiler,f,a.output/'fixture.exe']};r={'status':'PASS_ACTUAL_LINUX73_CCMP_KEY_CONTROLLER_AND_STRLCPY_LENGTH_FIXTURE','hardware_accessed':False,'firmware_eligible':False,**proof,'pins':pins,'limits':'Actualkeycontrol/strlcpy; AES primitive/allocationfakes. NoAEScipherbyteproof orARC/radio execution.'};(a.output/'result.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r,indent=2))
if __name__=='__main__':main()
