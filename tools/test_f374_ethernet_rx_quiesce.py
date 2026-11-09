"""Execute extracted F374 helper/caller with real Linux5.10 polling macro.

Run in REA-Linux with --output naming a new directory. Fake hardware maintains
independent ownership and register traces; no kernel/device/network access.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path('/workspace/user-home/Desktop/MitraStar')
SOURCE = ROOT/'work/kernel-port/f374-ethernet-rx-quiesce/qtn-topaz-emac-f352.c'
IOPOLL = Path('/home/rea/openmitrastar-f368-build-20261021/linux-5.10.260/include/linux/iopoll.h')
HEADER = ROOT/'work/kernel-port/linux-5.10/include/linux/soc/qtn/topaz-ethernet.h'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def extract_function(text, name):
    start = text.index('static int '+name+'(')
    brace = text.index('{', start)
    depth = 1
    i = brace+1
    while depth:
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
        i += 1
    return text[start:i]


def extract_macro(text, name):
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith('#define '+name+'('))
    end = start
    while lines[end].endswith('\\'):
        end += 1
    return '\n'.join(lines[start:end+1])+'\n'


PREAMBLE = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint32_t u32;
typedef uint16_t u16;
typedef uint64_t u64;
typedef uint64_t ktime_t;
#define BIT(n) (1U << (n))
#define GENMASK(h,l) ((~0U << (l)) & (~0U >> (31-(h))))
#define QTN_TOPAZ_EMAC_RX_RING_COUNT 256
#define QTN_TOPAZ_EMAC_RX_RESTART_QUIESCE_US 5000
#define QTN_TOPAZ_EMAC_RX_RESTART_COOLDOWN_MS 10000
#define lower_32_bits(n) ((u32)(n))
struct napi_struct { bool enabled; };
struct qtn_topaz_emac {
 unsigned char *regs;
 struct napi_struct napi;
 u16 rx_head;
 u32 rx_descs_dma;
 unsigned poll_rx_quiesce_timeouts,poll_rx_dma_restarts;
 unsigned rx_restart_reason_stopped,rx_restart_reason_no_desc;
 unsigned rx_restart_reason_missed,rx_restart_reason_stagnant;
 unsigned poll_same_cur_rx_pokes;
 unsigned long poll_last_progress_jiffies,poll_last_rx_restart_jiffies;
 void *ndev;
};
static unsigned assertions;
#define CHECK(v) do { assertions++;if(!(v)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#v);exit(1);}}while(0)
static u32 registers[256],descriptors[256],buffers[256];
static u32 sequence[16];
static unsigned sequence_size,reads,rearms,poll_demands,acks,bases,barriers;
static unsigned disables,enables,success_logs,event_count;
static bool observed_stopped,late_napi;
static uint64_t now_us;
static unsigned long jiffies;
struct event { unsigned kind;u32 reg,value; };
static struct event events[1024];
static void event(unsigned kind,u32 reg,u32 value){CHECK(event_count<1024);events[event_count++]=(struct event){kind,reg,value};}
static ktime_t ktime_get(void){return now_us;}
static ktime_t ktime_add_us(ktime_t a,u64 b){return a+b;}
static int ktime_compare(ktime_t a,ktime_t b){return a>b?1:a<b?-1:0;}
#define might_sleep_if(v) ((void)(v))
static void usleep_range(unsigned long low,unsigned long high){(void)low;(void)high;now_us+=2500;}
static void cpu_relax(void){}
'''

FAKES = r'''
static u32 qtn_emac_read(struct qtn_topaz_emac *emac,u32 reg){(void)emac;return registers[reg/4];}
static void qtn_emac_write(struct qtn_topaz_emac *emac,u32 reg,u32 value)
{
 (void)emac;event(1,reg,value);
 if(reg==QTN_EMAC_DMA_RX_BASE_ADDR){CHECK(observed_stopped);bases++;}
 if(reg==QTN_EMAC_DMA_STATUS_IRQ){CHECK(observed_stopped);acks++;}
 if(reg==QTN_EMAC_DMA_RX_POLL_DEMAND){CHECK(observed_stopped);poll_demands++;}
 registers[reg/4]=value;
}
static u32 readl(void *p)
{
 CHECK(p==(void*)((unsigned char*)registers+QTN_EMAC_DMA_STATUS_IRQ));
 u32 value=sequence[reads<sequence_size?reads:sequence_size-1];reads++;
 if(!(value&QTN_EMAC_DMA_RX_STATE_MASK))observed_stopped=true;
 event(2,QTN_EMAC_DMA_STATUS_IRQ,value);return value;
}
static void napi_disable(struct napi_struct *napi)
{
 CHECK(napi->enabled);disables++;napi->enabled=false;event(3,0,0);
 /* Emulate last poll completing and unmasking interrupts before disable returns. */
 if(late_napi){registers[QTN_EMAC_DMA_INT_ENABLE/4]=0x111;event(5,QTN_EMAC_DMA_INT_ENABLE,0x111);}
}
static void napi_enable(struct napi_struct *napi){CHECK(!napi->enabled);enables++;napi->enabled=true;event(4,0,0);}
static void dma_wmb(void){barriers++;}
static void qtn_emac_rearm_rx(struct qtn_topaz_emac *emac,u16 i)
{
 (void)emac;CHECK(observed_stopped);CHECK(!registers[QTN_TOPAZ_EMAC_RXP_CTRL/4]);
 CHECK(!(registers[QTN_EMAC_MAC_RX_CTRL/4]&QTN_EMAC_MAC_RX_ENABLE));
 CHECK(!(registers[QTN_EMAC_DMA_CTRL/4]&QTN_EMAC_DMA_CTRL_START_RX));
 CHECK(i<256);descriptors[i]=0x80000000U|i;rearms++;
}
static void netdev_info(void *ndev,const char *format,...){(void)ndev;(void)format;success_logs++;}
'''

TESTS = r'''
static unsigned caller(struct qtn_topaz_emac *emac,u32 dma_ctrl,u32 dma_status)
{
 int rx_restart_ret;bool rx_restarted=false;u16 rx_prod=21;u32 rx_head_status=0x80000000;
__CALLER__
rearm_poll:
 return rx_restarted;
}
static void one(const char *name,const u32 *values,unsigned count,bool timeout,
                unsigned expected_reads,unsigned variant,bool use_caller)
{
 struct qtn_topaz_emac emac={0};u32 saved_desc[256],saved_buf[256];
 u32 irq=variant>=4?0:0x110U+variant,mac=0x140U+(variant&1U),rxp=0x90U+variant;
 u32 expected_irq=irq?irq:0x111;
 u32 dma=0x80U+(variant&3U);int ret;
 memset(registers,0,sizeof(registers));memset(events,0,sizeof(events));
 for(unsigned i=0;i<256;i++){descriptors[i]=0xa0000000U+i;buffers[i]=0xb0000000U+i;}
 memcpy(saved_desc,descriptors,sizeof(saved_desc));memcpy(saved_buf,buffers,sizeof(saved_buf));
 memcpy(sequence,values,count*sizeof(*values));sequence_size=count;
 reads=rearms=poll_demands=acks=bases=barriers=disables=enables=success_logs=event_count=0;
 observed_stopped=false;late_napi=!!(variant&1U);now_us=0;jiffies=20000;
 registers[QTN_EMAC_DMA_INT_ENABLE/4]=irq;registers[QTN_EMAC_MAC_RX_CTRL/4]=mac;
 registers[QTN_TOPAZ_EMAC_RXP_CTRL/4]=rxp;registers[QTN_EMAC_DMA_CTRL/4]=dma;
 emac.regs=(unsigned char*)registers;emac.napi.enabled=true;emac.rx_head=73;emac.rx_descs_dma=0x10000;
 emac.poll_last_progress_jiffies=700;emac.poll_last_rx_restart_jiffies=900;
 emac.poll_same_cur_rx_pokes=27;emac.poll_rx_dma_restarts=4;
 emac.rx_restart_reason_stopped=3;emac.rx_restart_reason_no_desc=2;
 emac.rx_restart_reason_missed=5;emac.rx_restart_reason_stagnant=8;
 if(use_caller)ret=caller(&emac,0xdeadbeefU,QTN_EMAC_DMA_IRQ_RX_STOPPED)?0:-ETIMEDOUT;
 else ret=qtn_emac_restart_rx_dma(&emac,0xdeadbeefU);
 CHECK(ret==(timeout?-ETIMEDOUT:0));CHECK(reads==expected_reads);
 CHECK(disables==1&&enables==1&&emac.napi.enabled);CHECK(registers[QTN_EMAC_DMA_INT_ENABLE/4]==expected_irq);
 CHECK(memcmp(buffers,saved_buf,sizeof(buffers))==0);
 /* Parser must be stopped after NAPI completion's possible late unmask. */
 unsigned parser=0;while(parser<event_count&&!(events[parser].kind==1&&events[parser].reg==QTN_TOPAZ_EMAC_RXP_CTRL))parser++;
 CHECK(parser<event_count&&parser>0);CHECK(events[parser-1].kind==1&&events[parser-1].reg==QTN_EMAC_DMA_INT_ENABLE&&events[parser-1].value==0);
 if(timeout){
  CHECK(!observed_stopped);CHECK(!rearms&&!poll_demands&&!acks&&!bases&&!barriers);
  CHECK(emac.rx_head==73);CHECK(memcmp(descriptors,saved_desc,sizeof(descriptors))==0);
  CHECK(registers[QTN_EMAC_DMA_CTRL/4]==dma);CHECK(registers[QTN_EMAC_MAC_RX_CTRL/4]==mac);CHECK(registers[QTN_TOPAZ_EMAC_RXP_CTRL/4]==rxp);
  CHECK(event_count>=5);
  struct event *tail=events+event_count-5;
  CHECK(tail[0].kind==1&&tail[0].reg==QTN_EMAC_DMA_CTRL&&tail[0].value==dma);
  CHECK(tail[1].kind==1&&tail[1].reg==QTN_EMAC_MAC_RX_CTRL&&tail[1].value==mac);
  CHECK(tail[2].kind==1&&tail[2].reg==QTN_TOPAZ_EMAC_RXP_CTRL&&tail[2].value==rxp);
  CHECK(tail[3].kind==4);CHECK(tail[4].kind==1&&tail[4].reg==QTN_EMAC_DMA_INT_ENABLE&&tail[4].value==expected_irq);
  CHECK(emac.poll_same_cur_rx_pokes==27&&emac.poll_last_progress_jiffies==700);
  CHECK(emac.poll_rx_dma_restarts==4);CHECK(emac.rx_restart_reason_stopped==3&&emac.rx_restart_reason_no_desc==2&&emac.rx_restart_reason_missed==5&&emac.rx_restart_reason_stagnant==8);
  CHECK(success_logs==0);
 }else{
  CHECK(observed_stopped&&rearms==256&&poll_demands==1&&acks==1&&bases==1&&barriers==1);
  CHECK(emac.rx_head==0);CHECK(registers[QTN_EMAC_DMA_CTRL/4]==(dma|QTN_EMAC_DMA_CTRL_START_RX));
  CHECK(registers[QTN_EMAC_MAC_RX_CTRL/4]==(mac|QTN_EMAC_MAC_RX_ENABLE));
  if(use_caller){CHECK(emac.poll_rx_dma_restarts==5&&emac.rx_restart_reason_stopped==4);CHECK(emac.poll_same_cur_rx_pokes==0&&emac.poll_last_progress_jiffies==jiffies);CHECK(success_logs==1);}
 }
 if(use_caller){CHECK(emac.poll_last_rx_restart_jiffies==jiffies);CHECK(emac.poll_rx_quiesce_timeouts==(timeout?1:0));}
 else CHECK(emac.poll_last_rx_restart_jiffies==900&&emac.poll_rx_quiesce_timeouts==0);
 printf("case=%s variant=%u caller=%u PASS\n",name,variant,use_caller);
}
int main(void)
{
 u32 immediate[]={0};
 u32 latched_busy[]={QTN_EMAC_DMA_IRQ_RX_STOPPED|BIT(21),QTN_EMAC_DMA_IRQ_RX_STOPPED|BIT(21),0};
 u32 permanent[]={BIT(21)};
 u32 latched_permanent[]={QTN_EMAC_DMA_IRQ_RX_STOPPED|BIT(21)};
 u32 final_read[]={BIT(21),BIT(21),BIT(21),BIT(21),0};
 for(unsigned variant=0;variant<6;variant++)for(unsigned call=0;call<2;call++){
  one("immediate-stop",immediate,1,false,1,variant,call);
  one("latched-stop-still-busy",latched_busy,3,false,3,variant,call);
  one("permanent-busy",permanent,1,true,5,variant,call);
  one("latched-stop-permanent-busy",latched_permanent,1,true,5,variant,call);
  one("success-on-final-read",final_read,5,false,5,variant,call);
 }
 printf("F374_RX_QUIESCE_PASS cases=60 assertions=%u hardware_actions=0\n",assertions);
 return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=SOURCE)
    parser.add_argument('--candidate', type=Path, help='Candidate folder; selects its unchanged driver filename.')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.candidate:
        args.source = args.candidate/'qtn-topaz-emac-f352.c'
    args.output.mkdir(parents=True, exist_ok=False)
    pins = {str(p): sha(p) for p in (args.source, IOPOLL, HEADER, Path(__file__))}
    text = args.source.read_text()
    helper = extract_function(text, 'qtn_emac_restart_rx_dma')
    start = text.index('\t\t\t/* Cool down failed attempts too;')
    end = text.index('\n\t\t}\n\t}\n\nrearm_poll:', start)
    caller = text[start:end]
    header = HEADER.read_text().replace('#include <linux/bits.h>', '').replace('#include <linux/types.h>', '')
    macros = ''.join(extract_macro(IOPOLL.read_text(), n) for n in ('read_poll_timeout', 'readx_poll_timeout', 'readl_poll_timeout'))
    fixture = PREAMBLE+header+FAKES+macros+helper+'\n'+TESTS.replace('__CALLER__', caller)
    source = args.output/'fixture.c'
    source.write_text(fixture)
    command = ['cc', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror', '-fsanitize=undefined', str(source), '-o', str(args.output/'fixture')]
    proc = subprocess.run(command, capture_output=True)
    (args.output/'compile.stdout').write_bytes(proc.stdout)
    (args.output/'compile.stderr').write_bytes(proc.stderr)
    report = {'schema': 'openmitrastar.f374-rx-quiesce-fixture/v1', 'status': 'FAIL_OFFLINE_FIXTURE',
              'hardware_actions': False, 'source_pins': pins, 'compile_command': command,
              'fixture_sha256': sha(source), 'compile_exit_code': proc.returncode}
    if proc.returncode == 0:
        run = subprocess.run([str(args.output/'fixture')], capture_output=True)
        (args.output/'test.stdout').write_bytes(run.stdout)
        (args.output/'test.stderr').write_bytes(run.stderr)
        report['test_exit_code'] = run.returncode
        report['test_output'] = run.stdout.decode()
        if run.returncode == 0:
            report['status'] = 'PASS_OFFLINE_EXTRACTED_HELPER_AND_CALLER'
    for p, digest in pins.items():
        assert sha(p) == digest, 'input changed during fixture '+p
    report['inputs_unchanged'] = True
    (args.output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'result': str(args.output/'result.json'), 'status': report['status']}))
    return int(report['status'] != 'PASS_OFFLINE_EXTRACTED_HELPER_AND_CALLER')


if __name__ == '__main__':
    raise SystemExit(main())
