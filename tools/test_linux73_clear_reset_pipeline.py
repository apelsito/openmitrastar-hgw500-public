"""Exercise actual clear/crash-log/reset controllers with fake kernel/MMIO.

No router access. The reset controller tests software admission and ordering;
it cannot prove that NETSS/TQE/firmware producers are physically quiescent.
"""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from prepare_tqe_bounded_admission_prototype import function

ROOT = Path(__file__).resolve().parents[1]

PRE = r'''
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <assert.h>
#include <errno.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;
#define __iomem
#define GFP_KERNEL 0
#define ARRAY_SIZE(x) (sizeof(x)/sizeof(*(x)))
#define pr_info(...) ((void)0)
#define pr_err(...) ((void)0)
#define DBGPRINTF_E(...) ((void)0)
#define CONFIG_ARC_MUC_STACK_INIT 0x8803ffc0U
#define CONFIG_ARC_MUC_STACK_SIZE 2048U
#define RUBY_SRAM_BEGIN 0x88000000U
#define RUBY_SRAM_SIZE 0x80000U
#define CONFIG_ARC_MUC_SRAM_B1_BASE 0x20000U
#define CONFIG_ARC_MUC_SRAM_B1_SIZE 0x10000U
#define CONFIG_ARC_MUC_SRAM_B2_BASE 0x30000U
#define CONFIG_ARC_MUC_SRAM_B2_SIZE 0xffc0U
#define RUBY_CRUMBS_ADDR 0x8803ffc0U
#define RUBY_CRUMBS_SIZE 0x40U
#define RUBY_DRAM_BEGIN 0x80000000U
#define RUBY_MAX_DRAM_SIZE 0x8000000U
#define CONFIG_ARC_MUC_BASE 0xe0000U
#define CONFIG_ARC_MUC_SIZE 0x2c1000U
#define CONFIG_ARC_DSP_BASE 0x20000U
#define CONFIG_ARC_DSP_SIZE 0xc0000U
#define HEADER_CORE_DUMP 0xa5c3U
struct qdrv_cb{u32 resources;};struct device{struct qdrv_cb*cb;};
static struct qdrv_cb*dev_get_drvdata(struct device*d){return d?d->cb:NULL;}
static char*qdrv_crash_log;static uint32_t qdrv_crash_log_len;
struct om73_sram_writer_token{uint64_t generation;u32 cpu;};
struct om73_sram_reset_token{uint64_t generation;u32 mask;};
static unsigned held,begins,ends,checks,maps,unmaps,clears,reads,copyreads;
static unsigned deny_check,fail_map,fail_alloc;static int begin_error,end_error;
static u16 log_magic,log_size;static unsigned core_begins,hw_resets,boot_failures;
static int reset_begin_error,reset_end_error,core_begin_error;static unsigned reset_held;
static int om73_sram_writer_begin(unsigned cpu,struct om73_sram_writer_token*t){assert(!held&&!reset_held);begins++;if(begin_error)return begin_error;held=1;t->cpu=cpu;t->generation=1;return 0;}
static int om73_sram_writer_end(struct om73_sram_writer_token*t){assert(held&&t->generation==1);ends++;held=0;return end_error;}
static int om73_sram_writer_check(const struct om73_sram_writer_token*t,unsigned long a,size_t n){assert(held&&t->generation==1&&a&&n);checks++;return checks==deny_check?-EBUSY:0;}
static void*ioremap_nocache(unsigned long p,size_t n){assert(held&&p&&n&&checks==6);maps++;if(maps==fail_map)return NULL;void*b=calloc(1,n);assert(b);if(p==CONFIG_ARC_MUC_STACK_INIT-CONFIG_ARC_MUC_STACK_SIZE){memcpy(b,&log_magic,2);memcpy((char*)b+2,&log_size,2);if(log_size<=n-4)for(unsigned i=0;i<log_size;i++)((char*)b)[4+i]=(char)i;}return b;}
static void iounmap(void*p){assert(held&&p);unmaps++;free(p);}
static u16 readw(void*p){assert(held&&p);u16 v;memcpy(&v,p,2);reads++;return v;}
static void memset_io(void*p,int v,size_t n){assert(held&&p&&checks==6);clears++;memset(p,v,n);}
static void memcpy_fromio(void*d,const void*s,size_t n){assert(held);copyreads++;memcpy(d,s,n);}
static void*kmalloc(size_t n,int f){(void)f;return fail_alloc?NULL:malloc(n?n:1);}
static int om73_sram_reset_begin(u32 m,struct om73_sram_reset_token*t){assert(m==0x4180&&!held&&!reset_held);if(reset_begin_error)return reset_begin_error;reset_held=1;t->mask=m;t->generation=1;return 0;}
static int om73_sram_reset_end(struct om73_sram_reset_token*t){assert(reset_held&&t->mask==0x4180&&t->generation==1);reset_held=0;return reset_end_error;}
static int qdrv_f355_core_begin(void){assert(reset_held);core_begins++;return core_begin_error;}
static void hal_reset(void){assert(reset_held);hw_resets++;}
static void qdrv_f355_boot_failure(void){assert(!reset_held);boot_failures++;}
struct qdrv_clearsram_region{const char*name;u32 start,size,allowed_start,allowed_size;};
'''

