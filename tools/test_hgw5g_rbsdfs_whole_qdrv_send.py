"""WholeactualQDRVsend + actualkernel/core ownership/F355 ordering fixture."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from test_hgw5g_dfs467_refreshed_pick import extract
import test_hgw5g_rbsdfs_kernel_r3 as base
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists();a.output.mkdir(parents=True);header=a.candidate/'headers/net80211/ieee80211_var.h';h=header.read_text();api=h[h.index('struct om_rbsdfs_kernel_provider {'):h.index('struct ieee80211com {',h.index('struct om_rbsdfs_kernel_provider {'))];source=a.candidate/'source/qdrv/qdrv_wlan.c';s=source.read_text();fn=extract(s,s.index('static int qdrv_wlan_80211_send('));tail=base.TAIL
 tail=tail.replace('struct ieee80211_node {unsigned refs;};struct sk_buff {unsigned live;};','struct ieee80211_node {unsigned refs;struct ieee80211vap*ni_vap;unsigned ni_node_idx;};\nstruct net_device {unsigned dummy;};\nstruct sk_buff {unsigned live;struct net_device*dev;unsigned dest_port,priority;struct{void*ni;unsigned encap,flags;}cb;};')
 tail=tail.replace('struct ieee80211com {struct om_rbsdfs_kernel_state om_rbsdfs;unsigned ic_extender_role;','struct ieee80211com {struct om_rbsdfs_kernel_state om_rbsdfs;unsigned ic_extender_role;struct{unsigned sta_dfs_strict_mode,allow_measurement_report;}sta_dfs_info;')
 tail=tail.replace('static unsigned claims,node_frees;','static unsigned claims,node_frees,skb_frees,queued;')
 tail=tail.replace('static int send_frame(void*x,const void*frame){struct fake*f=x;assert(locks&&frame);f->sent++;return f->send;}','static int send_frame(void*x,const void*frame){struct fake*f=x;struct sk_buff*skb=(void*)frame;assert(locks&&frame);f->sent++;if(f->send==1){assert(skb->live);skb->live=0;skb_frees++;}return f->send;}')
 tail=tail.replace('claims=node_frees=0;','claims=node_frees=skb_frees=queued=0;')
 shim=r'''
struct qdrv_vap {struct ieee80211vap iv;struct net_device*ndev;};
#define QTN_SKB_CB_NI(s) ((s)->cb.ni)
#define QTN_SKB_ENCAP(s) ((s)->cb.encap)
#define QTN_SKB_ENCAP_80211_MGMT 1
#define QTN_SKB_ENCAP_80211_DATA 2
#define M_NO_AMSDU 0x400
#define false 0
#define M_FLAG_SET(s,f) ((s)->cb.flags|=(f))
static int ieee80211_is_chan_radar_detected(struct ieee80211_channel*c){return c&&c->ic_flags&0x1000;}
static int ieee80211_is_chan_cac_required(struct ieee80211_channel*c){return c&&c->ic_flags&0x800000;}
static void dev_kfree_skb_any(struct sk_buff*s){assert(!locks&&s->live);s->live=0;skb_frees++;}
static int dev_queue_xmit(struct sk_buff*s){assert(!locks&&s->live);s->live=0;skb_frees++;queued++;return 0;}
'''
 test=r'''
int main(void){struct ieee80211com ic;struct qdrv_vap qv;struct net_device dev;struct ieee80211_node ni;struct sk_buff skb;unsigned cases=0;
for(unsigned mode=0;mode<6;mode++){
setup(&ic);memset(&qv,0,sizeof(qv));memset(&ni,0,sizeof(ni));memset(&skb,0,sizeof(skb));qv.iv.iv_ic=&ic;qv.iv.iv_opmode=6;qv.iv.iv_state=4;qv.ndev=&dev;ni.refs=1;ni.ni_vap=&qv.iv;ni.ni_node_idx=7;skb.live=1;jiffies=100;
if(mode){ic.om_rbsdfs.core.measurement_in_cac=1;if(mode!=1){ic.om_rbsdfs.provider=&provider;assert(om_ieee80211_rbsdfs_radar(&ic,1,52)==1);} }
if(mode==3)fake.grant=2;
if(mode==4)fake.revoke=2;
if(mode==5)fake.grant=0;
assert(qdrv_wlan_80211_send(&ic,&ni,&skb,3,1)==0);assert(skb.cb.ni==&ni&&skb.cb.encap==1&&skb.cb.flags==0x400&&skb.dest_port==7&&skb.priority==3);
if(mode==0)assert(queued==1&&node_frees==1&&skb_frees==1&&ni.refs==0&&!skb.live&&!claims);
if(mode==1)assert(!queued&&node_frees==1&&skb_frees==1&&ni.refs==0&&!skb.live&&!claims&&!fake.granted);
if(mode==2)assert(!queued&&node_frees==1&&skb_frees==1&&ni.refs==0&&!skb.live&&claims==2&&fake.sent==1&&fake.revoked==1);
if(mode==3)assert(!queued&&!node_frees&&!skb_frees&&ni.refs==1&&skb.live&&claims==2&&fake.granted==1&&!fake.sent&&ic.om_rbsdfs.retained_node==&ni&&ic.om_rbsdfs.frame.frame==&skb);
if(mode==4)assert(!queued&&!node_frees&&skb_frees==1&&ni.refs==1&&!skb.live&&claims==2&&fake.sent==1&&ic.om_rbsdfs.retained_node==&ni);
if(mode==5)assert(!queued&&node_frees==1&&skb_frees==1&&ni.refs==0&&!skb.live&&claims==2&&!fake.sent);
if(mode==3||mode==4)assert(om_ieee80211_rbsdfs_stop(&ic)==-16&&om_ieee80211_rbsdfs_resume(&ic)==-16);
cases++;}
printf("{\"cases\":%u,\"actual_qdrv_send_body\":true,\"success_node_free_once\":true,\"provider_consumes_skb_only\":true,\"unknown_frame_node_retained\":true,\"claim_before_each_publication\":true}\n",cases);return 0;}
'''
 core=a.candidate/'source/wlan/openmitrastar_rbsdfs_recovered.c';inc=a.candidate/'source/wlan/openmitrastar_rbsdfs_kernel.inc';f=a.output/'actual-whole-qdrv-send.c';f.write_text(base.PRE+api+tail+core.read_text()+'\n'+inc.read_text()+'\n'+shim+'\n'+fn+'\n'+test);r=subprocess.run([str(a.compiler),'-O1','-std=c11','-I'+str(a.candidate/'headers/net80211'),str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,(r.returncode,r.stderr.decode());v=json.loads(r.stdout);pins={str(p):sha(p)for p in[header,source,core,inc,a.candidate/'headers/net80211/openmitrastar_rbsdfs_recovered.h',a.compiler,Path(__file__),Path(base.__file__),f,a.output/'fixture.exe']};(a.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n');result=dict(status='PASS_SOURCE_ONLY_RBSDFS_WHOLE_QDRV_SEND_FRAME_NODE_F355_FIXTURE',hardware_accessed=False,firmware_eligible=False,**v,limits='WholeactualQDRVsendwithactualcore/kernelbridge andfakenetqueue/provider/refcounts; nocallbackasynchardware/lifetimequalification');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':main()
