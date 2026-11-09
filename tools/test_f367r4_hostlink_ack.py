"""Run the actual producer and selected consumers with explicit fake mailbox completion."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,subprocess
from test_f355_lifetime import extract
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'work/kernel-port/f367r4-hostlink-ack/qdrv/qdrv'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def linux(p):p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
PRE=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <errno.h>
#include <stdio.h>
typedef uint32_t u32;typedef uintptr_t dma_addr_t;
#define HZ 200ul
#define QTN_HLINK_RC_DONE 1u
#define QTN_HLINK_RC_ERR 2u
#define QTN_CALSTATE_DEFAULT 0
#define IOCTL_DEV_CHANGE_CHANNEL 17
#define IOCTL_DEV_CHANGE_CHAN_DEFERRED 35
#define IOCTL_DEV_XMITCTL 26
#define IOCTL_DEV_BEACON_START 6
#define DBGPRINTF(...) do{}while(0)
#define DBGPRINTF_E(...) do{}while(0)
#define pr_info(...) do{}while(0)
#define pr_err(...) do{}while(0)
#define pr_err_ratelimited(...) do{}while(0)
#define KASSERT(v,unused) assert(v)
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x,v) ((x)=(v))
#define dma_wmb() do{}while(0)
#define wmb() do{}while(0)
#define container_of(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))
struct host_ioctl{u32 ioctl_command,ioctl_dev,ioctl_arg1,ioctl_arg2,ioctl_rc,ioctl_status;};
struct qtn_csa_info{int unused;};struct channel{bool radar;};
struct ieee80211com{int ic_pm_enabled;struct channel*ic_curchan;};
struct qdrv_mac{bool dead;unsigned ioctl_fail_count;};
struct qdrv_wlan{struct ieee80211com ic;struct qdrv_mac*mac;int unit,flowlock;struct{u32 tx_mbox[1];struct host_ioctl*hl_ring;uintptr_t hl_ring_dma;}tx_if;};
static struct{int calstate;}shared;static struct{int calstate;}*soc_shared_params;
static struct qdrv_wlan live;static struct qdrv_mac mac;static struct host_ioctl descriptors[1];static struct channel channel;
static unsigned long jiffies;static u32 firmware_rc;static unsigned published,freed,slept,done_after,checks,channel_faults,channel_passes;static int last_fault;static bool fail_alloc;
static int in_interrupt(void){return 0;}static int in_irq(void){return 0;}
static bool of_machine_is_compatible(const char*s){(void)s;return false;}
static bool time_after(unsigned long a,unsigned long b){return (long)(b-a)<0;}
static void msleep(unsigned n){(void)n;jiffies++;slept++;if(done_after&&slept>=done_after)descriptors[0].ioctl_rc=firmware_rc;}
static void udelay(unsigned n){(void)n;jiffies++;}
#define spin_lock_irqsave(l,f) do{assert((l)==&live.flowlock);(f)=0;}while(0)
#define spin_unlock_irqrestore(l,f) do{assert((l)==&live.flowlock);(void)(f);}while(0)
static void qdrv_mac_interrupt_muc(struct qdrv_mac*m){assert(m==&mac);published++;live.tx_if.tx_mbox[0]=0;descriptors[0].ioctl_rc=done_after?0:firmware_rc;}
static void qdrv_free_ioctl(struct host_ioctl*p){assert(p==descriptors);freed++;p->ioctl_status=1;}
static void qdrv_mac_die_action(struct qdrv_mac*m){m->dead=true;}
static struct host_ioctl*qdrv_alloc_ioctl(struct qdrv_wlan*qw){assert(qw==&live);if(fail_alloc)return NULL;memset(descriptors,0,sizeof(descriptors));descriptors[0].ioctl_dev=qw->unit;return descriptors;}
static struct{struct ieee80211com*ic;bool xmit_stopped,enabled;}qdrv_radar_cb;
static struct{bool tx_fault,needs_cac;}qdrv_f338_health;
static bool required;
static bool qdrv_f332_ready_stopping(void){return false;}
static bool qdrv_f338_detector_required(void){return required;}
static u32 qdrv_f332_generation(void){return 7;}
static bool qdrv_f338_needs_cac(void){return qdrv_f338_health.needs_cac;}
static bool qdrv_f367_tx_allowed(void){return true;}
static bool ieee80211_is_chan_radar_detected(struct channel*c){return c->radar;}
static void qdrv_f367_channel_fault(int rc){channel_faults++;last_fault=rc;}
static void reset(u32 raw){memset(&live,0,sizeof(live));memset(&mac,0,sizeof(mac));memset(&qdrv_f338_health,0,sizeof(qdrv_f338_health));channel.radar=false;live.ic.ic_curchan=&channel;live.mac=&mac;live.tx_if.hl_ring=descriptors;live.tx_if.hl_ring_dma=0x100000;firmware_rc=raw;published=freed=slept=done_after=0;fail_alloc=false;jiffies=0;channel_faults=channel_passes=0;last_fault=0;qdrv_radar_cb.ic=&live.ic;qdrv_radar_cb.xmit_stopped=false;qdrv_radar_cb.enabled=true;required=false;soc_shared_params=(void*)&shared;shared.calstate=0;}
#define CHECK(v) do{checks++;assert(v);}while(0)
'''
TEST=r'''
int main(void){struct qtn_csa_info csa;struct host_ioctl*p;int (*legacy)(struct qdrv_wlan*,struct host_ioctl*)=qdrv_send_ioctl;
 reset(1);run_channel_consumer();CHECK(channel_passes==1&&!channel_faults&&published==1&&freed==1);CHECK(descriptors[0].ioctl_command==17);
 reset(1);CHECK(qdrv_hostlink_setchan_deferred(&live,&csa)==0&&published==1&&freed==1);CHECK(descriptors[0].ioctl_command==35);
 reset(1);CHECK(qdrv_f338_force_tx_off()&&qdrv_radar_cb.xmit_stopped&&!qdrv_f338_health.tx_fault);CHECK(descriptors[0].ioctl_command==26&&descriptors[0].ioctl_arg1==0);
 reset(1);qdrv_radar_cb.xmit_stopped=true;required=true;CHECK(qdrv_f338_enable_tx()&&!qdrv_radar_cb.xmit_stopped&&!qdrv_f338_health.tx_fault);CHECK(descriptors[0].ioctl_arg1==1);
 reset(2);run_channel_consumer();CHECK(channel_faults==1&&!channel_passes&&last_fault==-EIO);
 reset(3);CHECK(!qdrv_f338_force_tx_off()&&qdrv_f338_health.tx_fault&&!qdrv_radar_cb.xmit_stopped);
 reset(3);qdrv_radar_cb.xmit_stopped=true;CHECK(!qdrv_f338_enable_tx()&&qdrv_f338_health.tx_fault);
 reset(0);CHECK(qdrv_hostlink_setchan(&live,1,36)==QDRV_IOCTL_RET_TIMEOUT&&published==1&&freed==1&&slept>0);
 reset(1);done_after=3;CHECK(qdrv_hostlink_setchan(&live,1,36)==0&&slept==3);
 reset(1);mac.dead=true;CHECK(qdrv_hostlink_setchan(&live,1,36)==-ENODEV&&!published&&freed==1);
 reset(1);mac.dead=true;CHECK(!qdrv_f338_force_tx_off()&&qdrv_f338_health.tx_fault&&!published);
 reset(1);mac.dead=true;p=qdrv_alloc_ioctl(&live);CHECK(legacy(&live,p)==1&&!published&&freed==1);
 reset(1);p=qdrv_alloc_ioctl(&live);CHECK(legacy(&live,p)==1&&published==1);
 reset(3);p=qdrv_alloc_ioctl(&live);CHECK(legacy(&live,p)==3&&published==1);
 reset(1);fail_alloc=true;CHECK(qdrv_hostlink_setchan(&live,1,36)==-ENOMEM&&!published&&!freed);
 reset(1);fail_alloc=true;CHECK(qdrv_hostlink_xmitctl(&live,false)==-ENOMEM&&!published);
 CHECK(qdrv_completed_ack_result(0)==-EIO&&qdrv_completed_ack_result(2)==-EIO&&qdrv_completed_ack_result(3)==-EIO);
 CHECK(qdrv_completed_ack_result(1)==0&&qdrv_completed_ack_result(5)==0&&qdrv_completed_ack_result(4)==-EIO);
 CHECK(qdrv_completed_ack_result(-ENOMEM)==-ENOMEM&&qdrv_completed_ack_result(-1)==-1);
 printf("F367R4_REAL_HOSTLINK_CONTRACT_PASS checks=%u producer_body=actual channel_consumer=actual tx_consumers=actual hardware=0\n",checks);return 0;}
'''
def main():
 out=ROOT/'outputs/preflight'/('f367r4-hostlink-ack-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True,exist_ok=False)
 h=(SOURCE/'qdrv_hostlink.c').read_text();r=(SOURCE/'qdrv_radar.c').read_text();a=(SOURCE/'qdrv_f338_availability.inc').read_text();w=(SOURCE/'qdrv_wlan.c').read_text()
 start=h.index('#define QDRV_IOCTL_EVNT_TIMEOUT');end=h.index('/* F367r4:',start);definitions=h[start:end]
 names=('qdrv_completed_ack_result','qdrv_send_ioctl_owned','qdrv_send_ioctl','qdrv_send_ioctl_ack','qdrv_hostlink_setchan','qdrv_hostlink_setchan_deferred','qdrv_hostlink_xmitctl')
 code=PRE+definitions+'\n'.join(extract(h,n) for n in names)+'\n'+extract(r,'sys_raw_enable_xmit')+extract(r,'sys_raw_disable_xmit')+extract(a,'qdrv_f338_force_tx_off')+extract(a,'qdrv_f338_enable_tx')
 consumer='{int rc=qdrv_hostlink_setchan(qw,freq_band,qtn_chan);\n\t if(rc){qdrv_f367_channel_fault(rc);return;}}'
 assert consumer in w
 code+='\nstatic void run_channel_consumer(void){struct qdrv_wlan*qw=&live;u32 freq_band=1,qtn_chan=36;'+consumer+'channel_passes++;}\n'+TEST
 (out/'test.c').write_bytes(code.encode());script=f"set -eu\ncc -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-variable -Wno-unused-but-set-variable -Wno-unused-function -Wno-pointer-to-int-cast -Wno-int-to-pointer-cast '{linux(out/'test.c')}' -o '{linux(out/'test')}'\n'{linux(out/'test')}'\n";(out/'run.sh').write_bytes(script.encode())
 p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True,timeout=30)
 result={'schema':'openmitrastar.f367r4-hostlink-test/v1','status':'PASS_REAL_PRODUCER_AND_CHANNEL_TX_CONSUMERS' if not p.returncode else 'FAIL','stdout':p.stdout.strip(),'stderr':p.stderr[-5000:],'source_pins':{str(SOURCE/n):sha(SOURCE/n) for n in ('qdrv_hostlink.c','qdrv_radar.c','qdrv_f338_availability.inc','qdrv_wlan.c')},'hardware_actions':False,'fake_boundary':'mailbox, IRQ, wait clock, alloc/free; source producer and consumer bodies execute unchanged'}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'result':str(out/'result.json'),**result},indent=2));return p.returncode
if __name__=='__main__':raise SystemExit(main())
