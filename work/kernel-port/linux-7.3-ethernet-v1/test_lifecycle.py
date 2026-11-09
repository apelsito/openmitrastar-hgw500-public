#!/usr/bin/env python3
"""Execute the candidate's actual open/stop/destructors against fake DMA/IRQ.
No device access. Uses Linux 7.3's exact polling macro and new evidence output.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def extract(text,name):
    match=re.search(r'static (?:inline )?[^\n]+\b'+re.escape(name)+r'\(',text)
    assert match,name
    start=match.start();brace=text.index('{',start);depth=1;pos=brace+1
    while depth:
        if text[pos]=='{':depth+=1
        elif text[pos]=='}':depth-=1
        pos+=1
    return text[start:pos]

PREAMBLE=r'''
#include <stdint.h>
#include <stdio.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
typedef uint16_t u16;
typedef uint64_t u64;
typedef uint64_t dma_addr_t;
typedef uint64_t ktime_t;
typedef unsigned long irq_hw_number_t;
#define BIT(n) (1U << (n))
#define GENMASK(h,l) ((~0U << (l)) & (~0U >> (31-(h))))
#define QTN_TOPAZ_EMAC_TX_RING_COUNT 64
#define QTN_TOPAZ_EMAC_RX_RING_COUNT 256
#define QTN_TOPAZ_EMAC_QUIESCE_US 50000
#define QTN_TOPAZ_EMAC_RX_RESTART_COOLDOWN_MS 10000
#define QTN_TOPAZ_EMAC_POLL_TRACE_FIRST 8
#define QTN_TOPAZ_EMAC_POLL_TRACE_DELAY_MS 1000
#define QTN_TOPAZ_EMAC_POLL_INTERVAL_MS 10
#define GFP_KERNEL 0
#define DMA_BIDIRECTIONAL 0
#define DMA_TO_DEVICE 1
#define DMA_FROM_DEVICE 2
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define max_t(t,a,b) ((t)(a)>(t)(b)?(t)(a):(t)(b))
#define __iomem
#define HZ 100
static unsigned assertions,cases;
#define CHECK(v) do{assertions++;if(!(v)){fprintf(stderr,"FAIL %d: %s\n",__LINE__,#v);exit(1);}}while(0)
static uint64_t now_us;
static ktime_t ktime_get(void){return now_us;}
static ktime_t ktime_add_us(ktime_t a,u64 b){return a+b;}
static int ktime_compare(ktime_t a,ktime_t b){return a>b?1:a<b?-1:0;}
#define might_sleep_if(v) ((void)(v))
static void usleep_range(unsigned long low,unsigned long high){(void)low;(void)high;now_us+=2500;}
static void cpu_relax(void){}
#define barrier() __asm__ volatile("" ::: "memory")
struct work { bool active; };
struct napi_struct { bool enabled; };
struct net_device { void *priv; char name[8]; bool carrier,queue; };
struct sk_buff { unsigned value; };
struct qtn_topaz_emac_buffer {struct sk_buff *skb;dma_addr_t dma;u32 len;};
struct qtn_topaz_emac {
 void *dev;
 struct net_device *ndev;
 unsigned char *regs;
 struct work link_work,irq_poll_work;
 struct napi_struct napi;
 bool dma_unsafe,link_polling,irq_poll_fallback,irq_requested,phy_autoneg,phy_link_valid,active_full_duplex;
 unsigned irq,active_speed,tx_lock;
 struct qtn_topaz_emac_desc *tx_descs,*rx_descs;
 dma_addr_t tx_descs_dma,rx_descs_dma,desc_alloc_dma;
 void *desc_alloc;size_t desc_alloc_size;
 struct qtn_topaz_emac_buffer tx_bufs[64],rx_bufs[256];
 unsigned tx_head,tx_tail,rx_head,irq20_count,poll_ticks,poll_trace_budget;
 unsigned long poll_last_rx_packets,poll_last_reported_packets,poll_last_progress_jiffies;
 unsigned long poll_last_trace_jiffies,poll_trace_start_jiffies,poll_last_poke_jiffies,poll_last_rx_restart_jiffies;
 unsigned poll_last_cur_rx,poll_same_cur_rx_pokes,poll_stall_pokes,poll_rx_dma_restarts;
 unsigned poll_rx_quiesce_timeouts,poll_rx_restart_throttled,poll_forced_napi;
 unsigned irq_tx_done,irq_rx_done,irq_mac,irq_rx_stopped,irq_no_rx_desc,irq_rx_missed,irq_napi_schedules;
 unsigned poll_napi_schedules,napi_polls,napi_completes,napi_budget_exhaustions,napi_rx_work;
 unsigned rx_head_dma_owned_samples,rx_head_cpu_owned_descs,rx_alloc_failures,rx_invalid_frames;
 unsigned dma_rx_stopped_samples,dma_no_rx_desc_samples,dma_rx_missed_samples;
 unsigned rx_restart_reason_stopped,rx_restart_reason_no_desc,rx_restart_reason_missed,rx_restart_reason_stagnant;
};
static u32 regs[256],seq[32];
static unsigned seq_count,seq_reads,events[2048],event_count;
static unsigned desc_writes,rx_allocs,rx_frees,tx_frees,ring_frees,irq_frees,irq_disables,napi_disables;
static int alloc_fail,request_error,hw_error;
static bool hw_busy,late_napi,safe_observed;
static unsigned long jiffies=100000;
static unsigned long msecs_to_jiffies(unsigned long x){return x/10;}
static void event(unsigned n){CHECK(event_count<2048);events[event_count++]=n;}
static void *netdev_priv(struct net_device *n){return n->priv;}
#define netdev_info(n,...) do{(void)(n);if(0)printf(__VA_ARGS__);}while(0)
#define netdev_err(n,...) do{(void)(n);if(0)printf(__VA_ARGS__);}while(0)
static u32 qtn_emac_read(struct qtn_topaz_emac *e,u32 r){CHECK(e->regs==(unsigned char*)regs);return regs[r/4];}
static void qtn_emac_write(struct qtn_topaz_emac *e,u32 r,u32 v){CHECK(e->regs==(unsigned char*)regs);regs[r/4]=v;event(100+r);}
static u32 readl(void *p){CHECK(p==(void*)((char*)regs+QTN_EMAC_DMA_STATUS_IRQ));u32 v=seq[seq_reads<seq_count?seq_reads:seq_count-1];seq_reads++;if(!(v&(QTN_EMAC_DMA_TX_STATE_MASK|QTN_EMAC_DMA_RX_STATE_MASK)))safe_observed=true;event(10);return v;}
static void qtn_desc_write(u32 *p,u32 v){CHECK(safe_observed);*p=v;desc_writes++;}
static u32 qtn_desc_read(u32 *p){return *p;}
static void qtn_desc_zero(struct qtn_topaz_emac_desc *p,unsigned n){CHECK(safe_observed);memset(p,0,n*sizeof(*p));desc_writes+=n*4;}
static void qtn_emac_select_rescue_port(struct qtn_topaz_emac *e){(void)e;}
static int qtn_emac_alloc_rx_buffer(struct qtn_topaz_emac *e,u16 i,unsigned flags){(void)flags;CHECK(safe_observed);if((int)i==alloc_fail)return -ENOMEM;e->rx_bufs[i].skb=(void*)1;e->rx_bufs[i].dma=i;e->rx_bufs[i].len=2048;rx_allocs++;return 0;}
static int qtn_emac_hw_start(struct qtn_topaz_emac *e){(void)e;event(20);if(hw_busy){safe_observed=false;seq[0]=BIT(21);seq_count=1;seq_reads=0;}return hw_error;}
static int request_irq(unsigned irq,void *handler,unsigned flags,const char *name,void *n){(void)irq;(void)handler;(void)flags;(void)name;(void)n;event(21);return request_error;}
#define qtn_emac_interrupt ((void*)1)
static void free_irq(unsigned irq,void *n){(void)irq;(void)n;irq_frees++;event(22);}
static void disable_irq(unsigned irq){(void)irq;irq_disables++;event(23);}
static void napi_enable(struct napi_struct *n){CHECK(!n->enabled);n->enabled=true;event(24);}
static void napi_disable(struct napi_struct *n){CHECK(n->enabled);n->enabled=false;napi_disables++;event(25);if(late_napi){regs[QTN_EMAC_DMA_INT_ENABLE/4]=0x111;event(26);}}
static bool cancel_delayed_work_sync(struct work *w){w->active=false;event(27);return true;}
static bool schedule_delayed_work(struct work *w,unsigned long delay){(void)delay;w->active=true;event(28);return true;}
static void netif_carrier_on(struct net_device *n){n->carrier=true;}
static void netif_carrier_off(struct net_device *n){n->carrier=false;}
static void netif_start_queue(struct net_device *n){n->queue=true;}
static void netif_stop_queue(struct net_device *n){n->queue=false;}
#define spin_lock_irqsave(l,f) do{(void)(l);(f)=0;}while(0)
#define spin_unlock_irqrestore(l,f) do{(void)(l);(void)(f);}while(0)
static void dma_unmap_single(void *dev,dma_addr_t addr,size_t len,int dir){(void)dev;(void)addr;(void)len;CHECK(safe_observed);event(30);if(dir==DMA_FROM_DEVICE)rx_frees++;else if(dir==DMA_TO_DEVICE)tx_frees++;else ring_frees++;}
static void dev_kfree_skb_any(struct sk_buff *s){CHECK(s);CHECK(safe_observed);event(31);}
static void kfree(void *p){CHECK(p);CHECK(safe_observed);event(32);}
'''

TESTS=r'''
static struct qtn_topaz_emac e;
static struct net_device n;
static struct qtn_topaz_emac_desc tx[64],rx[256];
static void setup(void){
 memset(&e,0,sizeof(e));memset(&n,0,sizeof(n));memset(regs,0,sizeof(regs));
 memset(tx,0xa5,sizeof(tx));memset(rx,0x5a,sizeof(rx));
 e.regs=(unsigned char*)regs;e.ndev=&n;n.priv=&e;e.tx_descs=tx;e.rx_descs=rx;e.irq=40;
 e.irq_poll_fallback=true;e.phy_autoneg=true;e.phy_link_valid=true;e.active_speed=1000;
 e.desc_alloc=(void*)1;e.desc_alloc_size=5120;
 regs[QTN_EMAC_DMA_CTRL/4]=3;regs[QTN_EMAC_MAC_TX_CTRL/4]=9;regs[QTN_EMAC_MAC_RX_CTRL/4]=0x4d;
 seq[0]=0;seq_count=1;seq_reads=0;now_us=0;safe_observed=false;event_count=0;
 desc_writes=rx_allocs=rx_frees=tx_frees=ring_frees=irq_frees=irq_disables=napi_disables=0;
 alloc_fail=-1;request_error=hw_error=0;hw_busy=late_napi=false;
}
static void verify_stop(unsigned variant,bool timeout){
 setup();CHECK(qtn_emac_open(&n)==0);CHECK(e.napi.enabled&&e.irq_requested&&n.queue);
 e.tx_bufs[0].skb=(void*)1;e.tx_bufs[0].len=64;e.tx_head=1;
 seq_reads=0;now_us=0;safe_observed=false;late_napi=!!(variant&1);
 seq[0]=timeout?(BIT(21)|QTN_EMAC_DMA_IRQ_RX_STOPPED):0;
 seq_count=1;event_count=0;
 CHECK(qtn_emac_stop(&n)==0);CHECK(!n.queue&&!n.carrier&&!e.napi.enabled&&!e.irq_requested);
 CHECK(!e.link_work.active&&!e.irq_poll_work.active&&!e.link_polling);
 CHECK(irq_frees==1&&irq_disables==1&&napi_disables==1);
 CHECK(regs[QTN_EMAC_DMA_INT_ENABLE/4]==0&&regs[QTN_EMAC_MAC_INT_ENABLE/4]==0);
 CHECK(!(regs[QTN_EMAC_DMA_CTRL/4]&3));CHECK(e.dma_unsafe==timeout);
 if(timeout){
  CHECK(!rx_frees&&!tx_frees);CHECK(e.rx_bufs[255].skb&&e.tx_bufs[0].skb);
  unsigned writes=desc_writes,allocs=rx_allocs,reads=seq_reads;
  CHECK(qtn_emac_open(&n)==-EIO);CHECK(desc_writes==writes&&rx_allocs==allocs&&seq_reads==reads);
 }else{CHECK(rx_frees==256&&tx_frees==1);CHECK(!e.rx_bufs[255].skb&&!e.tx_bufs[0].skb);}
 qtn_emac_free_rings(&e);CHECK(ring_frees==(timeout?0:1));CHECK(!!e.desc_alloc==timeout);
 cases++;
}
int main(void){
 for(unsigned variant=0;variant<4;variant++){verify_stop(variant,false);verify_stop(variant,true);}
 setup();seq[0]=BIT(16)|QTN_EMAC_DMA_IRQ_TX_STOPPED;
 CHECK(qtn_emac_open(&n)==-ETIMEDOUT);CHECK(e.dma_unsafe);CHECK(!desc_writes&&!rx_allocs);
 qtn_emac_free_rings(&e);CHECK(!ring_frees);cases++;
 for(int index=0;index<256;index+=51){setup();alloc_fail=index;
  CHECK(qtn_emac_open(&n)==-ENOMEM);CHECK(!e.dma_unsafe);CHECK(rx_allocs==(unsigned)index&&rx_frees==(unsigned)index);
  CHECK(!n.queue&&!e.napi.enabled&&!e.irq_requested);cases++;}
 setup();request_error=-EBUSY;late_napi=true;
 CHECK(qtn_emac_open(&n)==-EBUSY);CHECK(rx_frees==256&&!e.dma_unsafe&&napi_disables==1);
 CHECK(regs[QTN_EMAC_DMA_INT_ENABLE/4]==0);cases++;
 setup();hw_error=-EIO;late_napi=true;
 CHECK(qtn_emac_open(&n)==-EIO);CHECK(rx_frees==256&&irq_frees==1&&!e.dma_unsafe);cases++;
 setup();hw_error=-ETIMEDOUT;hw_busy=true;late_napi=true;
 CHECK(qtn_emac_open(&n)==-ETIMEDOUT);CHECK(e.dma_unsafe&&!rx_frees&&irq_frees==1);
 CHECK(regs[QTN_EMAC_DMA_INT_ENABLE/4]==0);qtn_emac_free_rings(&e);CHECK(!ring_frees);cases++;
 printf("ETH73_LIFECYCLE_PASS cases=%u assertions=%u hardware_accessed=0\n",cases,assertions);
 return 0;
}
'''

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--kernel-source',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    source=a.candidate/'driver/qtn-topaz-emac-eth73.c'
    header=a.candidate/'driver/topaz-ethernet.h'
    polling=a.kernel_source/'include/linux/iopoll.h'
    fixture_tool=ROOT/'tools/test_f374_ethernet_rx_quiesce.py'
    if not fixture_tool.exists():
        fixture_tool=HERE/'fixtures/test_f374_ethernet_rx_quiesce.py'
    spec=importlib.util.spec_from_file_location('f374_fixture',fixture_tool);old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    pins={str(f):sha(f) for f in [source,header,polling,fixture_tool,Path(__file__)]}
    text=source.read_text()
    macros=''.join(old.extract_macro(polling.read_text(),n) for n in ['poll_timeout_us','read_poll_timeout','readx_poll_timeout','readl_poll_timeout'])
    defs=header.read_text().replace('#include <linux/bits.h>','').replace('#include <linux/types.h>','')
    names=['qtn_emac_disable_irqs','qtn_emac_quiesce','qtn_emac_free_rx_buffers','qtn_emac_free_tx_buffers','qtn_emac_free_rings','qtn_emac_open','qtn_emac_stop']
    fixture=PREAMBLE.replace('struct qtn_topaz_emac {',defs+'\nstruct qtn_topaz_emac {')+macros+'\n'+'\n'.join(extract(text,n) for n in names)+TESTS
    (a.output/'fixture.c').write_text(fixture)
    cmd=['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-format','-fsanitize=undefined',str(a.output/'fixture.c'),'-o',str(a.output/'fixture')]
    proc=subprocess.run(cmd,capture_output=True)
    (a.output/'compile.stderr').write_bytes(proc.stderr)
    assert proc.returncode==0,proc.stderr.decode()
    result=subprocess.run([str(a.output/'fixture')],capture_output=True)
    (a.output/'test.stdout').write_bytes(result.stdout);(a.output/'test.stderr').write_bytes(result.stderr)
    report={'schema':'openmitrastar.eth73-lifecycle-fixture/v1','status':'PASS_EXTRACTED_LIFECYCLE' if result.returncode==0 else 'FAIL',
            'hardware_accessed':False,'pins':pins,'functions':names,'output':result.stdout.decode(),
            'limits':['Fake MMIO, IRQ, NAPI and work cancellation; no real DMA traffic or CPU execution.',
                      'Actual open/stop/free functions executed; driver probe/remove and full worker are not executed here.']}
    for f,digest in pins.items():assert sha(Path(f))==digest
    (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2));assert result.returncode==0,result.stderr.decode()

if __name__=='__main__':main()
