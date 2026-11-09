"""Execute real candidate quiesce/open/stop/destructors with fake reset erratum.
Two independent EMAC banks, read-during-reset trap, timeout and lifecycle cases.
"""
from pathlib import Path
import argparse,hashlib,importlib.util,json,subprocess
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--kernel-source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
 spec=importlib.util.spec_from_file_location('base_test',ROOT/'work/kernel-port/linux-7.3-ethernet-v1/test_lifecycle.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
 pollspec=importlib.util.spec_from_file_location('poll_base',ROOT/'tools/test_f374_ethernet_rx_quiesce.py');poll=importlib.util.module_from_spec(pollspec);pollspec.loader.exec_module(poll)
 driver=a.candidate/'driver/qtn-topaz-emac-eth73.c';header=a.candidate/'driver/topaz-ethernet.h';iopoll=a.kernel_source/'include/linux/iopoll.h'
 text=driver.read_text();defs=header.read_text().replace('#include <linux/bits.h>','').replace('#include <linux/types.h>','')
 pre=base.PREAMBLE.replace('unsigned irq,active_speed,tx_lock;','unsigned irq,active_speed,tx_lock;\n unsigned stop_reset_attempts,stop_reset_successes;')
 pre=pre.replace('static u32 regs[256],seq[32];','static u32 regs[256],seq[32],neighbor_regs[256];\nstatic bool reset_asserted,reset_works;\nstatic unsigned reset_assertions,reset_releases;')
 pre=pre.replace('static void qtn_emac_write(struct qtn_topaz_emac *e,u32 r,u32 v){CHECK(e->regs==(unsigned char*)regs);regs[r/4]=v;event(100+r);}',r'''
static void qtn_emac_write(struct qtn_topaz_emac *e,u32 r,u32 v){
 CHECK(e->regs==(unsigned char*)regs);
 if(reset_asserted)CHECK(r==QTN_EMAC_DMA_CONFIG);
 if(r==QTN_EMAC_DMA_CONFIG){
  if(v&QTN_EMAC_DMA_CONFIG_SOFT_RESET){CHECK(!reset_asserted);reset_asserted=true;reset_assertions++;}
  else{CHECK(reset_asserted);reset_asserted=false;reset_releases++;if(reset_works){seq[0]=0;seq_count=1;seq_reads=0;}}
 }
 regs[r/4]=v;event(100+r);
}
''')
 pre=pre.replace('return regs[r/4];}', 'CHECK(!reset_asserted);return regs[r/4];}')
 pre=pre.replace('static u32 readl(void *p){CHECK(', 'static u32 readl(void *p){CHECK(!reset_asserted);CHECK(')
 pre=pre.replace('static void cpu_relax(void){}','static void cpu_relax(void){}\nstatic void udelay(unsigned us){now_us+=us;}')
 defs=defs.replace('#include <linux/bits.h>','').replace('#include <linux/types.h>','')
 fixture=pre.replace('struct qtn_topaz_emac {',defs+'\nstruct qtn_topaz_emac {')
 fixture+=''.join(poll.extract_macro(iopoll.read_text(),name) for name in ['poll_timeout_us','read_poll_timeout','readx_poll_timeout','readl_poll_timeout'])
 names=['qtn_emac_disable_irqs','qtn_emac_quiesce','qtn_emac_free_rx_buffers','qtn_emac_free_tx_buffers','qtn_emac_free_rings','qtn_emac_open','qtn_emac_stop']
 fixture+='\n'.join(base.extract(text,name) for name in names)
 # Retain existing fault cases, now failed resets still must quarantine.
 tests=base.TESTS.replace('alloc_fail=-1;request_error=hw_error=0;hw_busy=late_napi=false;',
  'alloc_fail=-1;request_error=hw_error=0;hw_busy=late_napi=false;reset_asserted=false;reset_works=false;reset_assertions=reset_releases=0;memset(neighbor_regs,0x5a,sizeof(neighbor_regs));regs[QTN_EMAC_DMA_CONFIG/4]=0x48020;')
 extra=r'''
 for(unsigned variant=0;variant<8;variant++){
  setup();CHECK(qtn_emac_open(&n)==0);e.tx_bufs[0].skb=(void*)1;e.tx_bufs[0].len=64;e.tx_head=1;
  seq[0]=(variant&1?BIT(16):BIT(21))|(variant&2?QTN_EMAC_DMA_IRQ_TX_STOPPED|QTN_EMAC_DMA_IRQ_RX_STOPPED:0);
  seq_count=1;seq_reads=0;safe_observed=false;late_napi=!!(variant&4);reset_works=true;
  u32 untouched[256];memcpy(untouched,neighbor_regs,sizeof(untouched));
  CHECK(qtn_emac_stop(&n)==0);CHECK(!e.dma_unsafe&&e.stop_reset_attempts==1&&e.stop_reset_successes==1);
  CHECK(reset_assertions==1&&reset_releases==1&&!reset_asserted);
  CHECK(regs[QTN_EMAC_DMA_CONFIG/4]==0x48020);
  CHECK(!regs[QTN_TOPAZ_EMAC_RXP_CTRL/4]&&!regs[QTN_TOPAZ_EMAC_TXP_CTRL/4]);
  CHECK(rx_frees==256&&tx_frees==1&&safe_observed);
  CHECK(memcmp(untouched,neighbor_regs,sizeof(untouched))==0);
  CHECK(qtn_emac_open(&n)==0);CHECK(!e.dma_unsafe&&e.irq_requested&&e.napi.enabled);
  seq[0]=0;seq_reads=0;CHECK(qtn_emac_stop(&n)==0);CHECK(e.stop_reset_attempts==1);
  qtn_emac_free_rings(&e);CHECK(ring_frees==1);cases++;
 }
 setup();seq[0]=BIT(21);reset_works=true;
 CHECK(qtn_emac_open(&n)==0);CHECK(e.stop_reset_successes==1&&!e.dma_unsafe);cases++;
 setup();seq[0]=BIT(16)|QTN_EMAC_DMA_IRQ_TX_STOPPED;reset_works=false;
 CHECK(qtn_emac_open(&n)==-ETIMEDOUT);CHECK(e.stop_reset_attempts==1&&!e.stop_reset_successes&&e.dma_unsafe);
 CHECK(!rx_allocs&&!desc_writes);qtn_emac_free_rings(&e);CHECK(!ring_frees);cases++;
'''
 tests=tests.replace(' printf("ETH73_LIFECYCLE_PASS',extra+'\n printf("ETH73_RESET_LIFECYCLE_PASS')
 fixture+=tests;(a.output/'fixture.c').write_text(fixture)
 cmd=['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-format','-fsanitize=undefined',str(a.output/'fixture.c'),'-o',str(a.output/'fixture')]
 c=subprocess.run(cmd,capture_output=True);(a.output/'compile.stderr').write_bytes(c.stderr);assert not c.returncode,c.stderr.decode()
 r=subprocess.run([str(a.output/'fixture')],capture_output=True);(a.output/'test.stdout').write_bytes(r.stdout);(a.output/'test.stderr').write_bytes(r.stderr)
 report={'schema':'openmitrastar.eth73-reset-fixture/v2','status':'PASS_EXTRACTED_RESET_LIFECYCLE' if r.returncode==0 else 'FAIL','output':r.stdout.decode(),
  'driver_sha256':hashlib.sha256(driver.read_bytes()).hexdigest(),'fixture_sha256':hashlib.sha256(fixture.encode()).hexdigest(),'hardware_accessed':False,
  'limits':['Simulated reset register behavior, not physical DMA stop/reset acceptance.','Neighbor bank preservation and no reads while reset are fixture assertions; physical silicon unrun.']}
 (a.output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2));assert not r.returncode,r.stderr.decode()
if __name__=='__main__':main()
