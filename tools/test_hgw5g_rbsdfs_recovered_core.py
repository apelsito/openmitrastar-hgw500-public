"""Compile actual isolated OEM466/468 core and exact-frame adapter callbacks."""
import argparse,hashlib,json,subprocess
from pathlib import Path
TEST=r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "openmitrastar_rbsdfs_recovered.h"
struct fake {unsigned enables,disables,arms,statusreads,grant,send,revoke,validate;unsigned status1,status2,equal;omrbs_u32 channel,expires;int grantresult,sendresult,revokeresult,validresult;};
static struct fake f;static const void*expected=(void*)0x1234;
static void enable(void*c){((struct fake*)c)->enables++;}
static void disable(void*c){((struct fake*)c)->disables++;}
static void arm(void*c,omrbs_u32 chan,omrbs_u32 expiry){struct fake*p=c;p->arms++;p->channel=chan;p->expires=expiry;}
static void*find(void*c,omrbs_u32 chan){((struct fake*)c)->channel=chan;return(void*)0x2468;}
static int equal(void*c,void*ch){assert(ch==(void*)0x2468);return((struct fake*)c)->equal;}
static unsigned status(void*c){struct fake*p=c;return p->statusreads++?p->status2:p->status1;}
static int validate(void*c,const void*p,unsigned role,omrbs_u32 ch){struct fake*x=c;assert(p==expected&&(role==1||role==2)&&ch==52);x->validate++;return x->validresult;}
static int grant(void*c,const void*p){assert(p==expected);((struct fake*)c)->grant++;return((struct fake*)c)->grantresult;}
static int send(void*c,const void*p){assert(p==expected);((struct fake*)c)->send++;return((struct fake*)c)->sendresult;}
static int revoke(void*c,const void*p){assert(p==expected);((struct fake*)c)->revoke++;return((struct fake*)c)->revokeresult;}
int main(void){unsigned cases=0;struct om_rbsdfs_state s,old;omrbs_u32 v;const omrbs_u32 boundary[]={0,1,2,255,256,500,999,1000,1001,0x7fffffff,0x80000000,0xffffffff};struct om_rbsdfs_oem_hooks h={&f,enable,disable,arm,find,equal,status};
om_rbsdfs_init(&s);assert(s.end_tx_ms==500&&!s.measurement_in_cac&&!s.allow_rbs_report&&!s.allow_mbs_csa);cases++;
for(unsigned i=0;i<sizeof(boundary)/sizeof(*boundary);i++){om_rbsdfs_init(&s);assert(!om_rbsdfs_set466(&s,boundary[i]));v=4;assert(!om_rbsdfs_get466(&s,&v)&&v==!!boundary[i]);old=s;int r=om_rbsdfs_set468(&s,boundary[i]);if(boundary[i]>=1&&boundary[i]<=1000){assert(!r&&!om_rbsdfs_get468(&s,&v)&&v==boundary[i]);}else assert(r==-22&&!memcmp(&s,&old,sizeof(s)));cases++;}
for(unsigned ms=1;ms<=1000;ms++){memset(&f,0,sizeof(f));om_rbsdfs_init(&s);s.measurement_in_cac=1;assert(!om_rbsdfs_set468(&s,ms));assert(om_rbsdfs_oem_radar_window(&s,2,1,52,0xfffffff0U,200,&h)==1&&s.allow_rbs_report&&f.enables==1&&f.arms==1&&f.channel==52&&f.expires==(omrbs_u32)(0xfffffff0U+ms*200/1000));cases++;}
for(unsigned role=0;role<4;role++)for(unsigned cac=0;cac<2;cac++)for(unsigned enabled=0;enabled<2;enabled++){memset(&f,0,sizeof(f));om_rbsdfs_init(&s);s.measurement_in_cac=enabled;int r=om_rbsdfs_oem_radar_window(&s,role,cac,52,100,200,&h);assert(r==(role==2&&cac&&enabled)&&f.enables==(unsigned)r&&f.arms==(unsigned)r&&s.allow_rbs_report==(unsigned)r);cases++;}
for(unsigned wr=0;wr<2;wr++)for(unsigned vap=0;vap<2;vap++)for(unsigned cac=0;cac<2;cac++){memset(&f,0,sizeof(f));om_rbsdfs_init(&s);s.measurement_in_cac=1;int r=om_rbsdfs_oem_mbs_window(&s,wr,vap,cac,&h);assert(r==(!wr&&vap&&cac)&&f.enables==(unsigned)r&&s.allow_mbs_csa==(unsigned)r);cases++;}
for(unsigned role=0;role<4;role++)for(unsigned ena=0;ena<2;ena++)for(unsigned allowance=0;allowance<2;allowance++)for(unsigned a=0;a<10;a++)for(unsigned b=0;b<10;b++){memset(&f,0,sizeof(f));f.status1=a;f.status2=b;om_rbsdfs_init(&s);s.measurement_in_cac=ena;s.allow_rbs_report=s.allow_mbs_csa=allowance;int r=om_rbsdfs_oem_send_permitted(&s,role,&h);unsigned checked=ena&&(role==1||role==2)&&!allowance;assert(r==(checked?(a!=4&&b!=8):1));assert(f.statusreads==(checked?(a==4?1:2):0));if(ena&&(role==1||role==2)&&allowance)assert((role==2?s.allow_rbs_report:s.allow_mbs_csa)==0);cases++;}
for(unsigned eq=0;eq<2;eq++){memset(&f,0,sizeof(f));f.equal=eq;assert(om_rbsdfs_oem_expire(52,&h)==(int)eq&&f.disables==eq&&f.channel==52);cases++;}
/* No callbacks means zero publication, original state intact. */
memset(&f,0,sizeof(f));om_rbsdfs_init(&s);s.measurement_in_cac=1;old=s;struct om_rbsdfs_oem_hooks absent=h;absent.enable_tx=NULL;assert(om_rbsdfs_oem_radar_window(&s,2,1,52,0,200,&absent)==-22&&!memcmp(&s,&old,sizeof(s))&&!f.enables&&!f.arms);cases++;
struct om_rbsdfs_frame_hooks fh={&f,validate,grant,send,revoke};
for(int gr=-1;gr<=2;gr++)for(int se=-1;se<=2;se++)for(int re=-1;re<=2;re++){struct om_rbsdfs_frame_state state={0};memset(&f,0,sizeof(f));f.validresult=1;f.grantresult=gr;f.sendresult=se;f.revokeresult=re;enum om_rbsdfs_frame_result r=om_rbsdfs_exact_frame_window(&state,expected,2,52,200,&fh);assert(f.validate==1&&f.grant==1);if(gr==0)assert(r==OMRBS_REFUSED&&!state.active&&!state.frame&&!f.send&&!f.revoke);else if(gr!=1)assert(r==OMRBS_PUBLISHED_UNKNOWN&&state.active&&state.quarantined&&state.frame==expected&&!f.send&&!f.revoke);else{assert(f.send==1&&f.revoke==1);if(se!=0&&se!=1)assert(r==OMRBS_PUBLISHED_UNKNOWN&&state.quarantined);else if(re!=1)assert(r==OMRBS_PUBLISHED_UNKNOWN&&state.quarantined);else assert(r==(se==1?OMRBS_COMPLETE:OMRBS_REFUSED)&&!state.active&&!state.frame&&!state.quarantined);}if(state.quarantined){unsigned n=f.grant;assert(om_rbsdfs_exact_frame_window(&state,expected,2,52,200,&fh)==OMRBS_REFUSED&&f.grant==n);}cases++;}
{struct om_rbsdfs_frame_state state={0};memset(&f,0,sizeof(f));struct om_rbsdfs_frame_hooks absent=fh;absent.grant_frame=NULL;assert(om_rbsdfs_exact_frame_window(&state,expected,2,52,200,&absent)==OMRBS_REFUSED&&!state.generation&&!f.validate&&!f.grant);cases++;}
printf("{\"cases\":%u,\"all_delay_values_1_1000\":true,\"oem_boolean_range_defaults\":true,\"role_one_shot_status_gate\":true,\"expiry_never_marks_cac_radar\":true,\"frame_unknown_retained_no_retry\":true}\n",cases);return 0;}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--candidate',type=Path,required=True);p.add_argument('--compiler',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();pins={str(x.resolve()):hashlib.sha256(x.read_bytes()).hexdigest()for x in (Path(__file__),a.compiler,a.candidate/'openmitrastar_rbsdfs_recovered.c',a.candidate/'openmitrastar_rbsdfs_recovered.h')};a.output.mkdir(parents=True,exist_ok=False);f=a.output/'actual-rbsdfs-core.c';f.write_text(TEST);r=subprocess.run([str(a.compiler),'-std=c11','-O1','-I'+str(a.candidate),str(f),str(a.candidate/'openmitrastar_rbsdfs_recovered.c'),'-o',str(a.output/'fixture.exe')],capture_output=True);(a.output/'compile.stderr').write_bytes(r.stderr);assert not r.returncode,r.stderr.decode();r=subprocess.run([str(a.output/'fixture.exe')],capture_output=True);assert not r.returncode,r.stderr.decode();obs=json.loads(r.stdout)
 for path,h in pins.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==h
 result=dict(status='PASS_SOURCE_ONLY_OEM_RBSDFS_CORE_CALLBACK_FIXTURE',hardware_accessed=False,firmware_eligible=False,**obs,input_pins=pins,fixture_sha256=hashlib.sha256(f.read_bytes()).hexdigest(),limits='Actual isolated reconstructed core functions and fake callback/frame provider; no Linux lifetime/module/livegrant/regulatory/client proof. No runtimeprovider bound; qualifiedfunctionalopsadded0.');(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
