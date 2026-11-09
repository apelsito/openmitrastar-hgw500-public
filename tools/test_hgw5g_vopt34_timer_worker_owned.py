"""Actual ic_inact→VOPT worker→Linux482 helper→F355 core source fixture."""
import argparse,hashlib,json,re,subprocess
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function
from test_hgw5g_vopt34_linux_worker import PRE as WORKPRE
EXTRA=r'''
#define THIS_MODULE ((void*)1)
#define GFP_DMA 32
#define GFP_ATOMIC 128
#define IOCTL_DEV_CALCMD 19
#define IOCTL_DEV_SETPARAMS 11
#define QTN_HLINK_RC_DONE 1
#define QTN_HLINK_RC_ERR 2
typedef unsigned dma_addr_t;
struct qdrv_mac{unsigned dead;};struct qdrv_wlan{struct qdrv_mac*mac;unsigned unit;};
struct qdrv_vap{struct ieee80211vap iv;struct qdrv_wlan*parent;unsigned devid;};
struct host_ioctl{unsigned ioctl_command,ioctl_arg1,ioctl_arg2,ioctl_argp;};
struct qtn_setparams_args{int ni_param,ni_value,ni_len;unsigned char ni_data[64];};
static unsigned irq_local,module_pins,allocations,frees,sends,ioalloc,retained_stage;static unsigned char payloads[2][128];static struct host_ioctl ioctls[2];static struct f355_lifetime f355;
static void irqsave(unsigned long*f){*f=irq_local;irq_local=1;}
static void irqrestore(unsigned long f){irq_local=f;}
#define local_irq_save(f) irqsave(&(f))
#define local_irq_restore(f) irqrestore(f)
static int try_module_get(void*p){assert(p==THIS_MODULE);module_pins++;return 1;}
static void module_put(void*p){assert(p==THIS_MODULE&&module_pins);module_pins--;}
static bool reference(void*p){(void)p;return try_module_get(THIS_MODULE);}
static int qdrv_f355_claim(const char*n){assert(!strcmp(n,"vopt482"));return f355_claim(&f355,reference,NULL);}
static void*qdrv_hostlink_alloc_coherent(void*d,unsigned size,dma_addr_t*dma,unsigned flags){assert(!d&&allocations<2);unsigned n=allocations++;assert(size==(n?76:128)&&flags==(n?160:32));*dma=0x1000+0x100*n;return payloads[n];}
static void qdrv_hostlink_free_coherent(void*d,unsigned size,void*p,dma_addr_t dma){assert(!d&&size==(dma==0x1000?128:76)&&p==payloads[dma==0x1000?0:1]);frees++;}
static struct host_ioctl*qdrv_alloc_ioctl(struct qdrv_wlan*w){(void)w;assert(ioalloc<2);return&ioctls[ioalloc++];}
static struct host_ioctl*vnet_alloc_ioctl(struct qdrv_vap*v){return qdrv_alloc_ioctl(v->parent);}
static void vnet_free_ioctl(struct host_ioctl*i){(void)i;}
static int qdrv_send_ioctl_owned_observed(struct qdrv_wlan*w,struct host_ioctl*i,bool retain,bool*r,bool*p){(void)w;assert(retain);unsigned n=sends++;assert(n<2);assert(i->ioctl_command==(n?11:19));if(!n)assert(i->ioctl_arg2==6&&payloads[0][0]==19&&payloads[0][5]==44);else{struct qtn_setparams_args*a=(void*)payloads[1];assert(a->ni_param==482&&!a->ni_value&&!a->ni_len);}*p=true;*r=retained_stage==n+1;return*r?-1:1;}
#define from_timer(v,t,m) ((struct ieee80211com*)((char*)(t)-offsetof(struct ieee80211com,m)))
static void ieee80211_timeout_stations(struct node_table*t){(void)t;}
static void ieee80211_timeout_ap(struct ieee80211com*ic){(void)ic;}
'''
TEST=r'''
int main(void){unsigned cases=0;for(unsigned unknown=0;unknown<3;unknown++){struct ieee80211com ic={0};struct qdrv_vap qv={0};struct qdrv_mac mac={0};struct qdrv_wlan qw={&mac,0};struct ieee80211_node bss={0},peer={0};struct net_device dev={0};struct ieee80211_channel chan={0};f355=(struct f355_lifetime){.ready=true};module_pins=allocations=frees=sends=ioalloc=0;retained_stage=unknown;scheduled=reassocs=locks=rtlock=0;memset(params,0,sizeof(params));qv.parent=&qw;qv.devid=3;qv.iv.iv_ic=&ic;qv.iv.iv_opmode=6;qv.iv.iv_bss=&bss;qv.iv.iv_dev=&dev;bss.ni_vap=peer.ni_vap=&qv.iv;peer.ni_macaddr[0]=1;peer.ni_qtn_flags=0x800;ic.ic_vaps=&qv.iv;ic.ic_setparam=(void*)1;ic.ic_iterate_nodes=iterator;ic.ic_sta.nodes[0]=&bss;ic.ic_sta.nodes[1]=&peer;ic.ic_sta.count=2;ic.ic_curchan=&chan;om_ieee80211_vopt_initialize(&ic);ic.om_vopt.policy=1;om_vopt_global_backoff=0;
ieee80211_node_timeout(&ic.ic_inact);assert(scheduled==1&&!sends&&ic.om_vopt_pending&&ic.ic_inact.pending);ic.om_vopt_work.queued=0;current=&ic.om_vopt_work;ic.om_vopt_work.fn(&ic.om_vopt_work);current=NULL;assert(f355.retained&&f355_exit_begin(&f355)==F355_BUSY);if(unknown){assert(ic.om_vopt_stopping&&ic.om_vopt482.quarantined&&ic.om_vopt482.payload&&module_pins==2&&!params[414]&&!reassocs&&sends==unknown&&frees==unknown-1);assert(om_ieee80211_vopt_detach_begin(&ic)==-EINPROGRESS);assert(ic.om_vopt_destroying&&!ic.ic_inact.pending);}else assert(module_pins==1&&frees==2&&sends==2&&params[414]==1&&reassocs==1&&!ic.om_vopt482.quarantined);assert(!locks&&!rtlock);cases++;}
printf("{\"cases\":%u,\"whole_actual_timer_worker_ownedhelper\":true,\"F355_retains_outer_lifetime\":true,\"unknown_bothstages_no414_reassoc\":true}\n",cases);return 0;}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();q=a.candidate/'source/qdrv';w=a.candidate/'source/wlan';node=w/'ieee80211_node.c';host=q/'qdrv_hostlink.c';pre=re.sub(r'int om_qdrv_vopt482_pending\([^\n]+\n','',WORKPRE);pre=re.sub(r'int om_qdrv_vopt482\([^\n]+\n','',pre);parts=[q/'f355_lifetime.h',w/'openmitrastar_vopt481_kernel_core.inc',w/'openmitrastar_vopt481_kernel.inc'];h=host.read_text();helper='int '+function(h,'om_qdrv_vopt482_pending(const struct om_vopt482_state *s)')+'\nstatic int '+function(h,'om482_send_owned(struct qdrv_wlan *qw')+'\nint '+function(h,'om_qdrv_vopt482(struct ieee80211vap *vap');timer='static void '+function(node.read_text(),'ieee80211_node_timeout(struct timer_list *timer)');pins={str(x.resolve()):hashlib.sha256(x.read_bytes()).hexdigest()for x in [Path(__file__),Path(__file__).with_name('test_hgw5g_vopt34_linux_worker.py'),a.compiler,node,host,*parts]};a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-timer-worker-owned.c';f.write_text(pre+parts[0].read_text()+EXTRA+helper+parts[1].read_text()+parts[2].read_text()+timer+TEST);r=subprocess.run([str(a.compiler),'-std=c11','-O1','-I'+str(w),'-I'+str(a.candidate/'headers/net80211'),str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();obs=json.loads(r.stdout)
 for path,h in pins.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
 result=dict(status='PASS_WHOLE_ACTUAL_IC_TIMER_WORKER_482_HELPER_F355_CORE_SOURCE_FIXTURE',hardware_accessed=False,firmware_eligible=False,**obs,input_pins=pins,fixture_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),limits='Actual complete timer/worker/helper plusF355purecore; fakeshostlinkphysicalpublication/RTNL/scheduler. No fullmodule/lifecycleoperational/RFclaim.');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
