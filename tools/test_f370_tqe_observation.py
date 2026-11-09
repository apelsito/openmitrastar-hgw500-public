"""Compare actual baseline/candidate AuC function in a bounded C fixture."""
import argparse,hashlib,json,subprocess
from pathlib import Path
import prepare_f370_tqe_observation as prep

def extract(text,name):
    """Retain the actual complete C function body; no third-party imports."""
    import re
    match=re.search(r'(?m)^static[^\n]*\b'+re.escape(name)+r'\(',text)
    assert match,name
    start=match.start();brace=text.index('{',match.end());depth=1;position=brace+1
    while depth:
        assert position<len(text),'unclosed function'
        if text[position]=='{':depth+=1
        elif text[position]=='}':depth-=1
        position+=1
    return text[start:position]

PRE=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <assert.h>
typedef uint32_t u32;typedef uint16_t u16;
#define __sram_text
#define __always_inline inline
#define OPENMITRASTAR_QDRV_V89_PAIR 1
#define module_param_named(...)
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define likely(x) (x)
#define unlikely(x) (x)
#define pr_info(...) ((void)0)
#define DBGPRINTF_LIMIT_E(...) ((void)0)
#define NETDEV_TX_OK 0
#define NETDEV_TX_BUSY 16
#define NET_XMIT_SUCCESS 0
#define QTN_SKB_CB_NI(s) ((s)->ni)
#define IEEE80211_NODE_IDX_VALID(v) ((v)!=0)
#define IEEE80211_NODE_IDX_UNMAP(v) (v)
#define QTN_NCIDX_MAX 128
#define QTN_SKB_ENCAP_IS_80211(s) ((s)->encap)
#define QTN_SKB_ENCAP_IS_80211_MGMT(s) ((s)->mgmt)
#define IEEE80211_NODE_QOS 1
#define TOPAZ_TQE_MUC_PORT 2
#define TOPAZ_TQE_WMAC_PORT 3
#define QTN_TID_MGMT 6
#define QTN_TID_WLAN 7
#define WME_AC_TO_TID(v) (v)
#define M_FLAG_ISSET(s,m) ((s)->flags&(m))
#define M_NO_AMSDU 1
#define M_RATE_TRAINING 2
#define TQE_MISCUSER_L2A_NO_AMSDU 4
#define TQE_MISCUSER_L2A_RATE_TRAINING 8
#define TOPAZ_HBM_BUF_EMAC_RX_POOL 0
#define TOPAZ_HBM_EMAC_TX_DONE_POOL 1
struct ieee80211_node{unsigned ni_flags;};
struct sk_buff{struct ieee80211_node *ni;unsigned dest_port,len,priority,flags;bool encap,mgmt;uint8_t *data;};
struct qdrv_vap{struct {unsigned iv_vapnode_idx;} iv;};
union topaz_tqe_cpuif_ppctl{unsigned data;};
static unsigned omqdrvtx_auc_trace,omqdrvtx_auc_submit_total,omqdrvtx_auc_busy_total;
static int raw,target,frees,releases,calls;
static bool omqdrvtx_trace_skb(struct sk_buff*s){return false;}
static u16 omqdrvtx_ethertype(struct sk_buff*s){return 0;}
static bool of_machine_is_compatible(const char*s){return target;}
static uint8_t qdrv_tx_peer_use_4addr(struct ieee80211_node*n,const uint8_t*p){return 0;}
static void ieee80211_free_node(struct ieee80211_node*n){releases++;}
static unsigned topaz_hbm_pool_available(unsigned pool){return 4;}
static void topaz_tqe_cpuif_ppctl_init(union topaz_tqe_cpuif_ppctl*c,unsigned p,uint8_t*n,unsigned a,unsigned t,unsigned u,unsigned b,unsigned d,unsigned e,unsigned m){c->data=p;}
static int tqe_tx(union topaz_tqe_cpuif_ppctl*c,struct sk_buff*s){calls++;if(raw==0)frees++;return raw;}
static void kfree_skb(struct sk_buff*s){frees++;}
'''
CASES=r'''
static void clear(void){frees=releases=calls=0;omqdrvtx_auc_raw_ok=omqdrvtx_auc_raw_other=omqdrvtx_auc_busy_free=omqdrvtx_auc_return_success=0;}
int main(void){
 unsigned cases=0,checks=0;int values[]={0,16,3};unsigned i,j,k;
 struct ieee80211_node node={1};uint8_t payload[1500]={0};struct qdrv_vap vap={{2}};
 for(i=0;i<3;i++)for(j=0;j<2;j++)for(k=0;k<2;k++){
  struct sk_buff skb={&node,1,1500,2,0,k,k,payload};int bf,br,bc,ret;
  raw=values[i];target=j;clear();ret=baseline(&vap,&skb);bf=frees;br=releases;bc=calls;
  clear();assert(candidate(&vap,&skb)==ret);checks++;
  assert(frees==bf&&releases==br&&calls==bc);checks++;
  assert(ret==0&&calls==1&&releases==1&&frees==(raw==0||raw==16));checks++;
  assert(omqdrvtx_auc_raw_ok==(j&&raw==0));checks++;
  assert(omqdrvtx_auc_raw_other==(j&&raw!=0&&raw!=16));checks++;
  assert(omqdrvtx_auc_busy_free==(j&&raw==16));checks++;
  assert(omqdrvtx_auc_return_success==j);checks++;cases++;
 }
 {unsigned counter=~0U;omqdrvtx_observe_sat(&counter);assert(counter==~0U);checks++;counter=~0U-1;omqdrvtx_observe_sat(&counter);assert(counter==~0U);checks++;omqdrvtx_observe_sat(&counter);assert(counter==~0U);checks++;}
 printf("F370_OBSERVATION_PASS cases=%u checks=%u hardware=0 same_ownership=1 same_return=1\n",cases,checks);return 0;
}
'''
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);a=parser.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    old=(prep.BASE/'qdrv/qdrv_tx.c').read_text();new=(prep.OUT/'source/qdrv/qdrv_tx.c').read_text();assert prep.strip(new)==old
    baseline=extract(old,'qdrv_tx_to_auc').replace('qdrv_tx_to_auc(','baseline(',1)
    candidate=extract(new,'qdrv_tx_to_auc').replace('qdrv_tx_to_auc(','candidate(',1)
    fixture=PRE+'\n'+prep.DECLS+'\n'+baseline+'\n'+candidate+'\n'+CASES
    src=a.output/'fixture.c';src.write_text(fixture);exe=a.output/'fixture';build=subprocess.run(['cc','-std=gnu99','-O2','-Wall','-Wno-unused-function','-o',str(exe),str(src)],capture_output=True);(a.output/'compile.stderr').write_bytes(build.stderr);assert build.returncode==0,build.stderr.decode()
    run=subprocess.run([str(exe)],capture_output=True);(a.output/'stdout').write_bytes(run.stdout);(a.output/'stderr').write_bytes(run.stderr)
    result=dict(schema='openmitrastar.f370-observation-test/v1',status='PASS' if run.returncode==0 else 'FAIL',output=run.stdout.decode().strip(),source_pins={str(p):prep.sha(p) for p in (prep.BASE/'qdrv/qdrv_tx.c',prep.OUT/'source/qdrv/qdrv_tx.c',Path(__file__),Path(prep.__file__))},fixture_sha256=prep.sha(src),actual_function_body=True,hardware_accessed=False,physical='NO_GO_PHYSICAL',limits='Injected software result/ownership fixture; no real HBM/RF/traffic or throughput proof.')
    (a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));return int(run.returncode!=0)
if __name__=='__main__':raise SystemExit(main())
