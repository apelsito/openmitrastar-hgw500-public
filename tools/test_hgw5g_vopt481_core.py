"""Exercise reconstructed481 against source-independent OEM state/call traces."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

FIXTURE = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "openmitrastar_vopt481_recovered.h"
struct call {unsigned kind,id;int value;};
static struct call calls[32];static unsigned ncalls;static int scs_error,bg_error;
static void put(unsigned kind,unsigned id,int value){assert(ncalls<32);calls[ncalls++]=(struct call){kind,id,value};}
static int parameter(void *ctx,unsigned id,int value){(void)ctx;put(0,id,value);return -7;}
static int scs(void *ctx,unsigned value){(void)ctx;put(1,0,value);return scs_error;}
static int ocac(void *ctx,unsigned value){(void)ctx;put(2,0,value);return -7;}
static int bgget(void *ctx,unsigned id,unsigned *value){(void)ctx;put(3,id,0);*value=777;return bg_error;}
static int bgset(void *ctx,unsigned id,unsigned value){(void)ctx;put(4,id,value);return -7;}
static void reassociate(void *ctx,unsigned a,unsigned b){(void)ctx;put(5,a,b);}
static const struct om_vopt_provider provider={0,parameter,scs,ocac,bgget,bgset,reassociate};
static unsigned cases;
static void equal(const struct call *expected,unsigned count){assert(ncalls==count);for(unsigned i=0;i<count;i++){assert(calls[i].kind==expected[i].kind);assert(calls[i].id==expected[i].id);assert(calls[i].value==expected[i].value);}}
static void reset(void){ncalls=0;scs_error=bg_error=0;memset(calls,0,sizeof(calls));}
int main(void){
struct om_vopt_state state,old;struct om_vopt_environment environment={0,0,36,0x81};int output;
const unsigned values[]={0,1,2,3,127,128,255,256,65535,65536,0x7fffffffU,0x80000000U,0xffffffffU};
for(unsigned mode=0;mode<16;mode++)for(unsigned i=0;i<sizeof(values)/sizeof(*values);i++){
 om_vopt_initialize(&state,1,1);old=state;int r=om_vopt_set(&state,mode,values[i]);
 if(mode==6&&values[i]<3){assert(r==0&&state.policy==values[i]);old.policy=values[i];}
 else assert(r==-95);assert(!memcmp(&state,&old,sizeof(state)));cases++;
}
for(unsigned mode=0;mode<16;mode++)for(unsigned policy=0;policy<256;policy++)for(unsigned effective=0;effective<256;effective++){
 om_vopt_initialize(&state,1,1);state.policy=policy;state.effective=effective;old=state;
 assert(!om_vopt_get(&state,mode,&output));assert(output==(mode==6?((policy&15)<<4)|effective:0));
 assert(!memcmp(&state,&old,sizeof(state)));cases++;
}
/* Exact full disable-consumer callback order from OEM .text+61164. */
reset();om_vopt_initialize(&state,1,1);state.effective=1;state.saved_txbf=255;
state.saved_probe=128;state.saved_scs=3;state.saved_ocac=1;state.saved_bgscan=777;
assert(!om_vopt_apply(&state,0,&environment,&provider));
const struct call restored[]={
{0,78,-1},{0,68,17},{0,158,1},{1,0,0x10003},{0,147,0x10003},
{2,0,0x10024},{4,0,1},{0,195,-128},{0,288,1},{0,482,-127},{0,414,0},{5,0,0}};
equal(restored,12);assert(state.effective==0&&state.live_pppc==1&&state.live_airfair==1&&state.live_duplicate_mu==0);cases++;
/* Exact enable-consumer sequence, including ignored callback errors. */
reset();assert(!om_vopt_apply(&state,1,&environment,&provider));
const struct call optimized[]={{0,68,16},{0,78,0},{0,158,0},{0,195,0},{0,288,0},
{1,0,0x10000},{0,147,0x10000},{2,0,0x20000},{3,0,0},{4,0,0},{0,482,0},{0,414,3},{5,0,0}};
equal(optimized,13);assert(state.effective==1&&state.saved_bgscan==777&&state.live_pppc==0&&state.live_airfair==0&&state.live_duplicate_mu==3);cases++;
for(unsigned flags=0;flags<4;flags++)for(unsigned error=0;error<2;error++)for(unsigned background=0;background<2;background++){
 reset();environment.flags=flags&1?0x40000000U:0;environment.flags_ext=flags&2?0x800000U:0;
 scs_error=error?-1:0;bg_error=background?-1:0;om_vopt_initialize(&state,1,1);state.saved_bgscan=21;
 assert(!om_vopt_apply(&state,1,&environment,&provider));unsigned pppc=0,forwarded=0,setbg=0;
 for(unsigned i=0;i<ncalls;i++){if(calls[i].kind==0&&calls[i].id==158)pppc++;if(calls[i].kind==0&&calls[i].id==147)forwarded++;if(calls[i].kind==4)setbg++;}
 assert(pppc==(flags==3?0:1)&&forwarded==!error&&setbg==!background);
 assert(state.saved_bgscan==(background?21:777));assert(state.live_pppc==0);cases++;
}
environment.flags=environment.flags_ext=0;
/* Exhaustive small peer populations and backoff transitions, pure ARC states. */
const unsigned cooldowns[]={0,1,2,10,0xffffffffU};
for(unsigned policy=0;policy<4;policy++)for(unsigned effective=0;effective<4;effective++)
for(unsigned total=0;total<=32;total++)for(unsigned qualified=0;qualified<=total;qualified++)
for(unsigned k=0;k<sizeof(cooldowns)/sizeof(*cooldowns);k++){
 reset();om_vopt_initialize(&state,1,1);state.policy=policy;state.effective=effective;
 unsigned counter=cooldowns[k],expected_counter=counter,expected_effective=effective,expected_apply=0;
 if(policy!=effective){
  if(policy<2){expected_effective=policy;expected_counter=0;expected_apply=1;}
  else if(policy==2){
   if(counter)expected_counter=counter-1;
   else if(total==qualified&&effective!=1){expected_effective=1;expected_apply=1;}
   else if(total!=qualified&&effective!=0){expected_effective=0;expected_counter=10;expected_apply=1;}
  }
 }
 assert(!om_vopt_tick(&state,&counter,total,qualified,&environment,&provider));
 assert(counter==expected_counter&&state.effective==expected_effective);
 assert((ncalls!=0)==expected_apply);cases++;
}
for(unsigned self=0;self<4;self++)for(unsigned flags=0;flags<4096;flags++){
 struct om_vopt_peer peer={self&1,(self>>1)&1,flags};unsigned total=5,qualified=7;
 om_vopt_count_peer(&peer,&total,&qualified);assert(total==(self?5:6));assert(qualified==(self?7:7+!!(flags&0x800)));cases++;
}
for(unsigned missing=0;missing<4;missing++){
 reset();om_vopt_initialize(&state,1,1);old=state;struct om_vopt_provider incomplete=provider;
 if(missing==0)incomplete.parameter=0;if(missing==1)incomplete.scs=0;if(missing==2)incomplete.ocac=0;if(missing==3)incomplete.reassociate=0;
 assert(om_vopt_apply(&state,1,&environment,&incomplete)==-95);assert(!memcmp(&old,&state,sizeof(state))&&!ncalls);cases++;
}
/* Multiple ticks must not invent repeated application or lose the ten-tick delay. */
reset();om_vopt_initialize(&state,1,1);state.policy=2;unsigned counter=0;
assert(!om_vopt_tick(&state,&counter,0,0,&environment,&provider)&&state.effective==1);cases++;
reset();assert(!om_vopt_tick(&state,&counter,1,0,&environment,&provider)&&state.effective==0&&counter==10);cases++;
for(unsigned i=0;i<10;i++){reset();assert(!om_vopt_tick(&state,&counter,1,1,&environment,&provider));assert(!ncalls&&state.effective==0&&counter==9-i);cases++;}
reset();assert(!om_vopt_tick(&state,&counter,1,1,&environment,&provider)&&state.effective==1);cases++;
printf("{\"cases\":%u,\"exact_callback_sequences\":2,\"setter_getter_state_preserved\":true,\"auto_backoff\":true}\n",cases);return 0;
}
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--candidate',type=Path,required=True)
    parser.add_argument('--compiler',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    assert not args.output.exists()
    inputs=[Path(__file__).resolve(),args.compiler.resolve(),
            *[p for p in args.candidate.iterdir()if p.is_file()]]
    pins={str(path):sha(path)for path in inputs}
    args.output.mkdir(parents=True)
    source=args.output/'fixture.c';source.write_text(FIXTURE,encoding='utf-8',newline='\n')
    command=[str(args.compiler),'-std=c11','-O2','-I'+str(args.candidate),str(source),
             str(args.candidate/'openmitrastar_vopt481_recovered.c'),'-o',str(args.output/'fixture.exe')]
    (args.output/'compile.command.json').write_text(json.dumps(command,indent=2)+'\n')
    run=subprocess.run(command,capture_output=True,timeout=60)
    (args.output/'compile.stderr').write_bytes(run.stderr)
    assert run.returncode==0,run.stderr.decode(errors='replace')
    run=subprocess.run([str(args.output/'fixture.exe')],capture_output=True,timeout=60)
    (args.output/'fixture.stdout').write_bytes(run.stdout)
    (args.output/'run.stderr').write_bytes(run.stderr)
    assert run.returncode==0,(run.returncode,run.stderr.decode(errors='replace'))
    observed=json.loads(run.stdout)
    for path,digest in pins.items():assert sha(path)==digest
    (args.output/'input-pins.json').write_text(json.dumps(pins,indent=2)+'\n')
    result={'status':'PASS_OEM481_RECOVERED_CORE_STATE_CALL_SEQUENCE_FIXTURE',
            'hardware_accessed':False,'firmware_eligible':False,**observed,
            'fixture_sha256':sha(source),'source_sha256':sha(args.candidate/'openmitrastar_vopt481_recovered.c'),
            'limits':'Reconstructed C core tested with fake providers; not kernel/Lifetime/SCS/OCAC/MuC behavior, ioctl registration or physical acceptance.'}
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
