"""Actual482 serialize/ownedtransaction plus Linux CALCMD fragment fake sender."""
import argparse,hashlib,json,subprocess
from pathlib import Path
TEST=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include "openmitrastar_vopt482_transport.h"
static unsigned counts[4],steps[8],nsteps,allocation_failure;static om482_u8 payload[128];static om482_u32 expected_value;static struct om482_outcome calresult,normalresult;
static void*alloc(void*c,unsigned b,om482_u32*d,unsigned f){(void)c;assert(b==128&&f==32);counts[0]++;steps[nsteps++]=0;*d=0x1234;if(allocation_failure)return NULL;memset(payload,0xcc,128);return payload;}
static void release(void*c,unsigned b,void*p,om482_u32 d){(void)c;assert(b==128&&p==payload&&d==0x1234);counts[1]++;steps[nsteps++]=1;}
static struct om482_outcome calcmd(void*c,unsigned n,om482_u32 dma){(void)c;assert(n==6&&dma==0x1234);om482_u8 low=(om482_u8)expected_value;assert(payload[0]==19&&!payload[1]&&payload[2]==6&&!payload[3]&&payload[4]==1&&payload[5]==(low?(low*4U)&255:44));for(unsigned i=6;i<128;i++)assert(payload[i]==0xcc);counts[2]++;steps[nsteps++]=2;return calresult;}
static struct om482_outcome normal(void*c,unsigned command,om482_u32 value){(void)c;assert(command==482&&value==expected_value);counts[3]++;steps[nsteps++]=3;return normalresult;}
static struct om482_provider provider={NULL,alloc,release,calcmd,normal};
static void clear(void){memset(counts,0,sizeof(counts));nsteps=allocation_failure=0;calresult=(struct om482_outcome){OM482_TERMINAL,1};normalresult=calresult;}
/* Actual Linux fragment types/realAPI contract fakes. */
typedef om482_u32 u32;
#define READ_ONCE(v) (v)
#define IOCTL_DEV_CALCMD 19
#define QTN_HLINK_RC_DONE 1
#define QTN_HLINK_RC_ERR 2
struct qdrv_mac{unsigned dead;};struct qdrv_wlan{struct qdrv_mac*mac;};
struct host_ioctl{unsigned ioctl_command,ioctl_arg1,ioctl_arg2,ioctl_argp;};
static struct host_ioctl ioctl;static unsigned ioalloc_failure,sender_retained,sender_calls;static int sender_rc;
static struct host_ioctl*qdrv_alloc_ioctl(struct qdrv_wlan*qw){(void)qw;return ioalloc_failure?NULL:&ioctl;}
static int qdrv_send_ioctl_owned(struct qdrv_wlan*qw,struct host_ioctl*i,bool retain,bool*r){(void)qw;assert(i==&ioctl&&retain&&i->ioctl_command==19&&!i->ioctl_arg1&&i->ioctl_arg2==6&&i->ioctl_argp==0x1234);sender_calls++;*r=sender_retained;return sender_rc;}
'''
BODY=r'''
int main(void){unsigned cases=0;struct om482_transaction s;om482_u8 actual[6];const om482_u32 bounds[]={0,1,2,11,63,64,127,128,255,256,0x7fffffffU,0x80000000U,0xffffffffU};
for(unsigned v=0;v<256;v++){clear();memset(&s,0,sizeof(s));expected_value=v;om482_payload(v,actual);assert(actual[0]==19&&!actual[1]&&actual[2]==6&&!actual[3]&&actual[4]==1&&actual[5]==(v?(v*4U)&255:44));assert(om482_execute(&s,v,&provider)==OM482_ACKNOWLEDGED);assert(counts[0]==1&&counts[1]==1&&counts[2]==1&&counts[3]==1&&!s.active&&!s.payload&&!s.quarantined&&s.generation==1&&steps[0]==0&&steps[1]==2&&steps[2]==1&&steps[3]==3);cases++;}
for(unsigned bi=0;bi<sizeof(bounds)/sizeof(*bounds);bi++)for(unsigned allocfail=0;allocfail<2;allocfail++)for(unsigned pub=0;pub<4;pub++)for(unsigned rc=0;rc<8;rc++)for(unsigned normalpub=0;normalpub<4;normalpub++){
 clear();memset(&s,0,sizeof(s));expected_value=bounds[bi];allocation_failure=allocfail;calresult=(struct om482_outcome){pub,rc};normalresult=(struct om482_outcome){normalpub,rc};enum om482_result r=om482_execute(&s,expected_value,&provider);assert(counts[0]==1);if(!allocfail&&pub>=2){assert(r==OM482_PUBLISHED_UNKNOWN&&s.active&&s.quarantined&&s.payload==payload&&!counts[1]&&!counts[3]);}else{assert(counts[3]==1&&counts[1]==!allocfail);if(normalpub>=2)assert(r==OM482_PUBLISHED_UNKNOWN&&s.active&&s.quarantined&&!s.payload);else{int ack=!allocfail&&pub==1&&normalpub==1&&(rc&1)&&!(rc&2);assert(r==(ack?OM482_ACKNOWLEDGED:OM482_COMPLETED_ERROR)&&!s.active&&!s.quarantined&&!s.payload);}}if(s.quarantined){unsigned n=counts[0];assert(om482_execute(&s,expected_value,&provider)==OM482_REFUSED&&counts[0]==n);}cases++;
}
/* Providerabsence means no allocation, mutation or callback. */
for(unsigned missing=0;missing<4;missing++){clear();memset(&s,0,sizeof(s));struct om482_provider p=provider;if(missing==0)p.allocate=NULL;if(missing==1)p.release=NULL;if(missing==2)p.calcmd_owned=NULL;if(missing==3)p.parameter_owned=NULL;assert(om482_execute(&s,1,&p)==OM482_REFUSED&&!s.generation&&!counts[0]);cases++;}
/* Actual new Linux fragment parses retained independently of numericalrc. */
for(unsigned dead=0;dead<2;dead++)for(unsigned fail=0;fail<2;fail++)for(unsigned retained=0;retained<2;retained++)for(int rc=-1;rc<8;rc++){struct qdrv_mac mac={dead};struct qdrv_wlan qw={&mac};sender_rc=rc;sender_retained=retained;sender_calls=0;ioalloc_failure=fail;struct om482_outcome o=om482_linux_calcmd_owned(&qw,6,0x1234);if(dead||fail)assert(o.publication==OM482_UNPUBLISHED&&!sender_calls);else if(retained)assert(o.publication==OM482_UNKNOWN&&sender_calls==1);else assert(o.publication==((rc>=0&&(rc&3))?OM482_TERMINAL:OM482_UNPUBLISHED)&&sender_calls==1);cases++;}
printf("{\"cases\":%u,\"payload_all256bytes\":true,\"u32value_preserved_normal482\":true,\"allocation128_GFP32\":true,\"ack_error_unpublished_unknown_distinct\":true,\"unknown_payload_retained_no_forward_or_retry\":true,\"linux_fragment_dead_rc1_refused\":true}\n",cases);return 0;}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();files=[a.candidate/x for x in('openmitrastar_vopt482_transport.h','openmitrastar_vopt482_transport.c','linux-calcmd-owned-fragment.c.inc')];pins={str(x.resolve()):hashlib.sha256(x.read_bytes()).hexdigest()for x in [Path(__file__),a.compiler,*files]};a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-482-transport-fixture.c';f.write_text(TEST+files[-1].read_text()+BODY);r=subprocess.run([str(a.compiler),'-std=c11','-O1','-I'+str(a.candidate),str(f),str(files[1]),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);(a.output/'run.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();obs=json.loads(r.stdout)
 for path,h in pins.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
 result=dict(status='PASS_ACTUAL482_PAYLOAD_AND_OWNED_TRANSPORT_SOURCE_FIXTURE',hardware_accessed=False,firmware_eligible=False,**obs,input_pins=pins,fixture_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),limits='Actualnewsourcefunctions+Linuxfragment withfakeallocation/senderpublication; existinghostlinksenderloops notexecuted. No registeredprovider/modulelifetime/MuCreceiver/radioacceptance.');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
