"""Exercise actual bounded loader on exact selected firmware bytes and mutations.

Reads owned MuC/AuC/DSP carriers. Mapping/copy/CCM helpers are fakes; never writes
firmware or accesses the radio. Runs 32-bit arithmetic and preserves hashes.
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
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <limits.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;typedef uint32_t __le32;
#define __packed __attribute__((packed))
#define le32_to_cpu(x) (x)
#define U32_MAX UINT32_MAX
#define KERN_ERR ""
#define printk(...) ((void)0)
#define DBGPRINTF(...) ((void)0)
#define QDRV_BLD_VER 0x08020059U
#define QDRV_FWINFO_VADDR 0xffff0000U
#define QDRV_FWINFO_TYPE_RELEASE 1U
#define ELFMAG "\177ELF"
#define SELFMAG 4
#define EI_CLASS 4
#define EI_DATA 5
#define EI_VERSION 6
#define ELFCLASS32 1
#define ELFDATA2LSB 1
#define EV_CURRENT 1
#define ET_EXEC 2
#define EM_ARCOMPACT 93
#define PT_LOAD 1
typedef struct{unsigned char e_ident[16];uint16_t e_type,e_machine;uint32_t e_version,e_entry,e_phoff,e_shoff,e_flags;uint16_t e_ehsize,e_phentsize,e_phnum,e_shentsize,e_shnum,e_shstrndx;}Elf32_Ehdr;
typedef struct{uint32_t p_type,p_offset,p_vaddr,p_paddr,p_filesz,p_memsz,p_flags,p_align;}Elf32_Phdr;
struct qdrv_fwinfo{char magic[8];__le32 type,version;}__packed;
enum qdrv_fw_cpu{qdrv_fw_muc,qdrv_fw_auc,qdrv_fw_dsp};
#define RUBY_DSP_XYMEM_BEGIN 0xd0000000U
#define RUBY_DSP_XYMEM_END 0xdfffffffU
#define RUBY_SRAM_BEGIN 0x88000000U
#define RUBY_SRAM_SIZE 0x80000U
#define RUBY_DRAM_BEGIN 0x80000000U
#define RUBY_MAX_DRAM_SIZE 0x8000000U
#define TOPAZ_AUC_IMEM_ADDR 0xe5000000U
#define TOPAZ_AUC_IMEM_SIZE 0x8000U
#define TOPAZ_AUC_DMEM_ADDR 0xe5101000U
#define TOPAZ_AUC_DMEM_SIZE 0x3000U
#define RUBY_BAD_VIRT_ADDR NULL
#define __in_mem_range(a,s,n) ((a)>=(s)&&(a)-(s)<(n))
static void*bus_to_virt(unsigned long a){if(a>=0x80000000U&&a-0x80000000U<0x80000U)return(void*)(a+0x8000000U);if(a<0x8000000U)return(void*)(a+0x80000000U);if(a<0xc0000000U)return NULL;return(void*)a;}
static unsigned long muc_to_lhost(unsigned long a){if(a>=0x60000000U&&a-0x60000000U<0x80000U)a-=0x60000000U-0x80000000U;return(unsigned long)bus_to_virt(a);}
static unsigned long virt_to_phys(void*p){return(unsigned long)p;}
static unsigned maps,unmaps,copies,zeros,fail_map_at;static size_t mapping_size;
static void*ioremap_nocache(unsigned long a,size_t n){assert(a&&n&&n<0x1000000U);maps++;if(fail_map_at==maps)return NULL;mapping_size=n;void*p=malloc(n);assert(p);memset(p,0xa5,n);return p;}
static void iounmap(void*p){assert(p);unmaps++;free(p);}
static void qdrv_fw_auc_memcpy(void*d,const void*s,unsigned long n,unsigned long a){(void)a;assert(n<=mapping_size);copies++;memcpy(d,s,n);}
static void qdrv_fw_auc_memzero(void*d,unsigned long n,unsigned long a){(void)a;assert(n<=mapping_size);zeros++;memset(d,0,n);}
'''

TEST = r'''
static char*read_carrier(const char*name,size_t*size){FILE*f=fopen(name,"rb");assert(f);assert(!fseek(f,0,SEEK_END));long n=ftell(f);assert(n>0);rewind(f);char*b=malloc((size_t)n);assert(b&&fread(b,1,(size_t)n,f)==(size_t)n);fclose(f);*size=n;return b;}
static void reset(void){assert(maps==unmaps||fail_map_at);maps=unmaps=copies=zeros=fail_map_at=0;}
static void reject(char*b,size_t n,int cpu,unsigned*cases){reset();uint32_t start=0xdeadbeef;int rc=qdrv_fw_install(b,n,&start,cpu);assert(rc<0&&start==0xdeadbeef&&!maps&&!unmaps&&!copies&&!zeros);(*cases)++;}
int main(int argc,char**argv){assert(argc==4);_Static_assert(sizeof(size_t)==4,"32bit");unsigned cases=0;
for(int cpu=0;cpu<3;cpu++){size_t n;char*b=read_carrier(argv[cpu+1],&n);Elf32_Ehdr h;assert(!qdrv_fw_preflight(b,n,cpu,&h));Elf32_Phdr*ph=(void*)(b+52);uint32_t start=0xdeadbeef;reset();assert(qdrv_fw_install(b,n,&start,cpu)==h.e_phnum&&start==h.e_entry&&maps==unmaps);unsigned expected_maps=maps;cases++;
 for(size_t cut=0;cut<52+(size_t)h.e_phnum*32;cut++)reject(b,cut,cpu,&cases);
 /* Every short nonempty payload is rejected before any destination map. */
 size_t last=52+(size_t)h.e_phnum*32;for(unsigned i=0;i<h.e_phnum;i++)last+=ph[i].p_filesz;
 for(size_t cut=last>128?last-128:0;cut<last;cut++)reject(b,cut,cpu,&cases);
 char*m=malloc(n);assert(m);unsigned offsets[]={0,4,5,6,16,18,20,28,40,42,44};
 for(unsigned i=0;i<sizeof(offsets)/sizeof(*offsets);i++){memcpy(m,b,n);m[offsets[i]]^=0x7f;reject(m,n,cpu,&cases);}
 memcpy(m,b,n);((Elf32_Ehdr*)m)->e_entry=0xe0000040;reject(m,n,cpu,&cases);
 unsigned payload_index=h.e_phnum-1;while(!ph[payload_index].p_filesz||ph[payload_index].p_vaddr==QDRV_FWINFO_VADDR)payload_index--;
 unsigned fields[]={0,4,16,20};for(unsigned i=0;i<4;i++){memcpy(m,b,n);uint32_t*p=(void*)(m+52+payload_index*32+fields[i]);*p=i==0?2:i==1?0xffffffffU:i==2?0xffffffffU:0;reject(m,n,cpu,&cases);}
 memcpy(m,b,n);Elf32_Phdr*p=(void*)(m+52+payload_index*32);p->p_vaddr=0xc0000000;p->p_paddr=0xc0000000;reject(m,n,cpu,&cases);
 memcpy(m,b,n);p=(void*)(m+52+payload_index*32);p->p_vaddr=0x8007ffff;p->p_paddr=0x8007ffff;p->p_filesz=0;p->p_memsz=2;reject(m,n,cpu,&cases);
 for(unsigned i=0;i<h.e_phnum;i++)if(ph[i].p_vaddr==QDRV_FWINFO_VADDR){for(unsigned j=0;j<3;j++){memcpy(m,b,n);struct qdrv_fwinfo*info=(void*)(m+ph[i].p_offset);if(j==0)info->magic[0]='X';if(j==1)info->type=2;if(j==2)info->version++;reject(m,n,cpu,&cases);}}
 reset();fail_map_at=1;start=0xdeadbeef;assert(qdrv_fw_install(b,n,&start,cpu)==-ENOMEM&&start==0xdeadbeef&&maps==1&&!unmaps);cases++;
 if(expected_maps>1){reset();fail_map_at=2;start=0xdeadbeef;assert(qdrv_fw_install(b,n,&start,cpu)==-ENOMEM&&start==0xdeadbeef&&maps==2&&unmaps==1);cases++;}
 reset();assert(qdrv_fw_install(b,n,NULL,cpu)==-EINVAL&&!maps);cases++;reject(b,n,4,&cases);free(m);free(b);
}
printf("{\"cases\":%u,\"carriers\":3,\"preflight_error_mapping_calls\":0}\n",cases);return 0;}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assert not args.output.exists()
    args.output.mkdir(parents=True)
    source = args.candidate / 'source/qdrv/qdrv_fw.c'
    text = source.read_text()
    funcs = [function(text, signature) for signature in (
        'static int qdrv_fw_check_info(', 'static int qdrv_fw_physical_range(',
        'static int qdrv_fw_segment_address(', 'static int qdrv_fw_preflight(',
        'static int qdrv_fw_install_segment(', 'static int qdrv_fw_install(')]
    version = (args.candidate / 'source/qdrv/qdrv_bld.h').read_text()
    # The actual firmware check consumes the numeric product release constant.
    import re
    matches = re.findall(r'#define\s+QDRV_BLD_VER\s+\(?(0x[0-9a-fA-F]+)', version)
    match = matches[-1] if matches else None
    assert match, 'QDRV release version absent'
    prefix = re.sub(r'#define QDRV_BLD_VER 0x[0-9a-fA-F]+U',
                    '#define QDRV_BLD_VER ' + match + 'U', PRE)
    fixture = args.output / 'actual-loader.c'
    fixture.write_text(prefix + '\n'.join(funcs) + TEST, newline='\n')
    compiler = ROOT / 'tools/external/llvm-mingw-20260616-ucrt-x86_64/bin/i686-w64-mingw32-clang.exe'
    binary = args.output / 'fixture.exe'
    run = subprocess.run([str(compiler), '-O1', '-std=gnu11', '-Wall', '-Wextra',
                          str(fixture), '-o', str(binary)], capture_output=True)
    (args.output / 'compile.log').write_bytes(run.stdout + run.stderr)
    assert not run.returncode, run.stderr.decode()
    carriers = [ROOT / 'work/hgw500-rootfs-live/squashfs-root/etc/firmware' / name
                for name in ('qtn_driver.qtn_ruby.0.bin', 'auc_driver.nomu.0.bin', 'rdsp_driver.0.bin')]
    run = subprocess.run([str(binary), *map(str, carriers)], capture_output=True)
    (args.output / 'run.log').write_bytes(run.stdout + run.stderr)
    assert not run.returncode, run.stderr.decode()
    result = {'status': 'PASS_ACTUAL_BOUNDED_LOADER_SELECTED_CARRIERS_AND_32BIT_MUTATIONS',
              'hardware_accessed': False, 'firmware_eligible': False, **json.loads(run.stdout),
              'pins': {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in (Path(__file__), source, fixture, compiler, binary, *carriers)},
              'limits': ['Actual C preflight/install bodies; fake mapping/address helpers/CCM writes.',
                         'Selected OEM packed carriers pass; negative structural/metadata/address inputs never map.',
                         'Map failure may follow earlier segment writes but does not publish the firmware entry.',
                         'No actual memory/bus/core execution or complete SRAM writer exclusion proof.']}
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
