"""Execute actual F325/F332 clear/setup C with fake MMIO; never access hardware."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,subprocess
from f331_oem_postfilter_projection import linux
from test_f329_watchdog import function
ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'work/kernel-port/modules/f332_dfs_provider/provider'
OLD=ROOT/'work/kernel-port/modules/f325_radar_once/qtn_radar_shadow_f315_main.c'
SEALED=ROOT/'outputs/kernel-port/f325-radar-once-20260919T000320492832Z/source/qtn_radar_shadow_f315_main.c'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 if OLD.read_bytes()!=SEALED.read_bytes():raise ValueError('F325 source differs from sealed build snapshot')
 setup=(P/'f332_setup.inc').read_text();backend=(P/'f332_hardware.c').read_text();old=OLD.read_text()
 out=ROOT/('outputs/preflight/f332-startup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(parents=True)
 enum=setup[setup.index('enum f315_window_id'):setup.index('struct f315_mmio_window')]
 # Resolve the existing address declarations, rather than maintain a second map.
 header=(ROOT/'work/sources/Quantenna-GPL/drivers/radar/radar.h').read_text()
 defines=dict(re.findall(r'^#define\s+(\w+)\s+([^\r\n]+)',header,re.M));cache={}
 def value(name):
  if name in cache:return cache[name]
  expression=defines[name].split('/*')[0].split('//')[0].strip()
  expression=re.sub(r'\b[A-Z][A-Z0-9_]+\b',lambda m:str(value(m[0])),expression)
  if not re.fullmatch(r'[0-9a-fxA-FX()+\s]+',expression):raise ValueError(expression)
  cache[name]=eval(expression,{'__builtins__':{}},{});return cache[name]
 rows=re.findall(r'\[(F315_REG_\w+)\]\s*=\s*F315_REG_ENTRY\(\s*F315_WINDOW_\w+,\s*(QT4_\w+)',setup)
 required=set(re.findall(r'\bF315_REG_[A-Z0-9_]+\b',enum))-{'F315_REG_COUNT'}
 if {name for name,_ in rows}!=required:raise ValueError('incomplete actual register map')
 addresses='static const u32 reg_address[F315_REG_COUNT]={'+','.join('['+reg+']='+hex(value(sym)) for reg,sym in rows)+'};\n'
 prelude=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <errno.h>
#include <stdio.h>
typedef uint32_t u32;
#define __iomem
#define QTN_LHOST_SOC_CPU 1
#define F315_CAPTURE_SIZE 0x1800U
#define F315_ZC_VALID_BYTES 0x0e00U
#define TIMER_REC_EN_ADDR_MASK 0x80000000U
#define TH1_DEFAULT 0x34000U
#define TH2_DEFAULT 0x8000U
#define CLEAR_INT_STATUS_REG_RADAR_VAL 2U
#define atomic64_inc(p) (++*(p))
static bool shadow_enable=true,f315_configured,iir_programmed,zc_accurate;
static bool first_capture_trace,pm_begin_logged,pm_acquired_logged,pm_release_logged;
static unsigned phase_lines;
static void fake_info(const char*format,const char*name){(void)format;(void)name;}
#define pr_info fake_info
static u32 target_gain,zc_cursor,epoch_base;
static struct{u32 win_size,win_per_pulse,hw_width_min,hw_width_max;bool tag_enabled;}f315_profile={120,28,4,360,false};
static unsigned f315_mmio_writes,f315_mmio_write_refusals;
static unsigned char memory[0x1800];
static struct{void*base;}f315_windows[4];
struct event{unsigned kind;u32 address,value;};
static struct event trace[3000];static unsigned used,depth,clock_calls;static u32 chip=0x50,scan=1;
static void record(unsigned kind,u32 address,u32 val){assert(used<3000);trace[used++]=(struct event){kind,address,val};}
static void writel(u32 val,void*p){uintptr_t offset=(unsigned char*)p-memory;assert(offset<sizeof(memory));assert(depth==1);record(4,0xe6400000U+(u32)offset,val);}
static u32 readl(void*p){assert(p==&chip);assert(depth==1);record(8,0xe0000014,chip);return chip;}
static void *ioremap(u32 address,unsigned size){assert(address==0xe0000014&&size==4);record(6,address,size);return &chip;}
static void iounmap(void*p){assert(p==&chip);record(7,0,0);}
static unsigned get_bootcfg_scancnt(void){assert(depth==1);record(9,0,scan);return scan;}
static void qtn_bb_mutex_enter(unsigned cpu){assert(cpu==1&&!depth);depth=1;record(1,0,0);}
static void qtn_bb_mutex_leave(unsigned cpu){assert(cpu==1&&depth==1);depth=0;record(2,0,0);}
static void wmb(void){}
static int clock_now(int32_t*s,int32_t*u){assert(!depth);clock_calls++;*s=1;*u=(int32_t)clock_calls;record(5,1,clock_calls);return 0;}
'''
 stubs=r'''
static int f315_write_reg(enum f315_register_id id,u32 v){assert(depth==1);assert(id<F315_REG_COUNT);record(3,reg_address[id],v);return 0;}
static u32 f315_read_reg(enum f315_register_id id){assert(depth==1);assert(id==F315_REG_TIMER_REC_EN);return 0x1234;}
'''
 code=prelude+enum+addresses+stubs+function(backend,'phase')+'\n'
 code+=function(setup,'f315_clear_capture_word')+'\n'
 code+=function(old,'f315_clear_capture').replace('f315_clear_capture(', 'f325_clear_capture(')+'\n'
 for name in ('clear_point','native_gain','reset_counter_sequence','native_memory_clear','native_configuration','native_bootstrap'):code+=function(backend,name)+'\n'
 code+=r'''
int main(void){
 unsigned i,j,n,entries,exits,pairs;u32 invalid[]={0xe00,0xe04,0xffc,0x1800,0xffffffff,2};u32 old_addresses[1408],new_addresses[1408];
 f315_windows[F315_WINDOW_CAPTURE].base=memory;
 for(i=0;i<sizeof(invalid)/sizeof(invalid[0]);i++){used=0;assert(f315_clear_capture_word(invalid[i])==-EPERM);assert(!used);}
 shadow_enable=false;assert(f315_clear_capture_word(0)==-EPERM);shadow_enable=true;
 used=0;qtn_bb_mutex_enter(1);assert(!f325_clear_capture());qtn_bb_mutex_leave(1);
 n=0;for(i=0;i<used;i++)if(trace[i].kind==4){assert(n<1408);old_addresses[n++]=trace[i].address;}
 assert(n==1408&&old_addresses[0]==0xe6400000&&old_addresses[1407]==0xe64017fc);
 used=0;assert(!native_memory_clear());n=0;
 for(i=0;i<used;i++)if(trace[i].kind==4){assert(n<1408);new_addresses[n++]=trace[i].address;}
 assert(n==1408);
 for(i=0;i<256;i++){assert(new_addresses[2*i]==0xe6401400+4*i);assert(new_addresses[2*i+1]==0xe6401000+4*i);}
 for(i=0;i<896;i++)assert(new_addresses[512+i]==0xe6400000+4*i);
 for(i=0;i<1408;i++){
  assert(!(old_addresses[i]>=0xe6400e00&&old_addresses[i]<0xe6401000));
  assert(!(new_addresses[i]>=0xe6400e00&&new_addresses[i]<0xe6401000));
  for(j=0;j<1408&&new_addresses[i]!=old_addresses[j];j++){}
  assert(j<1408);
 }
 for(scan=0;scan<3;scan++)for(chip=0;chip<256;chip++)assert(native_gain(chip,scan)==(!scan||(chip&0xf0)==0x40?0x23:0x19));
 used=depth=clock_calls=0;chip=0x50;scan=1;assert(!native_bootstrap());
 entries=exits=pairs=n=0;
 for(i=0;i<used;i++){
  if(trace[i].kind==1)entries++;
  if(trace[i].kind==2)exits++;
  if(trace[i].kind==3&&trace[i].address==0xe6091518){assert(trace[i].value==0);pairs++;}
  if(trace[i].kind==4){assert(trace[i].address==new_addresses[n++]);}
  if(trace[i].kind==3)assert(trace[i].address<0xe60914e8||trace[i].address>0xe6091500); /* no IIR during bootstrap */
 }
 fprintf(stderr,"TRACE_SUMMARY enters=%u leaves=%u counter_writes=%u clocks=%u memory_words=%u counter_address=%x\n",entries,exits,pairs,clock_calls,n,reg_address[F315_REG_CNT_L]);
 assert(entries==6&&exits==6&&pairs==4&&clock_calls==2&&n==1408);
 assert(target_gain==0x19&&epoch_base==10000020U&&f315_configured&&!iir_programmed);
 for(i=0;i<200;i++)phase("bounded");
 assert(phase_lines==96);
 puts("F332_STARTUP_PASS old_new_words=1408 invalid_hole_writes=0 fifo_first=1 bb_phases=6 cnt_writes=4 gain_vectors=768 phase_limit=96 hardware=0");return 0;
}
'''
 (out/'harness.c').write_text(code,newline='\n')
 script=f"set -eu\ncc -std=gnu11 -O2 -Wall -Wextra -Werror '{linux(out/'harness.c')}' -o '{linux(out/'test')}'\n'{linux(out/'test')}'\n"
 (out/'run.sh').write_bytes(script.encode());p=subprocess.run(['wsl.exe','-d','podman-mem9-tidb','-u','root','-e','sh',linux(out/'run.sh')],capture_output=True,text=True,timeout=60)
 (out/'run.log').write_text(p.stdout+p.stderr)
 status='PASS_EXACT_C_STARTUP_PLAN_NO_HARDWARE' if not p.returncode and 'F332_STARTUP_PASS' in p.stdout else 'FAIL'
 report={'status':status,'hardware':False,'sources':{str(x.relative_to(ROOT)):sha(x) for x in (OLD,SEALED,P/'f332_setup.inc',P/'f332_hardware.c')},'evidence':p.stdout.strip(),'errors':p.stderr[-2000:]}
 (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'output':str(out),**report},indent=2));return status=='FAIL'
if __name__=='__main__':raise SystemExit(main())
