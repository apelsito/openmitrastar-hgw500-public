"""ActualLinuxbridge+faithfulcore fixture with explicitfaketimer/provider/lifetime."""
import argparse,hashlib,json,subprocess
from pathlib import Path
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
PRE=r'''#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <stdio.h>
#include "openmitrastar_rbsdfs_recovered.h"
typedef uint32_t u32;typedef uint8_t u8;typedef int spinlock_t;
#define EINVAL 22
#define EBUSY 16
#define EAGAIN 11
#define EOPNOTSUPP 95
#define EACCES 13
#define HZ 200
#define EXPORT_SYMBOL(x)
#define IEEE80211_M_HOSTAP 6
#define IEEE80211_S_RUN 4
#define IEEE80211_CHAN_DFS_CAC_IN_PROGRESS 0x1000000U
#define IEEE80211_CHAN_ANYC ((struct ieee80211_channel*)(uintptr_t)0xffff)
#define container_of(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))
#define from_timer(v,t,m) container_of(t,struct om_rbsdfs_kernel_state,m)
#define time_before(a,b) ((int32_t)((uint32_t)(a)-(uint32_t)(b))<0)
#define time_after_eq(a,b) (!time_before(a,b))
static unsigned locks,arms,joins;static uint32_t jiffies;static unsigned expiration_order;
struct timer_list {void(*fn)(struct timer_list*);uint32_t expires;unsigned pending;};
#define spin_lock_init(p) (*(p)=0)
#define spin_lock_irqsave(p,f) do{assert(!locks);*(p)=1;locks++;f=0;}while(0)
#define spin_unlock_irqrestore(p,f) do{assert(locks==1);*(p)=0;locks--;(void)f;}while(0)
static void timer_setup(struct timer_list*t,void(*fn)(struct timer_list*),int f){memset(t,0,sizeof(*t));t->fn=fn;}
static int mod_timer(struct timer_list*t,unsigned long expiry){t->expires=(u32)expiry;t->pending=1;arms++;return 0;}
static int del_timer_sync(struct timer_list*t){assert(!locks);t->pending=0;joins++;return 0;}
struct ieee80211com;struct ieee80211vap;struct ieee80211_node;struct sk_buff;
'''
TAIL=r'''
struct ieee80211_channel {u32 ic_flags;u8 ic_ieee;};
struct ieee80211_node {unsigned refs;};struct sk_buff {unsigned live;};
struct ieee80211vap {struct ieee80211com*iv_ic;int iv_opmode,iv_state;};
struct ieee80211com {struct om_rbsdfs_kernel_state om_rbsdfs;unsigned ic_extender_role;
 struct ieee80211_channel chan,*ic_curchan;
 int(*ic_chan_compare_equality)(struct ieee80211com*,struct ieee80211_channel*,struct ieee80211_channel*);
 int(*ic_get_chan_availability_status_by_chan_num)(struct ieee80211com*,struct ieee80211_channel*);};
static unsigned claims,node_frees;static int claim_result;
int om_qdrv_rbsdfs_claim_lifetime(const char*name){assert(locks==1);claims++;return claim_result;}
static void ieee80211_free_node(struct ieee80211_node*ni){assert(!locks&&ni->refs);ni->refs--;node_frees++;}
static unsigned finds,equalities,statusreads;static int equalresult=1,statusfirst=4,statussecond=8,wds_rbs;
static struct ieee80211_channel*ieee80211_find_channel_by_ieee(struct ieee80211com*ic,u32 c){finds++;return c==ic->chan.ic_ieee?&ic->chan:NULL;}
static int equal_current(struct ieee80211com*ic,struct ieee80211_channel*a,struct ieee80211_channel*b){assert(locks&&b==&ic->chan);equalities++;return equalresult;}
static int channel_status(struct ieee80211com*ic,struct ieee80211_channel*c){assert(locks&&c==ic->ic_curchan);return statusreads++?statussecond:statusfirst;}
static int ieee80211_scs_is_wds_rbs_node(struct ieee80211com*ic){return wds_rbs;}
struct fake {unsigned opened,closed,validated,granted,sent,revoked;int open,close,valid,grant,send,revoke;unsigned role;u32 channel,deadline;};
static struct fake fake;
static int open_window(void*x,unsigned role,u32 c,u32 d){struct fake*f=x;assert(locks);assert(claims);f->opened++;f->role=role;f->channel=c;f->deadline=d;return f->open;}
static int close_window(void*x,u32 c){struct fake*f=x;assert(locks);f->closed++;assert(c==f->channel);return f->close;}
static int validate_frame(void*x,const void*frame,unsigned role,u32 c){struct fake*f=x;assert(locks&&frame);f->validated++;assert(role==f->role&&c==f->channel);return f->valid;}
static int grant_frame(void*x,const void*frame){struct fake*f=x;assert(locks&&frame);assert(claims>=2);f->granted++;return f->grant;}
static int send_frame(void*x,const void*frame){struct fake*f=x;assert(locks&&frame);f->sent++;return f->send;}
static int revoke_frame(void*x,const void*frame){struct fake*f=x;assert(locks&&frame);f->revoked++;return f->revoke;}
static const struct om_rbsdfs_kernel_provider provider={{&fake,validate_frame,grant_frame,send_frame,revoke_frame},open_window,close_window};
static void setup(struct ieee80211com*ic){claims=node_frees=0;claim_result=0;memset(ic,0,sizeof(*ic));om_ieee80211_rbsdfs_init(ic);ic->chan.ic_ieee=52;ic->ic_curchan=&ic->chan;ic->ic_chan_compare_equality=equal_current;ic->ic_get_chan_availability_status_by_chan_num=channel_status;ic->ic_extender_role=2;memset(&fake,0,sizeof(fake));fake.open=fake.close=fake.valid=fake.grant=fake.send=fake.revoke=1;finds=equalities=statusreads=arms=joins=0;equalresult=1;statusfirst=4;statussecond=8;wds_rbs=0;}
'''
TEST=r'''
int main(void){struct ieee80211com ic;struct ieee80211vap vap;struct ieee80211_node ni={1};struct sk_buff skb={1};u32 v;unsigned cases=0;
setup(&ic);assert(!ic.om_rbsdfs.provider&&ic.om_rbsdfs.initialized&&!ic.om_rbsdfs.stopping&&ic.om_rbsdfs.core.end_tx_ms==500);cases++;
for(unsigned ms=0;ms<=1001;ms++){setup(&ic);v=ms;int rc=om_ieee80211_rbsdfs_policy(&ic,468,&v,1);assert(rc==((ms>=1&&ms<=1000)?0:-22));v=0;assert(!om_ieee80211_rbsdfs_policy(&ic,468,&v,0)&&v==((ms>=1&&ms<=1000)?ms:500));cases++;}
for(unsigned ms=1;ms<=1000;ms++)for(unsigned role=1;role<=2;role++){
setup(&ic);vap.iv_ic=&ic;vap.iv_opmode=6;vap.iv_state=4;ic.ic_extender_role=role;v=1;assert(!om_ieee80211_rbsdfs_policy(&ic,466,&v,1));v=ms;assert(!om_ieee80211_rbsdfs_policy(&ic,468,&v,1));jiffies=0xfffffff0U;
struct om_rbsdfs_state old=ic.om_rbsdfs.core;int rc=role==2?om_ieee80211_rbsdfs_radar(&ic,1,52):om_ieee80211_rbsdfs_mbs(&vap,1,52);assert(rc==-95&&!memcmp(&old,&ic.om_rbsdfs.core,sizeof(old))&&!fake.opened&&!arms);cases++;
ic.om_rbsdfs.provider=&provider;rc=role==2?om_ieee80211_rbsdfs_radar(&ic,1,52):om_ieee80211_rbsdfs_mbs(&vap,1,52);u32 end=(u32)(0xfffffff0U+ms*200/1000U);assert(rc==1&&fake.opened==1&&fake.deadline==end&&fake.role==role&&ic.om_rbsdfs.timer.expires==end&&ic.om_rbsdfs.window_active);cases++;
jiffies=end-1;ic.om_rbsdfs.timer.fn(&ic.om_rbsdfs.timer);assert(!fake.closed&&ic.om_rbsdfs.window_active);cases++;
jiffies=end;ic.om_rbsdfs.timer.fn(&ic.om_rbsdfs.timer);assert(fake.closed==1&&!ic.om_rbsdfs.window_active&&!ic.om_rbsdfs.quarantined&&finds==1&&equalities==1);assert((role==2?ic.om_rbsdfs.core.allow_rbs_report:ic.om_rbsdfs.core.allow_mbs_csa)==1);cases++;
assert(!om_ieee80211_rbsdfs_stop(&ic)&&joins==1&&ic.om_rbsdfs.stopping);assert(om_ieee80211_rbsdfs_radar(&ic,1,52)==-16&&!locks);assert(!om_ieee80211_rbsdfs_resume(&ic)&&!ic.om_rbsdfs.stopping&&!ic.om_rbsdfs.core.allow_rbs_report&&!ic.om_rbsdfs.core.allow_mbs_csa);cases++;
}
for(unsigned eq=0;eq<2;eq++){setup(&ic);ic.om_rbsdfs.provider=&provider;ic.om_rbsdfs.core.measurement_in_cac=1;jiffies=100;assert(om_ieee80211_rbsdfs_radar(&ic,1,52)==1);equalresult=eq;jiffies=200;ic.om_rbsdfs.timer.fn(&ic.om_rbsdfs.timer);assert(fake.closed==1&&!ic.om_rbsdfs.window_active&&!ic.om_rbsdfs.quarantined);cases++;}
for(int open=-1;open<=2;open++){setup(&ic);ic.om_rbsdfs.provider=&provider;ic.om_rbsdfs.core.measurement_in_cac=1;fake.open=open;jiffies=100;int rc=om_ieee80211_rbsdfs_radar(&ic,1,52);if(open==1)assert(rc==1&&ic.om_rbsdfs.window_active&&arms);else assert(rc==(open==0?-95:-16)&&!ic.om_rbsdfs.core.allow_rbs_report&&!arms&&ic.om_rbsdfs.quarantined==(open!=0));if(ic.om_rbsdfs.quarantined)assert(om_ieee80211_rbsdfs_stop(&ic)==-16&&om_ieee80211_rbsdfs_resume(&ic)==-16);cases++;}
for(unsigned role=1;role<=2;role++)for(int grant=-1;grant<=2;grant++)for(int send=-1;send<=2;send++)for(int revoke=-1;revoke<=2;revoke++){
setup(&ic);vap.iv_ic=&ic;vap.iv_opmode=6;vap.iv_state=4;ic.ic_extender_role=role;ic.om_rbsdfs.provider=&provider;ic.om_rbsdfs.core.measurement_in_cac=1;jiffies=100;assert((role==2?om_ieee80211_rbsdfs_radar(&ic,1,52):om_ieee80211_rbsdfs_mbs(&vap,1,52))==1);fake.grant=grant;fake.send=send;fake.revoke=revoke;ni.refs=1;int rc=om_ieee80211_rbsdfs_send(&ic,&ni,&skb,1);assert(fake.validated==1&&fake.granted==1);if(grant==0)assert(rc==-95&&!fake.sent&&!fake.revoked&&!ic.om_rbsdfs.frame.active);else if(grant!=1)assert(rc==2&&!fake.sent&&!fake.revoked&&ic.om_rbsdfs.retained_node==&ni&&ic.om_rbsdfs.frame.frame==&skb);else{assert(fake.sent==1&&fake.revoked==1);if((send!=0&&send!=1)||revoke!=1)assert(rc==2&&ic.om_rbsdfs.retained_node==&ni);else assert(rc==(send==1?1:-95)&&!ic.om_rbsdfs.frame.active);}assert(node_frees==(rc==1)&&ni.refs==(rc==1?0U:1U));if(rc==2){unsigned n=fake.granted;assert(om_ieee80211_rbsdfs_send(&ic,&ni,&skb,1)==-16&&fake.granted==n);assert(om_ieee80211_rbsdfs_stop(&ic)==-16&&om_ieee80211_rbsdfs_resume(&ic)==-16);}cases++;
}
setup(&ic);ic.om_rbsdfs.provider=&provider;ic.om_rbsdfs.core.measurement_in_cac=1;claim_result=-16;jiffies=100;assert(om_ieee80211_rbsdfs_radar(&ic,1,52)==-16&&!fake.opened&&!arms&&!ic.om_rbsdfs.core.allow_rbs_report);cases++;
setup(&ic);ic.om_rbsdfs.core.measurement_in_cac=1;assert(om_ieee80211_rbsdfs_send(&ic,&ni,&skb,1)==-13&&statusreads==1);statusreads=0;statusfirst=1;assert(om_ieee80211_rbsdfs_send(&ic,&ni,&skb,1)==-13&&statusreads==2);statusreads=0;statussecond=1;ic.chan.ic_flags=0x1000000U;assert(om_ieee80211_rbsdfs_send(&ic,&ni,&skb,1)==-13);ic.chan.ic_flags=0;assert(om_ieee80211_rbsdfs_send(&ic,&ni,&skb,1)==0);cases++;
assert(!locks);printf("{\"cases\":%u,\"all_delay_values\":1000,\"missing_provider_no_mutation\":true,\"actual_timer_early_expired\":true,\"stop_timer_join_outside_lock\":true,\"unknown_pins_frame_node_no_resume\":true}\n",cases);return 0;}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);hp=a.candidate/'headers/net80211/ieee80211_var.h';h=hp.read_text();start=h.index('struct om_rbsdfs_kernel_provider {');end=h.index('struct ieee80211com {',start);api=h[start:end];core=a.candidate/'source/wlan/openmitrastar_rbsdfs_recovered.c';inc=a.candidate/'source/wlan/openmitrastar_rbsdfs_kernel.inc';f=a.output/'actual-kernel-bridge.c';f.write_text(PRE+api+TAIL+core.read_text()+'\n'+inc.read_text()+'\n'+TEST);cmd=[str(a.compiler),'-O1','-std=c11','-I'+str(a.candidate/'headers/net80211'),str(f),'-o',str(a.output/'fixture.exe')];r=subprocess.run(cmd,capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,(r.returncode,r.stderr.decode());v=json.loads(r.stdout);pins={str(p):sha(p)for p in[hp,core,inc,a.candidate/'headers/net80211/openmitrastar_rbsdfs_recovered.h',a.compiler,Path(__file__),f,a.output/'fixture.exe']};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');result=dict(status='PASS_SOURCE_ONLY_RBSDFS_R3_ACTUAL_BRIDGE_F355_NODE_TIMER_FIXTURE',hardware_accessed=False,firmware_eligible=False,**v,limits='Actualcore/API/kernelbridgebodies withfakeIRQtimer/provider/nodealloc; nograntproviderorwholemodule/lifetimephysicalproof');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