TEST = r'''
static void reset(void){assert(!held&&!reset_held);free(qdrv_crash_log);qdrv_crash_log=NULL;qdrv_crash_log_len=0;begins=ends=checks=maps=unmaps=clears=reads=copyreads=0;deny_check=fail_map=fail_alloc=0;begin_error=end_error=0;log_magic=log_size=0;reset_begin_error=reset_end_error=core_begin_error=0;core_begins=hw_resets=boot_failures=0;}
int main(void){unsigned cases=0;struct qdrv_cb cb={0};struct device dev={&cb};
 for(unsigned bad=0;bad<3;bad++){reset();cb.resources=bad==2?1:0;int rc=qdrv_command_clearsram(bad==0?NULL:&dev,bad==1?2:1,NULL);assert(rc==(bad==0?-ENODEV:bad==1?-EINVAL:-EBUSY)&&begins==1&&ends==1&&!checks&&!maps);cases++;}cb.resources=0;
 for(unsigned denied=1;denied<=6;denied++){reset();deny_check=denied;assert(qdrv_command_clearsram(&dev,1,NULL)==-EBUSY&&checks==denied&&!maps&&ends==1);cases++;}
 reset();begin_error=-EBUSY;assert(qdrv_command_clearsram(&dev,1,NULL)==-EBUSY&&!maps&&!checks&&!ends);cases++;
 reset();assert(!qdrv_command_clearsram(&dev,1,NULL)&&begins==1&&ends==1&&checks==6&&maps==6&&unmaps==6&&clears==5&&!qdrv_crash_log&&reads==1);cases++;
 for(unsigned m=1;m<=6;m++){reset();fail_map=m;assert(qdrv_command_clearsram(&dev,1,NULL)==-ENOMEM&&maps==m&&unmaps==m-1&&ends==1&&clears==(m>1?m-2:0));cases++;}
 for(unsigned length=0;length<=2044;length+=511){reset();log_magic=HEADER_CORE_DUMP;log_size=length;assert(!qdrv_command_clearsram(&dev,1,NULL)&&qdrv_crash_log&&qdrv_crash_log_len==length&&copyreads==1&&reads==2&&maps==6&&unmaps==6);for(unsigned i=0;i<length;i++)assert(qdrv_crash_log[i]==(char)i);cases++;}
 reset();log_magic=HEADER_CORE_DUMP;log_size=2045;assert(qdrv_command_clearsram(&dev,1,NULL)==-ERANGE&&maps==1&&unmaps==1&&!clears&&!qdrv_crash_log&&!qdrv_crash_log_len);cases++;
 reset();log_magic=HEADER_CORE_DUMP;log_size=32;fail_alloc=1;assert(qdrv_command_clearsram(&dev,1,NULL)==-ENOMEM&&maps==1&&unmaps==1&&!clears&&!qdrv_crash_log&&!qdrv_crash_log_len);cases++;
 reset();qdrv_crash_log=malloc(8);qdrv_crash_log_len=8;assert(!qdrv_command_clearsram(&dev,1,NULL)&&maps==5&&unmaps==5&&!reads&&!copyreads&&clears==5&&qdrv_crash_log_len==8);cases++;
 reset();end_error=-EPERM;assert(qdrv_command_clearsram(&dev,1,NULL)==-EPERM&&clears==5&&ends==1);cases++;
 reset();fail_map=2;end_error=-EPERM;assert(qdrv_command_clearsram(&dev,1,NULL)==-ENOMEM&&ends==1);cases++;
 struct qdrv_clearsram_region ranges[]={{"zero",1,0,1,16},{"under",0,1,1,16},{"overflow",UINT32_MAX,2,1,UINT32_MAX},{"over-allow",17,1,1,16},{"allowed-overflow",1,1,UINT32_MAX,2}};
 for(unsigned i=0;i<5;i++){assert(!qdrv_clearsram_range_valid(&ranges[i]));cases++;}
 reset();reset_begin_error=-EBUSY;assert(qdrv_soc_admitted_core_reset()==-EBUSY&&!core_begins&&!hw_resets&&!boot_failures);cases++;
 reset();core_begin_error=-EIO;assert(qdrv_soc_admitted_core_reset()==-EIO&&core_begins==1&&!hw_resets&&!boot_failures&&!reset_held);cases++;
 reset();assert(!qdrv_soc_admitted_core_reset()&&core_begins==1&&hw_resets==1&&!boot_failures&&!reset_held);cases++;
 reset();reset_end_error=-EPERM;assert(qdrv_soc_admitted_core_reset()==-EPERM&&core_begins==1&&hw_resets==1&&boot_failures==1&&!reset_held);cases++;
 reset();printf("{\"cases\":%u,\"clear_regions\":5,\"preflight_spans\":6,\"reset_software_only\":true}\n",cases);return 0;}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    assert not a.output.exists()
    a.output.mkdir(parents=True)
    control = a.candidate / 'source/qdrv/qdrv_control.c'
    soc = a.candidate / 'source/qdrv/qdrv_soc.c'
    text = control.read_text()
    actual = '\n'.join(function(text, signature) for signature in (
        'static int qdrv_clearsram_range_valid(', 'static int qdrv_clearsram_zero_region(',
        'static int qdrv_clearsram_capture_log(', 'static int qdrv_command_clearsram_owned(',
        'static int qdrv_command_clearsram(struct device *dev, int argc, char *argv[])\n{'))
    actual += function(soc.read_text(), 'static int qdrv_soc_admitted_core_reset(')
    fixture = a.output / 'actual-clear-reset.c'
    fixture.write_text(PRE + actual + TEST, newline='\n')
    compiler = ROOT / 'tools/external/llvm-mingw-20260616-ucrt-x86_64/bin/i686-w64-mingw32-clang.exe'
    binary = a.output / 'fixture.exe'
    run = subprocess.run([str(compiler), '-std=gnu11', '-O1', '-Wall', '-Wextra',
                          str(fixture), '-o', str(binary)], capture_output=True)
    (a.output / 'compile.log').write_bytes(run.stdout + run.stderr)
    assert not run.returncode, run.stderr.decode()
    run = subprocess.run([str(binary)], capture_output=True)
    (a.output / 'run.log').write_bytes(run.stdout + run.stderr)
    assert not run.returncode, run.stderr.decode()
    result = {'status': 'PASS_ACTUAL_R26_CLEAR_CRASH_LOG_MAPPING_AND_RESET_ORDER_CONTROLLERS',
              'hardware_accessed': False, 'firmware_eligible': False, **json.loads(run.stdout),
              'pins': {str(x): hashlib.sha256(x.read_bytes()).hexdigest()
                       for x in (Path(__file__), control, soc, fixture, compiler, binary)},
              'limits': ['Actual source controllers; constants describe the selected profile and MMIO/leases are mocked.',
                         'No literal SRAM pointer dereference; crash bytes read through a mapping.',
                         'Software reset admission ordering is verified; physical TQE/NETSS writer quiescence is unproved.']}
    (a.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
