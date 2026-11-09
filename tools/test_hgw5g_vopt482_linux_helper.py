"""Actual complete caller-owned Linux482 helper fixture; fake owned sender."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function
PRE=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include "openmitrastar_vopt482_state.h"
#define READ_ONCE(v) (v)
#define EXPORT_SYMBOL(v)
#define THIS_MODULE ((void*)1)
#define GFP_DMA 32
#define GFP_ATOMIC 128
#define IOCTL_DEV_CALCMD 19
#define IOCTL_DEV_SETPARAMS 11
#define QTN_HLINK_RC_DONE 1
#define QTN_HLINK_RC_ERR 2
#define container_of(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))
typedef unsigned dma_addr_t;
struct ieee80211vap{unsigned dummy;};
struct qdrv_mac{unsigned dead;};struct qdrv_wlan{struct qdrv_mac*mac;unsigned unit;};
struct qdrv_vap{struct ieee80211vap iv;struct qdrv_wlan*parent;unsigned devid;};
struct host_ioctl{unsigned ioctl_command,ioctl_arg1,ioctl_arg2,ioctl_argp;};
struct qtn_setparams_args{int ni_param,ni_value,ni_len;unsigned char ni_data[64];};
static unsigned irq,interrupt,pins,pin_allowed=1,sendcount,freecount,alloccount,ioalloccount,ioreleases,allocfail,iofail;static unsigned char mem[2][128];static struct host_ioctl ios[2];static int rcs[2];static unsigned pubs[2],retains[2];static int expectedvalue;
static unsigned in_interrupt(void){return interrupt;}
static unsigned irqs_disabled(void){return irq;}
static void save(unsigned long*f){*f=irq;irq=1;}
static void restore(unsigned long f){irq=f;}
#define local_irq_save(f) save(&(f))
#define local_irq_restore(f) restore(f)
static int try_module_get(void*m){assert(m==THIS_MODULE);if(!pin_allowed)return 0;pins++;return 1;}
static void module_put(void*m){assert(m==THIS_MODULE&&pins);pins--;}
static void*qdrv_hostlink_alloc_coherent(void*d,unsigned size,dma_addr_t*dma,unsigned flags){assert(!d&&alloccount<2);unsigned n=alloccount++;assert(size==(n?76:128)&&flags==(n?160:32));*dma=0x1000+0x100*n;memset(mem[n],0xcc,128);return allocfail==n+1?NULL:mem[n];}
static void qdrv_hostlink_free_coherent(void*d,unsigned size,void*p,dma_addr_t dma){assert(!d&&p==mem[dma==0x1000?0:1]&&size==(dma==0x1000?128:76));freecount++;}
static struct host_ioctl*qdrv_alloc_ioctl(struct qdrv_wlan*qw){(void)qw;unsigned n=ioalloccount++;assert(n<2);return iofail==n+1?NULL:&ios[n];}
static struct host_ioctl*vnet_alloc_ioctl(struct qdrv_vap*qv){(void)qv;return qdrv_alloc_ioctl(qv->parent);}
static void vnet_free_ioctl(struct host_ioctl*i){assert(i);ioreleases++;}
static int qdrv_send_ioctl_owned_observed(struct qdrv_wlan*qw,struct host_ioctl*i,bool retain,bool*r,bool*p){(void)qw;assert(retain&&sendcount<2);unsigned n=sendcount++;if(i->ioctl_command==19){assert(i->ioctl_arg2==6&&!i->ioctl_arg1&&i->ioctl_argp==0x1000);unsigned low=(unsigned)expectedvalue&255;assert(mem[0][0]==19&&!mem[0][1]&&mem[0][2]==6&&!mem[0][3]&&mem[0][4]==1&&mem[0][5]==(low?(low*4U)&255:44));}else{assert(i->ioctl_command==11&&i->ioctl_arg1==3&&i->ioctl_argp>=0x1000);struct qtn_setparams_args*a=(void*)mem[i->ioctl_argp==0x1000?0:1];assert(a->ni_param==482&&a->ni_value==expectedvalue&&!a->ni_len);}*r=retains[n];*p=pubs[n];return rcs[n];}
'''
TEST=r'''
static struct qdrv_mac mac;static struct qdrv_wlan qw;static struct qdrv_vap qv;static struct om_vopt482_state s;
static void clear(void){memset(&s,0,sizeof(s));memset(ios,0,sizeof(ios));mac.dead=0;qw.mac=&mac;qw.unit=0;qv.parent=&qw;qv.devid=3;irq=interrupt=pins=sendcount=freecount=alloccount=ioalloccount=ioreleases=allocfail=iofail=0;pin_allowed=1;rcs[0]=rcs[1]=1;pubs[0]=pubs[1]=1;retains[0]=retains[1]=0;}
int main(void){unsigned cases=0;
for(unsigned v=0;v<256;v++){clear();expectedvalue=v;assert(!om_qdrv_vopt482(&qv.iv,&s,v)&&!pins&&!s.processing&&!s.payload&&!s.quarantined&&freecount==2&&sendcount==2&&!om_qdrv_vopt482_pending(&s));cases++;}
for(unsigned stage=0;stage<2;stage++)for(int rc=-1;rc<4;rc++)for(unsigned published=0;published<2;published++)for(unsigned retained=0;retained<2;retained++){clear();expectedvalue=(int)0x8000ffffU;rcs[stage]=rc;pubs[stage]=published;retains[stage]=retained;int r=om_qdrv_vopt482(&qv.iv,&s,expectedvalue);if(retained){assert(r==-EINPROGRESS&&pins==1&&s.processing&&s.quarantined&&s.payload&&s.pending_ioctl&&s.bytes==(stage?76:128)&&freecount==stage&&sendcount==stage+1&&om_qdrv_vopt482_pending(&s));unsigned n=sendcount;assert(om_qdrv_vopt482(&qv.iv,&s,1)==-EBUSY&&sendcount==n);}else assert(r==(rc>=0&&(rc&1)&&!(rc&2)&&published?0:-EIO)&&!pins&&!s.processing&&!s.payload&&freecount==2&&sendcount==2);cases++;}
clear();expectedvalue=1;allocfail=1;assert(om_qdrv_vopt482(&qv.iv,&s,1)==-EIO&&!pins&&!s.processing);cases++;
clear();expectedvalue=1;allocfail=2;assert(om_qdrv_vopt482(&qv.iv,&s,1)==-EIO&&!pins&&freecount==1&&ioreleases==1);cases++;
clear();interrupt=1;assert(om_qdrv_vopt482(&qv.iv,&s,1)==-EWOULDBLOCK&&!pins&&!alloccount);cases++;
clear();mac.dead=1;assert(om_qdrv_vopt482(&qv.iv,&s,1)==-ENODEV&&!pins&&!alloccount);cases++;
clear();pin_allowed=0;assert(om_qdrv_vopt482(&qv.iv,&s,1)==-ENODEV&&!pins&&!alloccount);cases++;
printf("{\"cases\":%u,\"actual_complete_linux_helper\":true,\"caller_owned_payload_ioctl_quarantine\":true,\"no_forward_after_unknown_calcmd\":true,\"dead_raw1_not_ack\":true}\n",cases);return 0;}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();fsource=a.candidate/'source/qdrv/qdrv_hostlink.c';text=fsource.read_text();body='int '+function(text,'om_qdrv_vopt482_pending(const struct om_vopt482_state *s)')+'\nstatic int '+function(text,'om482_send_owned(struct qdrv_wlan *qw')+'\nint '+function(text,'om_qdrv_vopt482(struct ieee80211vap *vap');header=a.candidate/'headers/net80211/openmitrastar_vopt482_state.h';pins={str(x.resolve()):hashlib.sha256(x.read_bytes()).hexdigest()for x in [Path(__file__),a.compiler,fsource,header]};a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-linux-482-helper.c';f.write_text(PRE+body+TEST);r=subprocess.run([str(a.compiler),'-std=c11','-O1','-I'+str(header.parent),str(f),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();obs=json.loads(r.stdout)
 for path,h in pins.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
 result=dict(status='PASS_ACTUAL_CALLER_OWNED_LINUX482_HELPER_FAKE_SENDER_FIXTURE',hardware_accessed=False,firmware_eligible=False,**obs,input_pins=pins,fixture_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),limits='Actualhelperbody butexistinghostlinksender fake; noICquiesce/providerlifetime/foreignproducerbank/MuCreceiver orphysicalacceptance.');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
